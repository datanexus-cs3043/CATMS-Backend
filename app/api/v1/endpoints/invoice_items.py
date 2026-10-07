from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.api.v1.endpoints._guards import database_mutation
from app.api.v1.endpoints.invoices import (
    INVOICE_WRITE_ROLES,
    _authorize_invoice,
    _get_invoice,
)
from app.auth.dependencies import get_current_user, require_csrf, require_role
from app.auth.schemas import JWTPayload
from app.core.database import get_db
from app.schemas.invoice import (
    InvoiceItemCreate,
    InvoiceItemResponse,
    InvoiceItemUpdate,
)

router = APIRouter(prefix="/invoices", tags=["Invoice Items"])


async def _get_item(cur, invoice_id: int, item_id: int) -> dict:
    await cur.execute(
        """SELECT ii.*, t.treatment_name
           FROM invoice_item ii JOIN treatment t ON t.treatment_id = ii.treatment_id
           WHERE ii.invoice_id = %s AND ii.invoice_item_id = %s FOR UPDATE;""",
        (invoice_id, item_id),
    )
    item = await cur.fetchone()
    if not item:
        raise HTTPException(404, f"Invoice item {item_id} not found for invoice {invoice_id}")
    return item


async def _validate_treatment(cur, treatment_id: int) -> None:
    await cur.execute("SELECT treatment_id FROM treatment WHERE treatment_id = %s;", (treatment_id,))
    if not await cur.fetchone():
        raise HTTPException(422, f"Treatment {treatment_id} not found")


@router.get("/{invoice_id}/items", response_model=List[InvoiceItemResponse])
async def list_invoice_items(
    invoice_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        invoice = await _get_invoice(cur, invoice_id)
        _authorize_invoice(invoice, current_user)
        await cur.execute(
            """SELECT ii.*, t.treatment_name
               FROM invoice_item ii JOIN treatment t ON t.treatment_id = ii.treatment_id
               WHERE ii.invoice_id = %s ORDER BY ii.invoice_item_id;""",
            (invoice_id,),
        )
        return [InvoiceItemResponse(**row) for row in await cur.fetchall()]


@router.post(
    "/{invoice_id}/items",
    response_model=InvoiceItemResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_invoice_item(
    invoice_id: int,
    payload: InvoiceItemCreate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*INVOICE_WRITE_ROLES)),
):
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        invoice = await _get_invoice(cur, invoice_id)
        _authorize_invoice(invoice, current_user, write=True)
        await _validate_treatment(cur, payload.treatment_id)
        await cur.execute(
            """INSERT INTO invoice_item
               (invoice_id, treatment_id, quantity, unitprice, description)
               VALUES (%s, %s, %s, %s, %s) RETURNING invoice_item_id;""",
            (invoice_id, payload.treatment_id, payload.quantity,
             payload.unitprice, payload.description),
        )
        item_id = (await cur.fetchone())["invoice_item_id"]
        item = await _get_item(cur, invoice_id, item_id)
    return InvoiceItemResponse(**item)


@router.put(
    "/{invoice_id}/items/{item_id}",
    response_model=InvoiceItemResponse,
    dependencies=[Depends(require_csrf)],
)
async def update_invoice_item(
    invoice_id: int,
    item_id: int,
    payload: InvoiceItemUpdate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*INVOICE_WRITE_ROLES)),
):
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(400, "No update fields provided")
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        invoice = await _get_invoice(cur, invoice_id)
        _authorize_invoice(invoice, current_user, write=True)
        await _get_item(cur, invoice_id, item_id)
        if "treatment_id" in update_data:
            await _validate_treatment(cur, update_data["treatment_id"])
        clauses = [f"{key} = %s" for key in update_data]
        values = list(update_data.values()) + [invoice_id, item_id]
        await cur.execute(
            f"UPDATE invoice_item SET {', '.join(clauses)} "
            "WHERE invoice_id = %s AND invoice_item_id = %s;",
            tuple(values),
        )
        item = await _get_item(cur, invoice_id, item_id)
    return InvoiceItemResponse(**item)


@router.delete(
    "/{invoice_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def delete_invoice_item(
    invoice_id: int,
    item_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*INVOICE_WRITE_ROLES)),
):
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        invoice = await _get_invoice(cur, invoice_id)
        _authorize_invoice(invoice, current_user, write=True)
        await _get_item(cur, invoice_id, item_id)
        await cur.execute(
            "DELETE FROM invoice_item WHERE invoice_id = %s AND invoice_item_id = %s;",
            (invoice_id, item_id),
        )
    return None
