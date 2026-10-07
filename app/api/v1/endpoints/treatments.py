from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.api.v1.endpoints._guards import database_mutation
from app.auth.dependencies import get_current_user, require_csrf, require_role
from app.auth.schemas import JWTPayload
from app.core.database import get_db
from app.schemas.treatment import TreatmentCreate, TreatmentResponse, TreatmentUpdate

router = APIRouter(prefix="/treatments", tags=["Treatments"])


async def _treatment_query(cur, treatment_id=None):
    query = """
        SELECT t.*, c.category_name
        FROM treatment t
        JOIN treatment_category c ON c.category_id = t.category_id
    """
    if treatment_id is not None:
        query += " WHERE t.treatment_id = %s"
    query += " ORDER BY t.treatment_name ASC;"
    await cur.execute(query, (treatment_id,) if treatment_id is not None else None)


@router.get("", response_model=List[TreatmentResponse])
async def list_treatments(
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await _treatment_query(cur)
        return [TreatmentResponse(**row) for row in await cur.fetchall()]


@router.get("/{treatment_id}", response_model=TreatmentResponse)
async def get_treatment(
    treatment_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await _treatment_query(cur, treatment_id)
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Treatment {treatment_id} not found")
    return TreatmentResponse(**row)
