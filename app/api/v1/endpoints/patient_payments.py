from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection
from psycopg.errors import CheckViolation, ForeignKeyViolation
from psycopg.rows import dict_row

from app.api.v1.endpoints._guards import check_branch_scope, database_mutation
from app.auth.dependencies import get_current_user, require_csrf, require_role
from app.auth.schemas import JWTPayload
from app.core.database import get_db
from app.schemas.patient_payment import PatientPaymentCreate, PatientPaymentResponse

# Patient receipts via sp_record_patient_payment (no overpayment); doctor pay is in payments.py.
router = APIRouter(tags=["Patient Payments"])
RECEIPT_ROLES = ("admin", "branch_manager", "receptionist_cashier")

_ROWS = """
    SELECT pp.payment_id, pp.invoice_id, pp.payment_date, pp.amount, pp.payment_method,
           pp.reference_number, pp.payment_type, pp.received_by,
           s.first_name || ' ' || s.last_name AS received_by_name,
           a.patient_id, p.first_name || ' ' || p.last_name AS patient_name
      FROM patient_payment pp
      JOIN invoice i ON i.invoice_id = pp.invoice_id
      JOIN appointment a ON a.appointment_id = i.appointment_id
      JOIN patient p ON p.patient_id = a.patient_id
      LEFT JOIN staff s ON s.staff_id = pp.received_by
"""


async def _invoice_scope(cur, invoice_id: int, current_user: JWTPayload) -> None:
    await cur.execute(
        """SELECT a.patient_id, a.branch_id FROM invoice i
           JOIN appointment a ON a.appointment_id = i.appointment_id WHERE i.invoice_id = %s;""",
        (invoice_id,),
    )
    invoice = await cur.fetchone()
    if not invoice:
        raise HTTPException(404, f"Invoice {invoice_id} not found")
    if current_user.user_type == "patient":
        if current_user.patient_id != invoice["patient_id"]:
            raise HTTPException(403, "You can only view payments for your own invoices.")
        return
    if current_user.role.lower() not in RECEIPT_ROLES:
        raise HTTPException(403, "You are not authorized to view patient payments.")
    check_branch_scope(invoice["branch_id"], current_user)


@router.get("/patient-payments", response_model=List[PatientPaymentResponse])
async def list_patient_payments(
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*RECEIPT_ROLES)),
):
    query, params = _ROWS, []
    if current_user.role.lower() != "admin":
        query += " WHERE a.branch_id = %s"
        params.append(current_user.branch_id)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(query + " ORDER BY pp.payment_date DESC, pp.payment_id DESC;", params)
        return [PatientPaymentResponse(**row) for row in await cur.fetchall()]


@router.get("/invoices/{invoice_id}/patient-payments", response_model=List[PatientPaymentResponse])
async def list_invoice_patient_payments(
    invoice_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await _invoice_scope(cur, invoice_id, current_user)
        await cur.execute(_ROWS + " WHERE pp.invoice_id = %s ORDER BY pp.payment_id;", (invoice_id,))
        return [PatientPaymentResponse(**row) for row in await cur.fetchall()]


@router.post(
    "/invoices/{invoice_id}/patient-payments",
    response_model=PatientPaymentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def record_patient_payment(
    invoice_id: int,
    payload: PatientPaymentCreate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*RECEIPT_ROLES)),
):
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        await _invoice_scope(cur, invoice_id, current_user)
        try:
            await cur.execute(
                "CALL sp_record_patient_payment(%s, %s, %s, %s, %s);",
                (invoice_id, payload.amount, payload.payment_method,
                 payload.reference_number, current_user.staff_id),
            )
        except (CheckViolation, ForeignKeyViolation) as exc:
            raise HTTPException(409, exc.diag.message_primary or "Payment could not be recorded.") from exc
        await cur.execute(_ROWS + " WHERE pp.invoice_id = %s ORDER BY pp.payment_id DESC LIMIT 1;", (invoice_id,))
        return PatientPaymentResponse(**await cur.fetchone())
