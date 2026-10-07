from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.api.v1.endpoints._guards import database_mutation
from app.auth.dependencies import get_current_user, require_csrf, require_role
from app.auth.schemas import JWTPayload
from app.core.database import get_db
from app.schemas.treatment_category import (
    TreatmentCategoryCreate,
    TreatmentCategoryResponse,
    TreatmentCategoryUpdate,
)

router = APIRouter(prefix="/treatment-categories", tags=["Treatment Categories"])


@router.get("", response_model=List[TreatmentCategoryResponse])
async def list_treatment_categories(
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT * FROM treatment_category ORDER BY category_name ASC;")
        return [TreatmentCategoryResponse(**row) for row in await cur.fetchall()]


@router.get("/{category_id}", response_model=TreatmentCategoryResponse)
async def get_treatment_category(
    category_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT * FROM treatment_category WHERE category_id = %s;", (category_id,))
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, f"Treatment category {category_id} not found")
    return TreatmentCategoryResponse(**row)


@router.post(
    "",
    response_model=TreatmentCategoryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_treatment_category(
    payload: TreatmentCategoryCreate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin")),
):
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT category_id FROM treatment_category WHERE LOWER(category_name) = LOWER(%s);",
            (payload.category_name,),
        )
        if await cur.fetchone():
            raise HTTPException(409, "A treatment category with this name already exists.")
        await cur.execute(
            """INSERT INTO treatment_category (category_name, description)
               VALUES (%s, %s) RETURNING *;""",
            (payload.category_name, payload.description),
        )
        return TreatmentCategoryResponse(**await cur.fetchone())


@router.put(
    "/{category_id}",
    response_model=TreatmentCategoryResponse,
    dependencies=[Depends(require_csrf)],
)
async def update_treatment_category(
    category_id: int,
    payload: TreatmentCategoryUpdate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin")),
):
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(400, "No update fields provided")
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT category_id FROM treatment_category WHERE category_id = %s;", (category_id,))
        if not await cur.fetchone():
            raise HTTPException(404, f"Treatment category {category_id} not found")
        if "category_name" in update_data:
            await cur.execute(
                """SELECT category_id FROM treatment_category
                   WHERE LOWER(category_name) = LOWER(%s) AND category_id != %s;""",
                (update_data["category_name"], category_id),
            )
            if await cur.fetchone():
                raise HTTPException(409, "A treatment category with this name already exists.")
        clauses = [f"{key} = %s" for key in update_data]
        values = list(update_data.values()) + [category_id]
        await cur.execute(
            f"UPDATE treatment_category SET {', '.join(clauses)} "
            "WHERE category_id = %s RETURNING *;",
            tuple(values),
        )
        return TreatmentCategoryResponse(**await cur.fetchone())


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def delete_treatment_category(
    category_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin")),
):
    async with database_mutation(conn), conn.cursor() as cur:
        await cur.execute("SELECT category_id FROM treatment_category WHERE category_id = %s;", (category_id,))
        if not await cur.fetchone():
            raise HTTPException(404, f"Treatment category {category_id} not found")
        await cur.execute("DELETE FROM treatment_category WHERE category_id = %s;", (category_id,))
    return None
