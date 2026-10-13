from decimal import Decimal, ROUND_FLOOR
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


def _coverage_limit(items: list[dict], coverages: list[dict]) -> Decimal:
    """MedSync assumption: treatment caps apply once per policy/invoice (visit).

    Use frozen invoice prices, not today's catalogue prices. Repeated treatment
    lines are aggregated before percentage/cap and rounded down to cents once.
    Missing rules, zero percentages and zero maximums provide no coverage.
    This is not an annual benefit limit or a promise of insurer reimbursement.
    Ambiguous or invalid coverage rules fail closed rather than increasing cover.
    """
    rules = {}
    for coverage in coverages:
        treatment_id = coverage["treatment_id"]
        if treatment_id in rules:
            raise HTTPException(409, "Duplicate treatment coverage rules must be resolved before filing a claim.")
        rules[treatment_id] = coverage

    eligible = Decimal("0.00")
    for item in items:
        minimum_price = Decimal(str(item["minimum_unitprice"]))
        treatment_total = Decimal(str(item["billed_amount"]))
        if (item["minimum_quantity"] <= 0 or not minimum_price.is_finite()
                or not treatment_total.is_finite() or minimum_price < 0 or treatment_total < 0):
            raise HTTPException(409, "Invalid invoice item values must be resolved before filing a claim.")
        rule = rules.get(item["treatment_id"])
        if rule is None:
            continue
        percentage = Decimal(str(rule["coverage_percentage"]))
        maximum = Decimal(str(rule["maximum_amount"]))
        if (not percentage.is_finite() or not maximum.is_finite()
                or not Decimal("0") <= percentage <= Decimal("100") or maximum < 0):
            raise HTTPException(409, "Invalid treatment coverage rules must be resolved before filing a claim.")
        covered = min(treatment_total * percentage / Decimal("100"), maximum)
        eligible += covered.quantize(Decimal("0.01"), rounding=ROUND_FLOOR)
    return eligible


