from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.api.v1.endpoints._guards import STAFF_ROLES, check_branch_scope, database_mutation
from app.auth.dependencies import get_current_user, require_csrf, require_role, verify_patient_ownership
from app.auth.schemas import JWTPayload
from app.core.database import get_db
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceResponse,
    InvoiceUpdate,
)

router = APIRouter(prefix="/invoices", tags=["Invoices"])
INVOICE_WRITE_ROLES = ("admin", "branch_manager", "receptionist_cashier")


async def _get_invoice(cur, invoice_id: int) -> dict:
    await cur.execute(
        """SELECT i.*, a.patient_id, a.branch_id, a.doctor_id, a.appointment_date,
                  p.first_name || ' ' || p.last_name AS patient_name,
                  d.doctor_name
           FROM invoice i
           JOIN appointment a ON a.appointment_id = i.appointment_id
           JOIN patient p ON p.patient_id = a.patient_id
           LEFT JOIN doctor d ON d.doctor_id = a.doctor_id
           WHERE i.invoice_id = %s FOR UPDATE OF i;""",
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
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        query = """SELECT i.*, a.patient_id, a.branch_id, a.doctor_id, a.appointment_date,
                          p.first_name || ' ' || p.last_name AS patient_name,
                          d.doctor_name
                   FROM invoice i
                   JOIN appointment a ON a.appointment_id = i.appointment_id
                   JOIN patient p ON p.patient_id = a.patient_id
                   LEFT JOIN doctor d ON d.doctor_id = a.doctor_id"""
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
                if current_user.role.lower() == "doctor":
                    query += " AND a.doctor_id = %s"
                    params.append(current_user.doctor_id)
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
        invoice = await _get_invoice(cur, invoice_id)
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
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT appointment_id, patient_id, branch_id FROM appointment "
            "WHERE appointment_id = %s FOR UPDATE;",
            (payload.appointment_id,),
        )
        appointment = await cur.fetchone()
        if not appointment:
            raise HTTPException(404, f"Appointment {payload.appointment_id} not found")
        check_branch_scope(appointment["branch_id"], current_user)
        await _validate_staff(cur, payload.staff_id, appointment["branch_id"])
        await cur.execute(
            "INSERT INTO invoice (appointment_id, staff_id, invoice_date, amount_paid, balance, status) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING invoice_id;",
            (payload.appointment_id, payload.staff_id, payload.invoice_date,
             payload.amount_paid, payload.balance, payload.status),
        )
        invoice_id = (await cur.fetchone())["invoice_id"]
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
