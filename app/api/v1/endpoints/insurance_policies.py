from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.api.v1.endpoints._guards import STAFF_ROLES, check_branch_scope, database_mutation
from app.auth.dependencies import get_current_user, require_csrf, require_role
from app.auth.schemas import JWTPayload
from app.core.database import get_db
from app.schemas.insurance_policy import (
    InsurancePolicyCreate,
    InsurancePolicyResponse,
    InsurancePolicyUpdate,
)

router = APIRouter(prefix="/insurance/policies", tags=["Insurance Policies"])
POLICY_WRITE_ROLES = ("admin", "branch_manager", "receptionist_cashier")


async def _get_policy(cur, policy_id: int) -> dict:
    await cur.execute(
        """SELECT p.*, ip.provider_name,
                  pt.first_name || ' ' || pt.last_name AS patient_name,
                  pt.branch_id
           FROM insurance_policy p
           JOIN insurance_provider ip ON ip.provider_id = p.provider_id
           JOIN patient pt ON pt.patient_id = p.patient_id
           WHERE p.policy_id = %s FOR UPDATE OF p;""",
        (policy_id,),
    )
    policy = await cur.fetchone()
    if not policy:
        raise HTTPException(404, f"Insurance policy {policy_id} not found")
    return policy


def _authorize_policy(policy: dict, current_user: JWTPayload, *, write: bool = False) -> None:
    if current_user.user_type == "patient":
        if current_user.patient_id != policy["patient_id"]:
            raise HTTPException(403, "You are not authorized to access this insurance policy.")
        if write:
            raise HTTPException(403, "Patients cannot modify insurance policies.")
        return
    if current_user.role.lower() not in STAFF_ROLES:
        raise HTTPException(403, "Staff credentials required for this resource.")
    check_branch_scope(policy["branch_id"], current_user)


@router.get("", response_model=List[InsurancePolicyResponse])
async def list_insurance_policies(
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        query = """SELECT p.*, ip.provider_name,
                          pt.first_name || ' ' || pt.last_name AS patient_name,
                          pt.branch_id
                   FROM insurance_policy p
                   JOIN insurance_provider ip ON ip.provider_id = p.provider_id
                   JOIN patient pt ON pt.patient_id = p.patient_id"""
        params = []
        if current_user.user_type == "patient":
            query += " WHERE p.patient_id = %s"
            params.append(current_user.patient_id)
        else:
            if current_user.role.lower() not in STAFF_ROLES:
                raise HTTPException(403, "Staff credentials required for this resource.")
            if current_user.role.lower() != "admin":
                query += " WHERE pt.branch_id = %s"
                params.append(current_user.branch_id)
        query += " ORDER BY p.start_date DESC, p.policy_id DESC;"
        await cur.execute(query, tuple(params))
        return [InsurancePolicyResponse(**row) for row in await cur.fetchall()]


@router.get("/{policy_id}", response_model=InsurancePolicyResponse)
async def get_insurance_policy(
    policy_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        policy = await _get_policy(cur, policy_id)
    _authorize_policy(policy, current_user)
    return InsurancePolicyResponse(**policy)


async def _validate_references(cur, patient_id: int, provider_id: int) -> dict:
    await cur.execute("SELECT patient_id, branch_id FROM patient WHERE patient_id = %s;", (patient_id,))
    patient = await cur.fetchone()
    if not patient:
        raise HTTPException(422, f"Patient {patient_id} not found")
    await cur.execute("SELECT provider_id FROM insurance_provider WHERE provider_id = %s;", (provider_id,))
    if not await cur.fetchone():
        raise HTTPException(422, f"Insurance provider {provider_id} not found")
    return patient


def _validate_dates(start_date, end_date) -> None:
    if end_date < start_date:
        raise HTTPException(422, "end_date must be on or after start_date")


@router.post(
    "",
    response_model=InsurancePolicyResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_insurance_policy(
    payload: InsurancePolicyCreate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*POLICY_WRITE_ROLES)),
):
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        patient = await _validate_references(cur, payload.patient_id, payload.provider_id)
        check_branch_scope(patient["branch_id"], current_user)
        _validate_dates(payload.start_date, payload.end_date)
        await cur.execute(
            """INSERT INTO insurance_policy
               (patient_id, provider_id, policy_number, start_date, end_date, status)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING policy_id;""",
            (payload.patient_id, payload.provider_id, payload.policy_number,
             payload.start_date, payload.end_date, payload.status),
        )
        policy_id = (await cur.fetchone())["policy_id"]
        policy = await _get_policy(cur, policy_id)
    return InsurancePolicyResponse(**policy)


@router.put(
    "/{policy_id}",
    response_model=InsurancePolicyResponse,
    dependencies=[Depends(require_csrf)],
)
async def update_insurance_policy(
    policy_id: int,
    payload: InsurancePolicyUpdate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*POLICY_WRITE_ROLES)),
):
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(400, "No update fields provided")
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        policy = await _get_policy(cur, policy_id)
        _authorize_policy(policy, current_user, write=True)
        patient_id = update_data.get("patient_id", policy["patient_id"])
        if patient_id != policy["patient_id"]:
            await cur.execute("SELECT claim_id FROM insurance_claim WHERE policy_id = %s LIMIT 1;", (policy_id,))
            if await cur.fetchone():
                raise HTTPException(409, "A policy with claims cannot be reassigned to another patient.")
        provider_id = update_data.get("provider_id", policy["provider_id"])
        patient = await _validate_references(cur, patient_id, provider_id)
        check_branch_scope(patient["branch_id"], current_user)
        start_date = update_data.get("start_date", policy["start_date"])
        end_date = update_data.get("end_date", policy["end_date"])
        _validate_dates(start_date, end_date)
        clauses = [f"{key} = %s" for key in update_data]
        values = list(update_data.values()) + [policy_id]
        await cur.execute(
            f"UPDATE insurance_policy SET {', '.join(clauses)} "
            "WHERE policy_id = %s;",
            tuple(values),
        )
        policy = await _get_policy(cur, policy_id)
    return InsurancePolicyResponse(**policy)


@router.delete(
    "/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def delete_insurance_policy(
    policy_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*POLICY_WRITE_ROLES)),
):
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        policy = await _get_policy(cur, policy_id)
        _authorize_policy(policy, current_user, write=True)
        await cur.execute("DELETE FROM insurance_policy WHERE policy_id = %s;", (policy_id,))
    return None
