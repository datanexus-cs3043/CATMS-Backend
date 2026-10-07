from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.api.v1.endpoints._guards import STAFF_ROLES, check_branch_scope, database_mutation
from app.auth.dependencies import get_current_user, require_csrf, require_role, verify_patient_ownership
from app.auth.schemas import JWTPayload
from app.core.database import get_db
from app.schemas.insurance_claim import (
    InsuranceClaimCreate,
    InsuranceClaimResponse,
    InsuranceClaimUpdate,
)

router = APIRouter(prefix="/insurance/claims", tags=["Insurance Claims"])
CLAIM_WRITE_ROLES = ("admin", "branch_manager", "receptionist_cashier")


async def _get_claim(cur, claim_id: int) -> dict:
    await cur.execute(
        """SELECT c.*, a.patient_id, a.branch_id,
                  p.patient_id AS policy_patient_id,
                  p.policy_number,
                  pt.first_name || ' ' || pt.last_name AS patient_name
           FROM insurance_claim c
           JOIN invoice i ON i.invoice_id = c.invoice_id
           JOIN appointment a ON a.appointment_id = i.appointment_id
           JOIN insurance_policy p ON p.policy_id = c.policy_id
           JOIN patient pt ON pt.patient_id = a.patient_id
           WHERE c.claim_id = %s FOR UPDATE;""",
        (claim_id,),
    )
    claim = await cur.fetchone()
    if not claim:
        raise HTTPException(404, f"Insurance claim {claim_id} not found")
    return claim


def _authorize_claim(claim: dict, current_user: JWTPayload, *, write: bool = False) -> None:
    if claim["patient_id"] != claim["policy_patient_id"]:
        raise HTTPException(409, "The claim policy does not belong to the invoice patient.")
    if current_user.user_type == "patient":
        verify_patient_ownership(claim["patient_id"], current_user)
        if write:
            raise HTTPException(403, "Patients cannot modify insurance claims.")
        return
    if current_user.role.lower() not in STAFF_ROLES:
        raise HTTPException(403, "Staff credentials required for this resource.")
    check_branch_scope(claim["branch_id"], current_user)


async def _validate_references(cur, invoice_id: int, policy_id: int) -> dict:
    await cur.execute(
        """SELECT i.invoice_id, a.patient_id, a.branch_id
           FROM invoice i
           JOIN appointment a ON a.appointment_id = i.appointment_id
           WHERE i.invoice_id = %s;""",
        (invoice_id,),
    )
    invoice = await cur.fetchone()
    if not invoice:
        raise HTTPException(422, f"Invoice {invoice_id} not found")
    await cur.execute(
        "SELECT policy_id, patient_id FROM insurance_policy WHERE policy_id = %s;",
        (policy_id,),
    )
    policy = await cur.fetchone()
    if not policy:
        raise HTTPException(422, f"Insurance policy {policy_id} not found")
    if policy["patient_id"] != invoice["patient_id"]:
        raise HTTPException(422, "The insurance policy must belong to the invoice patient.")
    return invoice


def _validate_amounts(claim_amount, approved_amount) -> None:
    if approved_amount > claim_amount:
        raise HTTPException(422, "approved_amount cannot exceed claim_amount")


@router.get("", response_model=List[InsuranceClaimResponse])
async def list_insurance_claims(
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        query = """SELECT c.*, a.patient_id, a.branch_id,
                          p.patient_id AS policy_patient_id,
                          p.policy_number,
                          pt.first_name || ' ' || pt.last_name AS patient_name
                   FROM insurance_claim c
                   JOIN invoice i ON i.invoice_id = c.invoice_id
                   JOIN appointment a ON a.appointment_id = i.appointment_id
                   JOIN insurance_policy p ON p.policy_id = c.policy_id
                   JOIN patient pt ON pt.patient_id = a.patient_id"""
        params = []
        if current_user.user_type == "patient":
            query += " WHERE a.patient_id = %s"
            params.append(current_user.patient_id)
        else:
            if current_user.role.lower() not in STAFF_ROLES:
                raise HTTPException(403, "Staff credentials required for this resource.")
            if current_user.role.lower() != "admin":
                query += " WHERE a.branch_id = %s"
                params.append(current_user.branch_id)
        query += " ORDER BY c.claim_date DESC, c.claim_id DESC;"
        await cur.execute(query, tuple(params))
        claims = await cur.fetchall()
    return [InsuranceClaimResponse(**claim) for claim in claims]


@router.get("/{claim_id}", response_model=InsuranceClaimResponse)
async def get_insurance_claim(
    claim_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        claim = await _get_claim(cur, claim_id)
    _authorize_claim(claim, current_user)
    return InsuranceClaimResponse(**claim)


@router.post(
    "",
    response_model=InsuranceClaimResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_insurance_claim(
    payload: InsuranceClaimCreate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*CLAIM_WRITE_ROLES)),
):
    _validate_amounts(payload.claim_amount, payload.approved_amount)
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        invoice = await _validate_references(cur, payload.invoice_id, payload.policy_id)
        check_branch_scope(invoice["branch_id"], current_user)
        await cur.execute(
            """INSERT INTO insurance_claim
               (invoice_id, policy_id, claim_date, claim_amount, approved_amount, status)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING claim_id;""",
            (payload.invoice_id, payload.policy_id, payload.claim_date,
             payload.claim_amount, payload.approved_amount, payload.status),
        )
        claim_id = (await cur.fetchone())["claim_id"]
        claim = await _get_claim(cur, claim_id)
    return InsuranceClaimResponse(**claim)


@router.put(
    "/{claim_id}",
    response_model=InsuranceClaimResponse,
    dependencies=[Depends(require_csrf)],
)
async def update_insurance_claim(
    claim_id: int,
    payload: InsuranceClaimUpdate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*CLAIM_WRITE_ROLES)),
):
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(400, "No update fields provided")
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        claim = await _get_claim(cur, claim_id)
        _authorize_claim(claim, current_user, write=True)
        invoice_id = update_data.get("invoice_id", claim["invoice_id"])
        policy_id = update_data.get("policy_id", claim["policy_id"])
        invoice = await _validate_references(cur, invoice_id, policy_id)
        check_branch_scope(invoice["branch_id"], current_user)
        claim_amount = update_data.get("claim_amount", claim["claim_amount"])
        approved_amount = update_data.get("approved_amount", claim["approved_amount"])
        _validate_amounts(claim_amount, approved_amount)
        clauses = [f"{key} = %s" for key in update_data]
        values = list(update_data.values()) + [claim_id]
        await cur.execute(
            f"UPDATE insurance_claim SET {', '.join(clauses)} "
            "WHERE claim_id = %s;",
            tuple(values),
        )
        claim = await _get_claim(cur, claim_id)
    return InsuranceClaimResponse(**claim)


@router.delete(
    "/{claim_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def delete_insurance_claim(
    claim_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*CLAIM_WRITE_ROLES)),
):
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        claim = await _get_claim(cur, claim_id)
        _authorize_claim(claim, current_user, write=True)
        await cur.execute("DELETE FROM insurance_claim WHERE claim_id = %s;", (claim_id,))
    return None
