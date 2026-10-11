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


async def _reject_issued_item_change(
    cur, invoice_id: int, current_user: JWTPayload, *, item_id: int | None = None
) -> None:
    # Every persisted invoice is issued: both creation routes generate its items
    # from the completed visit. Unpaid is a payment state, not an editable draft.
    # Keep the invoice lock and scope checks used by other financial mutations.
    invoice = await _get_invoice(cur, invoice_id)
    _authorize_invoice(invoice, current_user, write=True)
    if item_id is not None:
        await _get_item(cur, invoice_id, item_id)
    raise HTTPException(
        status.HTTP_409_CONFLICT,
        "Issued invoice items cannot be changed. Record treatments before generating "
        "the invoice; billing corrections require an explicitly authorized adjustment workflow.",
    )


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
        await _reject_issued_item_change(cur, invoice_id, current_user)


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
    if not payload.model_dump(exclude_unset=True):
        raise HTTPException(400, "No update fields provided")
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        await _reject_issued_item_change(cur, invoice_id, current_user, item_id=item_id)


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
        await _reject_issued_item_change(cur, invoice_id, current_user, item_id=item_id)
