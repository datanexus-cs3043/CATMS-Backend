from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.api.v1.endpoints._guards import STAFF_ROLES, check_branch_scope, database_mutation
from app.auth.dependencies import get_current_user, require_csrf, require_role
from app.auth.schemas import JWTPayload
from app.core.database import get_db
from app.schemas.payment import PaymentCreate, PaymentResponse, PaymentUpdate

router = APIRouter(tags=["Doctor Payments"])
PAYMENT_WRITE_ROLES = ("admin", "branch_manager", "receptionist_cashier")


async def _get_invoice_for_payment(cur, invoice_id: int) -> dict:
    await cur.execute(
        """SELECT i.invoice_id, a.appointment_id, a.patient_id, a.branch_id
           FROM invoice i JOIN appointment a ON a.appointment_id = i.appointment_id
           WHERE i.invoice_id = %s FOR UPDATE;""",
        (invoice_id,),
    )
    invoice = await cur.fetchone()
    if not invoice:
        raise HTTPException(404, f"Invoice {invoice_id} not found")
    return invoice


def _authorize_payment_resource(
    invoice: dict, current_user: JWTPayload, *, write: bool = False, doctor_id: int | None = None
) -> None:
    if current_user.user_type != "staff" or current_user.role.lower() not in STAFF_ROLES:
        raise HTTPException(403, "Staff credentials required for this resource.")
    check_branch_scope(invoice["branch_id"], current_user)
    if write and current_user.role.lower() not in PAYMENT_WRITE_ROLES:
        raise HTTPException(403, "You are not authorized to modify payments.")
    if current_user.role.lower() == "doctor":
        if current_user.doctor_id is None or (
            doctor_id is not None and doctor_id != current_user.doctor_id
        ):
            raise HTTPException(403, "Doctors can only access their own compensation.")


async def _payment_query(cur, payment_id=None, invoice_id=None, doctor_id=None) -> None:
    query = """SELECT dp.doctor_payment_id AS payment_id, dp.doctor_id,
                      dp.appointment_id, dp.invoice_item_id, dp.date, dp.time,
                      dp.doctor_payment AS amount
               FROM doctor_payment dp
               JOIN appointment a ON a.appointment_id = dp.appointment_id
               JOIN invoice i ON i.appointment_id = a.appointment_id"""
    params = []
    if payment_id is not None:
        query += " WHERE dp.doctor_payment_id = %s"
        params.append(payment_id)
    elif invoice_id is not None:
        query += " WHERE i.invoice_id = %s"
        params.append(invoice_id)
    if doctor_id is not None:
        query += " AND dp.doctor_id = %s" if params else " WHERE dp.doctor_id = %s"
        params.append(doctor_id)
    query += " ORDER BY dp.date DESC, dp.time DESC, dp.doctor_payment_id DESC"
    if payment_id is not None:
        query += " FOR UPDATE OF dp"
    query += ";"
    await cur.execute(query, tuple(params))


