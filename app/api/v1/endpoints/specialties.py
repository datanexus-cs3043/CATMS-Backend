from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.core.database import get_db
from app.auth.dependencies import get_current_user, require_role, require_csrf
from app.auth.schemas import JWTPayload
from app.schemas.doctor import SpecialtyCreate, SpecialtyUpdate, SpecialtyResponse

router = APIRouter(prefix="/specialties", tags=["Specialties"])


# =========================================================================
# GET /api/specialties — List all specialties (any authenticated user)
# =========================================================================
@router.get("", response_model=List[SpecialtyResponse], summary="List all specialties")
async def list_specialties(
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT * FROM specialty ORDER BY specialty_name ASC;")
        rows = await cur.fetchall()
        return [SpecialtyResponse(**r) for r in rows]


# =========================================================================
# GET /api/specialties/{specialty_id} — Get specialty by ID
# =========================================================================
@router.get("/{specialty_id}", response_model=SpecialtyResponse, summary="Get specialty by ID")
async def get_specialty(
    specialty_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT * FROM specialty WHERE specialty_id = %s;", (specialty_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Specialty {specialty_id} not found")
        return SpecialtyResponse(**row)


# =========================================================================
# POST /api/specialties — Create specialty (Admin only + CSRF)
# =========================================================================
@router.post(
    "",
    response_model=SpecialtyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create specialty",
    dependencies=[Depends(require_csrf)],
)
async def create_specialty(
    payload: SpecialtyCreate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin")),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT specialty_id FROM specialty WHERE LOWER(specialty_name) = LOWER(%s);",
            (payload.specialty_name.strip(),),
        )
        if await cur.fetchone():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=f"Specialty '{payload.specialty_name}' already exists")
        await cur.execute(
            "INSERT INTO specialty (specialty_name, description) VALUES (%s, %s) RETURNING *;",
            (payload.specialty_name.strip(), payload.description),
        )
        return SpecialtyResponse(**await cur.fetchone())


# =========================================================================
# PUT /api/specialties/{specialty_id} — Update specialty (Admin only + CSRF)
# =========================================================================
@router.put(
    "/{specialty_id}",
    response_model=SpecialtyResponse,
    summary="Update specialty",
    dependencies=[Depends(require_csrf)],
)
async def update_specialty(
    specialty_id: int,
    payload: SpecialtyUpdate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin")),
):
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No update fields provided")
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT specialty_id FROM specialty WHERE specialty_id = %s;", (specialty_id,))
        if not await cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Specialty {specialty_id} not found")
        set_clauses = [f"{k} = %s" for k in update_data]
        values = list(update_data.values()) + [specialty_id]
        await cur.execute(
            f"UPDATE specialty SET {', '.join(set_clauses)} WHERE specialty_id = %s RETURNING *;",
            tuple(values),
        )
        return SpecialtyResponse(**await cur.fetchone())


# =========================================================================
# DELETE /api/specialties/{specialty_id} — Delete specialty (Admin only + CSRF)
# =========================================================================
@router.delete(
    "/{specialty_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete specialty",
    dependencies=[Depends(require_csrf)],
)
async def delete_specialty(
    specialty_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin")),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT specialty_id FROM specialty WHERE specialty_id = %s;", (specialty_id,))
        if not await cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Specialty {specialty_id} not found")
        # Unlink from all doctors first
        await cur.execute("DELETE FROM doctor_specialty WHERE specialty_id = %s;", (specialty_id,))
        await cur.execute("DELETE FROM specialty WHERE specialty_id = %s;", (specialty_id,))
    return None

