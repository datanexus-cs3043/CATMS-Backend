from typing import List

from fastapi import APIRouter, Depends, HTTPException
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.api.v1.endpoints._guards import STAFF_ROLES, check_branch_scope
from app.auth.dependencies import get_current_user
from app.auth.schemas import JWTPayload
from app.core.database import get_db
from app.schemas.insurance_policy import InsurancePolicyResponse

router = APIRouter(prefix="/insurance/policies", tags=["Insurance Policies"])


async def _get_policy(cur, policy_id: int) -> dict:
    await cur.execute(
        """SELECT p.*, ip.provider_name,
                  pt.first_name || ' ' || pt.last_name AS patient_name,
                  pt.branch_id
           FROM insurance_policy p
           JOIN insurance_provider ip ON ip.provider_id = p.provider_id
           JOIN patient pt ON pt.patient_id = p.patient_id
           WHERE p.policy_id = %s;""",
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
