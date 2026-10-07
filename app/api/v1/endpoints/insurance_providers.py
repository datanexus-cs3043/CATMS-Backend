from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.api.v1.endpoints._guards import database_mutation
from app.auth.dependencies import get_current_user, require_csrf, require_role
from app.auth.schemas import JWTPayload
from app.core.database import get_db
from app.schemas.insurance_provider import (
    InsuranceProviderCreate,
    InsuranceProviderResponse,
    InsuranceProviderUpdate,
)

router = APIRouter(prefix="/insurance/providers", tags=["Insurance Providers"])


@router.get("", response_model=List[InsuranceProviderResponse])
async def list_insurance_providers(
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT * FROM insurance_provider ORDER BY provider_name ASC;")
        return [InsuranceProviderResponse(**row) for row in await cur.fetchall()]


@router.get("/{provider_id}", response_model=InsuranceProviderResponse)
async def get_insurance_provider(
    provider_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT * FROM insurance_provider WHERE provider_id = %s;", (provider_id,))
        provider = await cur.fetchone()
    if not provider:
        raise HTTPException(404, f"Insurance provider {provider_id} not found")
    return InsuranceProviderResponse(**provider)


@router.post(
    "",
    response_model=InsuranceProviderResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_insurance_provider(
    payload: InsuranceProviderCreate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin")),
):
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT provider_id FROM insurance_provider WHERE LOWER(provider_name) = LOWER(%s);",
            (payload.provider_name,),
        )
        if await cur.fetchone():
            raise HTTPException(409, "An insurance provider with this name already exists.")
        await cur.execute(
            """INSERT INTO insurance_provider (provider_name, contact_details)
               VALUES (%s, %s) RETURNING *;""",
            (payload.provider_name, payload.contact_details),
        )
        return InsuranceProviderResponse(**await cur.fetchone())


@router.put(
    "/{provider_id}",
    response_model=InsuranceProviderResponse,
    dependencies=[Depends(require_csrf)],
)
async def update_insurance_provider(
    provider_id: int,
    payload: InsuranceProviderUpdate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin")),
):
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(400, "No update fields provided")
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT provider_id FROM insurance_provider WHERE provider_id = %s;", (provider_id,))
        if not await cur.fetchone():
            raise HTTPException(404, f"Insurance provider {provider_id} not found")
        if "provider_name" in update_data:
            await cur.execute(
                """SELECT provider_id FROM insurance_provider
                   WHERE LOWER(provider_name) = LOWER(%s) AND provider_id != %s;""",
                (update_data["provider_name"], provider_id),
            )
            if await cur.fetchone():
                raise HTTPException(409, "An insurance provider with this name already exists.")
        clauses = [f"{key} = %s" for key in update_data]
        values = list(update_data.values()) + [provider_id]
        await cur.execute(
            f"UPDATE insurance_provider SET {', '.join(clauses)} "
            "WHERE provider_id = %s RETURNING *;",
            tuple(values),
        )
        return InsuranceProviderResponse(**await cur.fetchone())


@router.delete(
    "/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def delete_insurance_provider(
    provider_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin")),
):
    async with database_mutation(conn), conn.cursor() as cur:
        await cur.execute("SELECT provider_id FROM insurance_provider WHERE provider_id = %s;", (provider_id,))
        if not await cur.fetchone():
            raise HTTPException(404, f"Insurance provider {provider_id} not found")
        await cur.execute("DELETE FROM insurance_provider WHERE provider_id = %s;", (provider_id,))
    return None