@router.get("/invoices/{invoice_id}/payments", response_model=List[PaymentResponse])
async def list_invoice_payments(
    invoice_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    """List doctor compensation linked to an invoice, not patient receipts."""
    async with conn.cursor(row_factory=dict_row) as cur:
        invoice = await _get_invoice_for_payment(cur, invoice_id)
        _authorize_payment_resource(invoice, current_user)
        doctor_id = current_user.doctor_id if current_user.role.lower() == "doctor" else None
        await _payment_query(cur, invoice_id=invoice_id, doctor_id=doctor_id)
        return [PaymentResponse(**row) for row in await cur.fetchall()]


async def _get_payment(cur, payment_id: int) -> dict:
    await _payment_query(cur, payment_id=payment_id)
    payment = await cur.fetchone()
    if not payment:
        raise HTTPException(404, f"Payment {payment_id} not found")
    await cur.execute(
        """SELECT i.invoice_id, a.appointment_id, a.patient_id, a.branch_id
           FROM invoice i JOIN appointment a ON a.appointment_id = i.appointment_id
           WHERE a.appointment_id = %s;""",
        (payment["appointment_id"],),
    )
    invoice = await cur.fetchone()
    if not invoice:
        raise HTTPException(404, "The payment is not linked to an invoice.")
    return {**payment, "_invoice": invoice}


@router.get("/payments/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    """Retrieve a doctor compensation record; the payment URL is a legacy alias."""
    async with conn.cursor(row_factory=dict_row) as cur:
        payment = await _get_payment(cur, payment_id)
    _authorize_payment_resource(payment["_invoice"], current_user, doctor_id=payment["doctor_id"])
    payment.pop("_invoice")
    return PaymentResponse(**payment)


async def _validate_payment_links(cur, invoice: dict, payload: dict) -> None:
    if payload["appointment_id"] != invoice["appointment_id"]:
        raise HTTPException(422, "Payment appointment must match the invoice appointment.")
    await cur.execute(
        """SELECT d.doctor_id
           FROM doctor d JOIN staff s ON s.staff_id = d.staff_id
           WHERE d.doctor_id = %s AND s.branch_id = %s;""",
        (payload["doctor_id"], invoice["branch_id"]),
    )
    if not await cur.fetchone():
        raise HTTPException(422, "Payment doctor must belong to the invoice branch.")
    if payload.get("invoice_item_id") is not None:
        await cur.execute(
            "SELECT invoice_item_id FROM invoice_item WHERE invoice_item_id = %s AND invoice_id = %s;",
            (payload["invoice_item_id"], invoice["invoice_id"]),
        )
        if not await cur.fetchone():
            raise HTTPException(422, "Payment invoice item must belong to the invoice.")


@router.post(
    "/invoices/{invoice_id}/payments",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_invoice_payment(
    invoice_id: int,
    payload: PaymentCreate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*PAYMENT_WRITE_ROLES)),
):
    """Record doctor compensation. This does not record a patient receipt or settle an invoice."""
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        invoice = await _get_invoice_for_payment(cur, invoice_id)
        _authorize_payment_resource(invoice, current_user, write=True)
        values = payload.model_dump()
        await _validate_payment_links(cur, invoice, values)
        await cur.execute(
            """INSERT INTO doctor_payment
               (doctor_id, appointment_id, invoice_item_id, date, time, doctor_payment)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING doctor_payment_id;""",
            (values["doctor_id"], values["appointment_id"], values["invoice_item_id"],
             values["date"], values["time"], values["amount"]),
        )
        payment_id = (await cur.fetchone())["doctor_payment_id"]
        payment = await _get_payment(cur, payment_id)
    payment.pop("_invoice")
    return PaymentResponse(**payment)


@router.put(
    "/payments/{payment_id}",
    response_model=PaymentResponse,
    dependencies=[Depends(require_csrf)],
)
async def update_payment(
    payment_id: int,
    payload: PaymentUpdate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*PAYMENT_WRITE_ROLES)),
):
    """Update doctor compensation without changing patient payment totals."""
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(400, "No update fields provided")
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        payment = await _get_payment(cur, payment_id)
        invoice = payment["_invoice"]
        _authorize_payment_resource(invoice, current_user, write=True)
        merged = {
            key: update_data.get(key, payment[key])
            for key in ("doctor_id", "appointment_id", "invoice_item_id")
        }
        await _validate_payment_links(cur, invoice, merged)
        column_map = {"amount": "doctor_payment"}
        clauses = [f"{column_map.get(key, key)} = %s" for key in update_data]
        values = [value for value in update_data.values()] + [payment_id]
        await cur.execute(
            f"UPDATE doctor_payment SET {', '.join(clauses)} "
            "WHERE doctor_payment_id = %s;",
            tuple(values),
        )
        payment = await _get_payment(cur, payment_id)
    payment.pop("_invoice")
    return PaymentResponse(**payment)
