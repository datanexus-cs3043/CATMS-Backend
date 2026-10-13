from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import AsyncConnection
from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
from psycopg.rows import dict_row

from app.api.v1.endpoints._guards import STAFF_ROLES, check_branch_scope, database_mutation
from app.auth.dependencies import get_current_user, require_csrf, require_role, verify_patient_ownership
from app.auth.schemas import JWTPayload
from app.core.database import get_db
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceGenerate,
    InvoiceResponse,
    InvoiceUpdate,
)

router = APIRouter(prefix="/invoices", tags=["Invoices"])
INVOICE_WRITE_ROLES = ("admin", "branch_manager", "receptionist_cashier")

# Columns every invoice response shares, including totals the pages display.
_INVOICE_SELECT = """SELECT i.*, a.patient_id, a.branch_id, a.doctor_id, a.appointment_date,
                  p.first_name || ' ' || p.last_name AS patient_name, d.doctor_name,
                  (i.amount_paid + i.balance) AS total_amount,
                  COALESCE((SELECT SUM(c.approved_amount) FROM insurance_claim c
                            WHERE c.invoice_id = i.invoice_id AND c.status = 'Approved'), 0) AS insurance_covered,
                  COALESCE((SELECT SUM(c.claim_amount) FROM insurance_claim c
                            WHERE c.invoice_id = i.invoice_id AND c.status = 'Pending'), 0) AS insurance_pending
           FROM invoice i
           JOIN appointment a ON a.appointment_id = i.appointment_id
           JOIN patient p ON p.patient_id = a.patient_id
           LEFT JOIN doctor d ON d.doctor_id = a.doctor_id"""


async def _get_invoice(cur, invoice_id: int, *, lock: bool = True) -> dict:
    await cur.execute(
        _INVOICE_SELECT + " WHERE i.invoice_id = %s" + (" FOR UPDATE OF i" if lock else "") + ";",
        (invoice_id,),
    )
    invoice = await cur.fetchone()
    if not invoice:
        raise HTTPException(404, f"Invoice {invoice_id} not found")
    return invoice


def _authorize_invoice(invoice: dict, current_user: JWTPayload, *, write: bool = False) -> None:
    if current_user.user_type == "patient":
        verify_patient_ownership(invoice["patient_id"], current_user)
        if write:
            raise HTTPException(403, "Patients cannot modify invoices.")
        return
    if current_user.role.lower() not in STAFF_ROLES:
        raise HTTPException(403, "Staff credentials required for this resource.")
    check_branch_scope(invoice["branch_id"], current_user)
    if current_user.role.lower() == "doctor" and current_user.doctor_id != invoice["doctor_id"]:
        raise HTTPException(403, "Doctors can only access invoices for their own appointments.")
    if write and current_user.role.lower() not in INVOICE_WRITE_ROLES:
        raise HTTPException(403, "You are not authorized to modify invoices.")


@router.get("", response_model=List[InvoiceResponse])
async def list_invoices(
    appointment_id: Optional[int] = Query(None, gt=0),
    patient_id: Optional[int] = Query(None, gt=0),
    status_filter: Optional[str] = Query(None, alias="status", description="Comma list, e.g. Unpaid,Partially Paid"),
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        query = _INVOICE_SELECT + " WHERE TRUE"
        params = []
        if current_user.user_type == "patient":
            query += " AND a.patient_id = %s"
            params.append(current_user.patient_id)
        else:
            if current_user.role.lower() not in STAFF_ROLES:
                raise HTTPException(403, "Staff credentials required for this resource.")
            if current_user.role.lower() != "admin":
                query += " AND a.branch_id = %s"
                params.append(current_user.branch_id)
                if current_user.role.lower() == "doctor":
                    query += " AND a.doctor_id = %s"
                    params.append(current_user.doctor_id)
        if appointment_id is not None:
            query += " AND i.appointment_id = %s"
            params.append(appointment_id)
        if patient_id is not None:
            query += " AND a.patient_id = %s"
            params.append(patient_id)
        if status_filter:
            query += " AND i.status = ANY(%s)"
            params.append([s.strip() for s in status_filter.split(",") if s.strip()])
        query += " ORDER BY i.invoice_date DESC, i.invoice_id DESC;"
        await cur.execute(query, tuple(params))
        return [InvoiceResponse(**row) for row in await cur.fetchall()]


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        invoice = await _get_invoice(cur, invoice_id, lock=False)
    _authorize_invoice(invoice, current_user)
    return InvoiceResponse(**invoice)


async def _validate_staff(cur, staff_id: int, branch_id: int) -> None:
    await cur.execute(
        "SELECT staff_id FROM staff WHERE staff_id = %s AND branch_id = %s;",
        (staff_id, branch_id),
    )
    if not await cur.fetchone():
        raise HTTPException(422, "Invoice staff must belong to the appointment branch.")


@router.post(
    "",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_invoice(
    payload: InvoiceCreate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*INVOICE_WRITE_ROLES)),
):
    """Compatibility creation uses the same completed-visit billing as /generate."""
    if payload.staff_id != current_user.staff_id:
        raise HTTPException(403, "Issue the invoice using your linked staff profile.")
    if payload.amount_paid != 0 or payload.balance != 0 or payload.status != "Unpaid":
        raise HTTPException(409, "Invoice totals are calculated from recorded treatments. "
                            "Use /invoices/generate, then record payments through the receipt endpoint.")
    return await _generate_invoice(payload.appointment_id, conn, current_user, invoice_date=payload.invoice_date)