async def _get_claim(cur, claim_id: int, *, lock: bool = False) -> dict:
    await cur.execute(
        """SELECT c.*, a.patient_id, a.branch_id, a.doctor_id,
                  p.patient_id AS policy_patient_id,
                  p.policy_number, ip.provider_name,
                  pt.first_name || ' ' || pt.last_name AS patient_name
           FROM insurance_claim c
           JOIN invoice i ON i.invoice_id = c.invoice_id
           JOIN appointment a ON a.appointment_id = i.appointment_id
           JOIN insurance_policy p ON p.policy_id = c.policy_id
           JOIN insurance_provider ip ON ip.provider_id = p.provider_id
           JOIN patient pt ON pt.patient_id = a.patient_id
           WHERE c.claim_id = %s""" + (" FOR UPDATE OF c" if lock else "") + ";",
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
    if current_user.role.lower() == "doctor" and (current_user.doctor_id is None or current_user.doctor_id != claim["doctor_id"]):
        raise HTTPException(403, "Doctors can only access claims for their own appointments.")


async def _validate_references(cur, invoice_id: int, policy_id: int, *, rejecting: bool = False) -> dict:
    await cur.execute(
        """SELECT i.invoice_id, i.invoice_date, i.amount_paid, i.balance, a.patient_id, a.branch_id
           FROM invoice i
           JOIN appointment a ON a.appointment_id = i.appointment_id
           WHERE i.invoice_id = %s FOR UPDATE OF i;""",
        (invoice_id,),
    )
    invoice = await cur.fetchone()
    if not invoice:
        raise HTTPException(422, f"Invoice {invoice_id} not found")
    await cur.execute(
        "SELECT policy_id, patient_id, status, start_date, end_date "
        "FROM insurance_policy WHERE policy_id = %s FOR SHARE;",
        (policy_id,),
    )
    policy = await cur.fetchone()
    if not policy:
        raise HTTPException(422, f"Insurance policy {policy_id} not found")
    if policy["patient_id"] != invoice["patient_id"]:
        raise HTTPException(422, "The insurance policy must belong to the invoice patient.")
    if not rejecting and (policy["status"] != "Active"
            or not policy["start_date"] <= invoice["invoice_date"] <= policy["end_date"]):
        raise HTTPException(422, "The insurance policy must be active on the invoice date.")
    invoice["policy_id"] = policy_id
    if rejecting:
        # Denial releases a reservation. Changed/inactive terms or a legacy
        # overclaim must not prevent staff recording that outcome. Ownership
        # and branch authorization still apply, and approved_amount must be zero.
        return invoice
    # A separate statement after acquiring the invoice lock sees any item changes
    # that committed while this transaction waited for that lock (READ COMMITTED).
    await cur.execute(
        "SELECT COALESCE(SUM(quantity * unitprice), %s) AS billed_amount "
        "FROM invoice_item WHERE invoice_id = %s;",
        (invoice["amount_paid"] + invoice["balance"], invoice_id),
    )
    invoice["billed_amount"] = (await cur.fetchone())["billed_amount"]
    await cur.execute(
        """SELECT treatment_id, SUM(quantity * unitprice) AS billed_amount,
                  MIN(quantity) AS minimum_quantity, MIN(unitprice) AS minimum_unitprice
           FROM invoice_item WHERE invoice_id = %s GROUP BY treatment_id;""",
        (invoice_id,),
    )
    items = await cur.fetchall()
    # The policy and existing coverage rows stay stable until this claim commits.
    # FOR SHARE also coordinates with the coverage endpoint's row update locks.
    await cur.execute(
        """SELECT coverage_id, treatment_id, coverage_percentage, maximum_amount
           FROM insurance_coverage WHERE policy_id = %s
           ORDER BY coverage_id FOR SHARE;""",
        (policy_id,),
    )
    invoice["eligible_amount"] = _coverage_limit(items, await cur.fetchall())
    return invoice


def _validate_amounts(claim_amount, approved_amount, claim_status) -> None:
    if approved_amount > claim_amount:
        raise HTTPException(422, "approved_amount cannot exceed claim_amount")
    if claim_status != "Approved" and approved_amount != 0:
        raise HTTPException(422, "Only Approved claims may have a non-zero approved_amount.")


async def _validate_claim_total(cur, invoice, claim_amount, approved_amount, claim_status, claim_id=None):
    """Serialize claims on the invoice; approval is not a patient receipt.

    Rejected claims reserve nothing; approved claims reserve the approved amount.
    The per-policy visit budget is separate from the invoice-wide billed ceiling.
    No automatic approval, patient receipt or balance adjustment occurs here.
    """
    if claim_status == "Rejected":
        return
    if claim_amount > invoice["billed_amount"]:
        raise HTTPException(422, "claim_amount cannot exceed the billed invoice amount.")
    # A partial approval preserves the original request but reserves only the
    # approved portion. Legacy excessive requests can also be rejected above.
    requested = claim_amount if claim_status == "Pending" else approved_amount
    if invoice["eligible_amount"] <= 0 or requested > invoice["eligible_amount"]:
        raise HTTPException(422, "The pending claim or approved amount cannot exceed this policy's eligible treatment coverage for the invoice/visit.")
    await cur.execute(
        """SELECT COALESCE(SUM(CASE WHEN status = 'Pending' THEN claim_amount
                                   WHEN status = 'Approved' THEN approved_amount ELSE 0 END), 0) AS reserved,
                  COALESCE(SUM(CASE WHEN policy_id = %s THEN
                                   CASE WHEN status = 'Pending' THEN claim_amount
                                        WHEN status = 'Approved' THEN approved_amount ELSE 0 END
                                   ELSE 0 END), 0) AS policy_reserved
           FROM insurance_claim WHERE invoice_id = %s AND (%s::integer IS NULL OR claim_id <> %s);""",
        (invoice["policy_id"], invoice["invoice_id"], claim_id, claim_id),
    )
    totals = await cur.fetchone()
    if totals["policy_reserved"] + requested > invoice["eligible_amount"]:
        raise HTTPException(409, "Pending and approved claims for this policy exceed its eligible coverage for the invoice/visit.")
    if totals["reserved"] + requested > invoice["billed_amount"]:
        raise HTTPException(409, "Pending and approved claims together cannot exceed the billed invoice amount.")


@router.get("", response_model=List[InsuranceClaimResponse])
async def list_insurance_claims(
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        query = """SELECT c.*, a.patient_id, a.branch_id, a.doctor_id,
                          p.patient_id AS policy_patient_id,
                          p.policy_number, ip.provider_name,
                          pt.first_name || ' ' || pt.last_name AS patient_name
                   FROM insurance_claim c
                   JOIN invoice i ON i.invoice_id = c.invoice_id
                   JOIN appointment a ON a.appointment_id = i.appointment_id
                   JOIN insurance_policy p ON p.policy_id = c.policy_id
                   JOIN insurance_provider ip ON ip.provider_id = p.provider_id
                   JOIN patient pt ON pt.patient_id = a.patient_id"""
        params = []
        if current_user.user_type == "patient":
            query += " WHERE a.patient_id = %s"
            params.append(current_user.patient_id)
        else:
            if current_user.role.lower() not in STAFF_ROLES:
                raise HTTPException(403, "Staff credentials required for this resource.")
            if current_user.role.lower() != "admin":
                check_branch_scope(current_user.branch_id, current_user)
                query += " WHERE a.branch_id = %s"
                params.append(current_user.branch_id)
            if current_user.role.lower() == "doctor":
                if current_user.doctor_id is None:
                    raise HTTPException(403, "A linked doctor profile is required.")
                query += " AND a.doctor_id = %s"
                params.append(current_user.doctor_id)
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
    _validate_amounts(payload.claim_amount, payload.approved_amount, payload.status)
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        invoice = await _validate_references(
            cur, payload.invoice_id, payload.policy_id, rejecting=payload.status == "Rejected"
        )
        check_branch_scope(invoice["branch_id"], current_user)
        await _validate_claim_total(cur, invoice, payload.claim_amount, payload.approved_amount, payload.status)
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
        if (update_data.get("invoice_id", claim["invoice_id"]) != claim["invoice_id"]
                or update_data.get("policy_id", claim["policy_id"]) != claim["policy_id"]):
            raise HTTPException(409, "A filed claim cannot be moved to another invoice or policy.")
        invoice_id = update_data.get("invoice_id", claim["invoice_id"])
        policy_id = update_data.get("policy_id", claim["policy_id"])
        invoice = await _validate_references(
            cur, invoice_id, policy_id, rejecting=update_data.get("status") == "Rejected"
        )
        check_branch_scope(invoice["branch_id"], current_user)
        claim = await _get_claim(cur, claim_id, lock=True)
        _authorize_claim(claim, current_user, write=True)
        claim_amount = update_data.get("claim_amount", claim["claim_amount"])
        approved_amount = update_data.get("approved_amount", claim["approved_amount"])
        claim_status = update_data.get("status", claim["status"])
        _validate_amounts(claim_amount, approved_amount, claim_status)
        await _validate_claim_total(cur, invoice, claim_amount, approved_amount, claim_status, claim_id)
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
        # Match create/update lock order; deletion releases this claim's reservation.
        await cur.execute("SELECT invoice_id FROM invoice WHERE invoice_id = %s FOR UPDATE;", (claim["invoice_id"],))
        claim = await _get_claim(cur, claim_id, lock=True)
        _authorize_claim(claim, current_user, write=True)
        await cur.execute("DELETE FROM insurance_claim WHERE claim_id = %s;", (claim_id,))
    return None
