import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from starlette.concurrency import run_in_threadpool

from app.core.database import get_db
from app.auth.dependencies import get_current_user, require_role, require_csrf
from app.auth.schemas import JWTPayload
from app.auth.security import get_password_hash, verify_password
from app.schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    LoginHistoryResponse,
    PasswordChangeRequest,
    PasswordResetResponse,
)
from app.api.v1.endpoints._guards import database_mutation

logger = logging.getLogger("medsync.api.users")
router = APIRouter()
DEFAULT_RESET_PASSWORD = "password123"


async def _check_login_identifiers(cur, username: str, email: str, *, exclude_user_id=None) -> None:
    """Caller holds the account table's SHARE ROW EXCLUSIVE write lock."""
    query = '''SELECT user_id FROM "user"
               WHERE (LOWER(username) IN (LOWER(%s), LOWER(%s))
                   OR LOWER(email) IN (LOWER(%s), LOWER(%s)))'''
    params = (username, email, username, email)
    if exclude_user_id is not None:
        query += " AND user_id != %s"
        params += (exclude_user_id,)
    await cur.execute(query + " LIMIT 1;", params)
    if await cur.fetchone():
        raise HTTPException(409, "That username or account email is already in use. Choose unique sign-in details.")


# ==========================================
# 1. List All Users (Admin Only)
# ==========================================
@router.get(
    "",
    response_model=List[UserResponse],
    summary="List all users",
    description="Returns all user records in the system. Accessible by Admin only.",
)
async def list_users(
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin")),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT user_id, first_name, last_name, contact_details, email, username
            FROM "user"
            ORDER BY user_id ASC;
            """
        )
        users = await cur.fetchall()
        return users


# ==========================================
# 2. Get User by ID (Admin or Self)
# ==========================================
@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get user details",
    description="Fetches a specific user by user_id. Accessible by Admin or the account owner.",
)
async def get_user_by_id(
    user_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    # Enforce access: Admin or own profile
    if current_user.role != "admin" and current_user.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: You can only view your own user profile.",
        )

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT user_id, first_name, last_name, contact_details, email, username
            FROM "user"
            WHERE user_id = %s;
            """,
            (user_id,),
        )
        user = await cur.fetchone()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found.",
            )
        return user


# ==========================================
# 3. Create User (Admin Only)
# ==========================================
@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user",
    description="Registers a new user with an Argon2id hashed password. Accessible by Admin only.",
    dependencies=[Depends(require_csrf)],
)
async def create_user(
    user_in: UserCreate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin")),
):
    # Keep expensive hashing outside the event loop and account-write lock.
    hashed_password = await run_in_threadpool(get_password_hash, user_in.password)
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        await cur.execute('LOCK TABLE "user" IN SHARE ROW EXCLUSIVE MODE;')
        await _check_login_identifiers(cur, user_in.username.strip(), user_in.email.strip())

        await cur.execute(
            """
            INSERT INTO "user" (first_name, last_name, contact_details, email, username, password)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING user_id, first_name, last_name, contact_details, email, username;
            """,
            (
                user_in.first_name,
                user_in.last_name,
                user_in.contact_details,
                user_in.email.strip() if user_in.email else None,
                user_in.username.strip(),
                hashed_password,
            ),
        )
        new_user = await cur.fetchone()
        return new_user


# ==========================================
# 4. Update User (Admin or Self)
# ==========================================
@router.put(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update user details",
    description="Updates user profile fields. Accessible by Admin or the account owner.",
    dependencies=[Depends(require_csrf)],
)
async def update_user(
    user_id: int,
    user_in: UserUpdate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    # Enforce access: Admin or own profile
    if current_user.role != "admin" and current_user.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: You can only update your own user profile.",
        )

    # Preserve administrator control over these account/profile identity fields.
    if current_user.role.lower() != "admin" and {"email", "contact_details"} & user_in.model_fields_set:
        raise HTTPException(403, "Account-linking fields can only be changed by an administrator.")

    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        # Acquire the table lock before any row lock to match registration order.
        if user_in.email is not None:
            await cur.execute('LOCK TABLE "user" IN SHARE ROW EXCLUSIVE MODE;')
        else:
            await cur.execute('LOCK TABLE "user" IN ROW EXCLUSIVE MODE;')
        # Verify user exists
        await cur.execute('SELECT user_id, username FROM "user" WHERE user_id = %s FOR UPDATE;', (user_id,))
        existing_user = await cur.fetchone()
        if not existing_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found.",
            )

        # Check the resulting login identifiers, excluding this account itself.
        if user_in.email is not None:
            await _check_login_identifiers(
                cur, existing_user["username"], user_in.email.strip(), exclude_user_id=user_id,
            )

        # Build dynamic update statement based on provided fields
        update_fields = []
        params = []

        if user_in.first_name is not None:
            update_fields.append("first_name = %s")
            params.append(user_in.first_name)

        if user_in.last_name is not None:
            update_fields.append("last_name = %s")
            params.append(user_in.last_name)

        if "contact_details" in user_in.model_fields_set:
            update_fields.append("contact_details = %s")
            params.append(user_in.contact_details)

        if user_in.email is not None:
            update_fields.append("email = %s")
            params.append(user_in.email.strip())

        if not update_fields:
            # Nothing to update, return current record
            await cur.execute(
                """
                SELECT user_id, first_name, last_name, contact_details, email, username
                FROM "user"
                WHERE user_id = %s;
                """,
                (user_id,),
            )
            return await cur.fetchone()

        params.append(user_id)
        query = f"""
            UPDATE "user"
            SET {", ".join(update_fields)}
            WHERE user_id = %s
            RETURNING user_id, first_name, last_name, contact_details, email, username;
        """
        await cur.execute(query, tuple(params))
        updated_user = await cur.fetchone()
        return updated_user