@router.post(
    "/generate",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def generate_invoice(
    payload: InvoiceGenerate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*INVOICE_WRITE_ROLES)),
):
    """Create the invoice and its items for a completed visit (sp_generate_invoice)."""
    return await _generate_invoice(payload.appointment_id, conn, current_user)


async def _generate_invoice(appointment_id, conn, current_user, *, invoice_date=None):
    if current_user.staff_id is None:
        raise HTTPException(403, "A linked staff profile is required to issue invoices.")
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT branch_id, status FROM appointment WHERE appointment_id = %s FOR UPDATE;", (appointment_id,)
        )
        appointment = await cur.fetchone()
        if not appointment:
            raise HTTPException(404, f"Appointment {appointment_id} not found")
        check_branch_scope(appointment["branch_id"], current_user)
        if appointment["status"] != "Completed":
            raise HTTPException(409, "Only completed appointments can be invoiced.")
        await _validate_staff(cur, current_user.staff_id, appointment["branch_id"])
        try:
            await cur.execute(
                "CALL sp_generate_invoice(%s, %s, NULL);",
                (appointment_id, current_user.staff_id),
            )
        except (CheckViolation, UniqueViolation, ForeignKeyViolation) as exc:
            # Pass the procedure's own message (e.g. "Record at least one treatment...").
            raise HTTPException(409, exc.diag.message_primary or "Invoice could not be generated.") from exc
        invoice_id = (await cur.fetchone())["p_invoice_id"]
        if invoice_date is not None:
            await cur.execute("UPDATE invoice SET invoice_date = %s WHERE invoice_id = %s;", (invoice_date, invoice_id))
        invoice = await _get_invoice(cur, invoice_id)
    return InvoiceResponse(**invoice)


@router.put(
    "/{invoice_id}",
    response_model=InvoiceResponse,
    dependencies=[Depends(require_csrf)],
)
async def update_invoice(
    invoice_id: int,
    payload: InvoiceUpdate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*INVOICE_WRITE_ROLES)),
):
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(400, "No update fields provided")
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        invoice = await _get_invoice(cur, invoice_id)
        _authorize_invoice(invoice, current_user, write=True)
        if {"amount_paid", "balance", "status"}.intersection(update_data):
            raise HTTPException(409, "Invoice totals and status are derived from billed items and payment receipts; "
                                "they cannot be edited directly.")
        if "invoice_date" in update_data and update_data["invoice_date"] != invoice["invoice_date"]:
            await cur.execute("SELECT claim_id FROM insurance_claim WHERE invoice_id = %s LIMIT 1;", (invoice_id,))
            if await cur.fetchone():
                raise HTTPException(409, "The invoice date cannot change after an insurance claim is filed.")
        if "staff_id" in update_data:
            await _validate_staff(cur, update_data["staff_id"], invoice["branch_id"])
        clauses = [f"{key} = %s" for key in update_data]
        values = list(update_data.values()) + [invoice_id]
        await cur.execute(
            f"UPDATE invoice SET {', '.join(clauses)} WHERE invoice_id = %s;",
            tuple(values),
        )
        invoice = await _get_invoice(cur, invoice_id)
    return InvoiceResponse(**invoice)
