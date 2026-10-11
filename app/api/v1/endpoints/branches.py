from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.auth.dependencies import require_csrf, require_role
from app.api.v1.endpoints._guards import STAFF_ROLES, check_branch_scope, database_mutation
from app.auth.schemas import JWTPayload
from app.core.database import get_db
from app.schemas.branch import (
    BranchAppointmentResponse,
    BranchCreate,
    BranchDoctorResponse,
    BranchResponse,
    BranchStaffResponse,
    BranchUpdate,
)

router = APIRouter(prefix="/branches", tags=["Branches"])


async def _get_branch(conn: AsyncConnection, branch_id: int) -> dict:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT * FROM branch WHERE branch_id = %s;", (branch_id,))
        branch = await cur.fetchone()
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Branch {branch_id} not found",
        )
    return branch


@router.get("", response_model=List[BranchResponse], summary="List branches")
async def list_branches(
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin", "branch_manager", "receptionist_cashier")),
):
    # Non-admin staff only see their own branch (front desk needs it for booking/registration forms).
    async with conn.cursor(row_factory=dict_row) as cur:
        if current_user.role.lower() == "admin":
            await cur.execute("SELECT * FROM branch ORDER BY branch_name ASC;")
        else:
            check_branch_scope(current_user.branch_id, current_user)
            await cur.execute("SELECT * FROM branch WHERE branch_id = %s ORDER BY branch_name ASC;",
                              (current_user.branch_id,))
        rows = await cur.fetchall()
    return [BranchResponse(**row) for row in rows]


@router.get("/{branch_id}", response_model=BranchResponse, summary="Get branch")
async def get_branch(
    branch_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*STAFF_ROLES)),
):
    branch = await _get_branch(conn, branch_id)
    check_branch_scope(branch_id, current_user)
    return BranchResponse(**branch)


@router.post(
    "",
    response_model=BranchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create branch",
    dependencies=[Depends(require_csrf)],
)
async def create_branch(
    payload: BranchCreate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin")),
):
    # A manager must already belong to this branch, which does not exist yet.
    if payload.manager_staff_id is not None:
        raise HTTPException(422, "Create the branch first, then assign staff belonging to it.")
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """INSERT INTO branch (branch_name, location, contact_details, manager_staff_id)
               VALUES (%s, %s, %s, %s) RETURNING *;""",
            (payload.branch_name.strip(), payload.location.strip(),
             payload.contact_details, payload.manager_staff_id),
        )
        return BranchResponse(**await cur.fetchone())


@router.put(
    "/{branch_id}",
    response_model=BranchResponse,
    summary="Update branch",
    dependencies=[Depends(require_csrf)],
)
async def update_branch(
    branch_id: int,
    payload: BranchUpdate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin", "branch_manager")),
):
    branch = await _get_branch(conn, branch_id)
    check_branch_scope(branch_id, current_user)
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="No update fields provided")
    if "manager_staff_id" in update_data and current_user.role.lower() != "admin":
        raise HTTPException(403, "Only administrators can assign branch managers.")
    if "branch_name" in update_data:
        update_data["branch_name"] = update_data["branch_name"].strip()
    if "location" in update_data:
        update_data["location"] = update_data["location"].strip()
    clauses = [f"{key} = %s" for key in update_data]
    values = list(update_data.values()) + [branch_id]
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        if update_data.get("manager_staff_id") is not None:
            await cur.execute("SELECT staff_id FROM staff WHERE staff_id = %s AND branch_id = %s;",
                              (update_data["manager_staff_id"], branch_id))
            if not await cur.fetchone():
                raise HTTPException(422, "The manager must belong to this branch.")
        await cur.execute(
            f"UPDATE branch SET {', '.join(clauses)} WHERE branch_id = %s RETURNING *;",
            tuple(values),
        )
        return BranchResponse(**await cur.fetchone())


@router.delete(
    "/{branch_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete branch",
    dependencies=[Depends(require_csrf)],
)
async def delete_branch(
    branch_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin")),
):
    await _get_branch(conn, branch_id)
    async with database_mutation(conn), conn.cursor() as cur:
        await cur.execute("DELETE FROM branch WHERE branch_id = %s;", (branch_id,))
    return None


@router.get("/{branch_id}/staff", response_model=List[BranchStaffResponse], summary="List branch staff")
async def list_branch_staff(
    branch_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*STAFF_ROLES)),
):
    await _get_branch(conn, branch_id)
    check_branch_scope(branch_id, current_user)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT * FROM staff WHERE branch_id = %s ORDER BY last_name, first_name;",
            (branch_id,),
        )
        rows = await cur.fetchall()
    return [BranchStaffResponse(**row) for row in rows]


@router.get("/{branch_id}/doctors", response_model=List[BranchDoctorResponse], summary="List branch doctors")
async def list_branch_doctors(
    branch_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*STAFF_ROLES)),
):
    await _get_branch(conn, branch_id)
    check_branch_scope(branch_id, current_user)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """SELECT d.doctor_id, d.staff_id, d.doctor_name,
                      d.doctor_license_number, s.email
               FROM doctor d JOIN staff s ON s.staff_id = d.staff_id
               WHERE s.branch_id = %s ORDER BY d.doctor_name;""",
            (branch_id,),
        )
        rows = await cur.fetchall()
    return [BranchDoctorResponse(**row) for row in rows]


@router.get(
    "/{branch_id}/appointments",
    response_model=List[BranchAppointmentResponse],
    summary="List branch appointments",
)
async def list_branch_appointments(
    branch_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*STAFF_ROLES)),
):
    await _get_branch(conn, branch_id)
    check_branch_scope(branch_id, current_user)
    async with conn.cursor(row_factory=dict_row) as cur:
        query = """SELECT a.appointment_id, a.patient_id, a.doctor_id, a.branch_id,
                      a.appointment_date, a.start_time, a.end_time,
                      a.appointment_type, a.created_by,
                      p.first_name || ' ' || p.last_name AS patient_name,
                      d.doctor_name
               FROM appointment a
               JOIN patient p ON p.patient_id = a.patient_id
               JOIN doctor d ON d.doctor_id = a.doctor_id
               WHERE a.branch_id = %s"""
        params = [branch_id]
        if current_user.role.lower() == "doctor":
            if current_user.doctor_id is None:
                raise HTTPException(403, "A linked doctor profile is required.")
            query += " AND a.doctor_id = %s"
            params.append(current_user.doctor_id)
        query += " ORDER BY a.appointment_date DESC, a.start_time DESC;"
        await cur.execute(query, tuple(params))
        rows = await cur.fetchall()
    return [BranchAppointmentResponse(**row) for row in rows]
