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


@router.post(
    "",
    response_model=TreatmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_treatment(
    payload: TreatmentCreate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin")),
):
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT category_id FROM treatment_category WHERE category_id = %s;",
            (payload.category_id,),
        )
        if not await cur.fetchone():
            raise HTTPException(422, f"Treatment category {payload.category_id} not found")
        await cur.execute(
            "SELECT treatment_id FROM treatment WHERE LOWER(service_code) = LOWER(%s);",
            (payload.service_code,),
        )
        if await cur.fetchone():
            raise HTTPException(409, "A treatment with this service code already exists.")
        await cur.execute(
            """INSERT INTO treatment
               (category_id, service_code, treatment_name, standard_price)
               VALUES (%s, %s, %s, %s) RETURNING treatment_id;""",
            (payload.category_id, payload.service_code, payload.treatment_name, payload.standard_price),
        )
        treatment_id = (await cur.fetchone())["treatment_id"]
        await _treatment_query(cur, treatment_id)
        return TreatmentResponse(**await cur.fetchone())


@router.put(
    "/{treatment_id}",
    response_model=TreatmentResponse,
    dependencies=[Depends(require_csrf)],
)
async def update_treatment(
    treatment_id: int,
    payload: TreatmentUpdate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin")),
):
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(400, "No update fields provided")
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT treatment_id FROM treatment WHERE treatment_id = %s;", (treatment_id,))
        if not await cur.fetchone():
            raise HTTPException(404, f"Treatment {treatment_id} not found")
        if "category_id" in update_data:
            await cur.execute(
                "SELECT category_id FROM treatment_category WHERE category_id = %s;",
                (update_data["category_id"],),
            )
            if not await cur.fetchone():
                raise HTTPException(422, f"Treatment category {update_data['category_id']} not found")
        if "service_code" in update_data:
            await cur.execute(
                """SELECT treatment_id FROM treatment
                   WHERE LOWER(service_code) = LOWER(%s) AND treatment_id != %s;""",
                (update_data["service_code"], treatment_id),
            )
            if await cur.fetchone():
                raise HTTPException(409, "A treatment with this service code already exists.")
        clauses = [f"{key} = %s" for key in update_data]
        values = list(update_data.values()) + [treatment_id]
        await cur.execute(
            f"UPDATE treatment SET {', '.join(clauses)} WHERE treatment_id = %s;",
            tuple(values),
        )
        await _treatment_query(cur, treatment_id)
        return TreatmentResponse(**await cur.fetchone())


@router.delete(
    "/{treatment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def delete_treatment(
    treatment_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin")),
):
    async with database_mutation(conn), conn.cursor() as cur:
        await cur.execute("SELECT treatment_id FROM treatment WHERE treatment_id = %s;", (treatment_id,))
        if not await cur.fetchone():
            raise HTTPException(404, f"Treatment {treatment_id} not found")
        await cur.execute("DELETE FROM treatment WHERE treatment_id = %s;", (treatment_id,))
    return None