@router.post(
    "/change-password",
    response_model=PasswordResetResponse,
    summary="Change own password",
    description="Changes the authenticated account owner's password after verifying the current password.",
    dependencies=[Depends(require_csrf)],
)
async def change_password(
    password_in: PasswordChangeRequest,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    if password_in.current_password == password_in.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The new password must be different from the current password.",
        )

    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        # Take the ordinary write lock before locking a row, so identity writers
        # cannot hold the table lock while waiting for this row's password write.
        await cur.execute('LOCK TABLE "user" IN ROW EXCLUSIVE MODE;')
        await cur.execute(
            'SELECT password FROM "user" WHERE user_id = %s FOR UPDATE;',
            (current_user.user_id,),
        )
        user = await cur.fetchone()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User account not found.",
            )

        if not await run_in_threadpool(verify_password, password_in.current_password, user["password"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The current password is incorrect.",
            )

        hashed_password = await run_in_threadpool(get_password_hash, password_in.new_password)
        await cur.execute(
            """
            UPDATE "user"
            SET password = %s
            WHERE user_id = %s;
            """,
            (hashed_password, current_user.user_id),
        )

    return PasswordResetResponse(
        user_id=current_user.user_id,
        message="Password changed successfully.",
    )


@router.post(
    "/{user_id}/reset-password",
    response_model=PasswordResetResponse,
    summary="Reset a user's password",
    description="Resets any user's password to the system default. Accessible by Admin only.",
    dependencies=[Depends(require_csrf), Depends(require_role("admin"))],
)
async def reset_password(
    user_id: int,
    conn: AsyncConnection = Depends(get_db),
):
    hashed_password = await run_in_threadpool(get_password_hash, DEFAULT_RESET_PASSWORD)
    async with database_mutation(conn), conn.cursor() as cur:
        await cur.execute(
            """
            UPDATE "user"
            SET password = %s
            WHERE user_id = %s
            RETURNING user_id;
            """,
            (hashed_password, user_id),
        )
        reset_user = await cur.fetchone()
        if not reset_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found.",
            )

    return PasswordResetResponse(
        user_id=user_id,
        message="Password reset successfully to the default password.",
    )


# ==========================================
# 6. Delete User (Admin Only)
# ==========================================
@router.delete(
    "/{user_id}",
    summary="Delete a user",
    description="Deletes a user account and associated login records. Accessible by Admin only.",
    dependencies=[Depends(require_csrf)],
)
async def delete_user(
    user_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin")),
):
    # Prevent admin from deleting their own currently logged-in account
    if current_user.user_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own administrative account.",
        )

    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        await cur.execute('LOCK TABLE "user" IN ROW EXCLUSIVE MODE;')
        await cur.execute('SELECT user_id FROM "user" WHERE user_id = %s FOR UPDATE;', (user_id,))
        if not await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found.",
            )

        # Delete dependent login audit records
        await cur.execute("DELETE FROM users_logins WHERE user_id = %s;", (user_id,))

        # Delete user
        await cur.execute('DELETE FROM "user" WHERE user_id = %s;', (user_id,))

        return {"message": f"User {user_id} and associated login history deleted successfully."}


# ==========================================
# 7. Get User Login History (Admin or Self)
# ==========================================
@router.get(
    "/{user_id}/login-history",
    response_model=List[LoginHistoryResponse],
    summary="Get user login history",
    description="Returns the login audit trail for a specific user. Accessible by Admin or the account owner.",
)
async def get_user_login_history(
    user_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    # Enforce access: Admin or own profile
    if current_user.role != "admin" and current_user.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: You can only view your own login history.",
        )

    async with conn.cursor(row_factory=dict_row) as cur:
        # Check user exists
        await cur.execute('SELECT user_id FROM "user" WHERE user_id = %s;', (user_id,))
        if not await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found.",
            )

        await cur.execute(
            """
            SELECT users_logins_id, user_id, login_time, user_name
            FROM users_logins
            WHERE user_id = %s
            ORDER BY login_time DESC
            LIMIT 100;
            """,
            (user_id,),
        )
        history = await cur.fetchall()
        return history
