import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.core.database import get_db
from app.auth.dependencies import get_current_user, require_role, require_csrf
from app.auth.schemas import JWTPayload
from app.auth.security import get_password_hash
from app.schemas.user import UserCreate, UserUpdate, UserResponse, LoginHistoryResponse
from app.api.v1.endpoints._guards import database_mutation

logger = logging.getLogger("medsync.api.users")
router = APIRouter()


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
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        # Check if username is already taken
        await cur.execute(
            """
            SELECT user_id FROM "user"
            WHERE LOWER(username) = LOWER(%s);
            """,
            (user_in.username.strip(),),
        )
        if await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Username '{user_in.username}' is already in use.",
            )

        # Check if email is already taken (if provided)
        if user_in.email:
            await cur.execute(
                """
                SELECT user_id FROM "user"
                WHERE LOWER(email) = LOWER(%s);
                """,
                (user_in.email.strip(),),
            )
            if await cur.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Email '{user_in.email}' is already registered.",
                )

        # Hash password securely using Argon2id
        hashed_password = get_password_hash(user_in.password)

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
    description="Updates user profile fields and optionally password. Accessible by Admin or the account owner.",
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

    # Legacy login resolution uses email/contact details as account-linking keys.
    if current_user.role.lower() != "admin" and {"email", "contact_details"} & user_in.model_fields_set:
        raise HTTPException(403, "Account-linking fields can only be changed by an administrator.")

    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        # Verify user exists
        await cur.execute('SELECT user_id FROM "user" WHERE user_id = %s;', (user_id,))
        if not await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found.",
            )

        # Check email uniqueness if email is being updated
        if user_in.email:
            await cur.execute(
                """
                SELECT user_id FROM "user"
                WHERE LOWER(email) = LOWER(%s) AND user_id != %s;
                """,
                (user_in.email.strip(), user_id),
            )
            if await cur.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Email '{user_in.email}' is already in use by another user.",
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

        if user_in.password is not None:
            hashed_pwd = get_password_hash(user_in.password)
            update_fields.append("password = %s")
            params.append(hashed_pwd)

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


# ==========================================
# 5. Delete User (Admin Only)
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
# 6. Get User Login History (Admin or Self)
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
