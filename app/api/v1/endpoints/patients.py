from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from psycopg import AsyncConnection

from app.core.database import get_db
from app.schemas.patient import PatientResponse

router = APIRouter(prefix="/patients", tags=["Patients"])


@router.get("", response_model=List[PatientResponse])
async def list_patients(
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    search: Optional[str] = Query(None, description="Search by patient name or email"),
    branch_id: Optional[int] = Query(None, description="Filter by branch ID"),
    conn: AsyncConnection = Depends(get_db),
):
    """Retrieve a paginated list of registered patients with optional filtering."""
    query = "SELECT * FROM patient WHERE 1=1"
    params = []

    if branch_id is not None:
        query += " AND branch_id = %s"
        params.append(branch_id)

    if search:
        query += " AND (first_name ILIKE %s OR last_name ILIKE %s OR email ILIKE %s)"
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern, search_pattern])

    query += " ORDER BY patient_id DESC LIMIT %s OFFSET %s;"
    params.extend([limit, skip])

    async with conn.cursor() as cur:
        await cur.execute(query, tuple(params))
        rows = await cur.fetchall()
        return [PatientResponse(**row) for row in rows]
