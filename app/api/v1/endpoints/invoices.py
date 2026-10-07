from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.api.v1.endpoints._guards import STAFF_ROLES, check_branch_scope, database_mutation
from app.auth.dependencies import get_current_user, require_csrf, require_role, verify_patient_ownership
from app.auth.schemas import JWTPayload
from app.core.database import get_db
from app.schemas.invoice import InvoiceCreate, InvoiceResponse, InvoiceUpdate

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
           WHERE i.invoice_id = %s FOR UPDATE;""",
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
    if write and current_user.role.lower() not in INVOICE_WRITE_ROLES:
        raise HTTPException(403, "You are not authorized to modify invoices.")


@router.get("", response_model=List[InvoiceResponse])
async def list_invoices(
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        query = """SELECT i.*, a.patient_id, a.branch_id, a.appointment_date,
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
