from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.auth.dependencies import get_current_user, require_csrf, require_role, verify_branch_access
from app.auth.schemas import JWTPayload
from app.core.database import get_db
from app.schemas.staff import StaffCreate, StaffResponse, StaffUpdate

STAFF_ROLES = ("admin", "branch_manager", "doctor", "receptionist_cashier")
router = APIRouter(prefix="/staff", tags=["Staff"])


async def _get_staff(conn: AsyncConnection, staff_id: int) -> dict:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT * FROM staff WHERE staff_id = %s;", (staff_id,))
        staff = await cur.fetchone()
    if not staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Staff member {staff_id} not found",
        )
    return staff


def _check_branch_access(staff: dict, current_user: JWTPayload) -> None:
    verify_branch_access(staff["branch_id"], current_user)


def _check_manager_branch(branch_id: int, current_user: JWTPayload) -> None:
    if current_user.role.lower() != "admin" and current_user.branch_id != branch_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Branch managers can only manage staff in their assigned branch.")


@router.get("", response_model=List[StaffResponse], summary="List staff")
async def list_staff(
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*STAFF_ROLES)),
):
    query = "SELECT * FROM staff"
    params = []
    if current_user.role.lower() != "admin":
        query += " WHERE branch_id = %s"
        params.append(current_user.branch_id)
    query += " ORDER BY last_name, first_name;"
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(query, tuple(params))
        rows = await cur.fetchall()
    return [StaffResponse(**row) for row in rows]


@router.get("/{staff_id}", response_model=StaffResponse, summary="Get staff member")
async def get_staff(
    staff_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*STAFF_ROLES)),
):
    staff = await _get_staff(conn, staff_id)
    _check_branch_access(staff, current_user)
    return StaffResponse(**staff)


@router.post(
    "",
    response_model=StaffResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create staff member",
    dependencies=[Depends(require_csrf)],
)
async def create_staff(
    payload: StaffCreate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin", "branch_manager")),
):
    _check_manager_branch(payload.branch_id, current_user)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT branch_id FROM branch WHERE branch_id = %s;", (payload.branch_id,))
        if not await cur.fetchone():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch does not exist")
        await cur.execute(
            """INSERT INTO staff (branch_id, users_logins_id, first_name, last_name,
               contact_details, email, staff_type, role)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *;""",
            (payload.branch_id, payload.users_logins_id, payload.first_name,
             payload.last_name, payload.contact_details, str(payload.email),
             payload.staff_type, payload.role),
        )
        return StaffResponse(**await cur.fetchone())


@router.put(
    "/{staff_id}",
    response_model=StaffResponse,
    summary="Update staff member",
    dependencies=[Depends(require_csrf)],
)
async def update_staff(
    staff_id: int,
    payload: StaffUpdate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin", "branch_manager")),
):
    staff = await _get_staff(conn, staff_id)
    _check_branch_access(staff, current_user)
    update_data = payload.model_dump(exclude_unset=True)
    target_branch = update_data.get("branch_id", staff["branch_id"])
    _check_manager_branch(target_branch, current_user)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No update fields provided")
    if "email" in update_data and update_data["email"] is not None:
        update_data["email"] = str(update_data["email"])
    clauses = [f"{key} = %s" for key in update_data]
    values = list(update_data.values()) + [staff_id]
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"UPDATE staff SET {', '.join(clauses)} WHERE staff_id = %s RETURNING *;",
            tuple(values),
        )
        return StaffResponse(**await cur.fetchone())


@router.delete(
    "/{staff_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete staff member",
    dependencies=[Depends(require_csrf)],
)
async def delete_staff(
    staff_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin", "branch_manager")),
):
    staff = await _get_staff(conn, staff_id)
    _check_branch_access(staff, current_user)
    if current_user.staff_id == staff_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Cannot delete your own staff account.")
    async with conn.cursor() as cur:
        await cur.execute("DELETE FROM staff WHERE staff_id = %s;", (staff_id,))
    return None