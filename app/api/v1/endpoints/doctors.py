from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from psycopg import AsyncConnection

from app.core.database import get_db
from app.schemas.doctor import DoctorResponse, DoctorDetailResponse, SpecialtyResponse

router = APIRouter(prefix="/doctors", tags=["Doctors"])


@router.get("", response_model=List[DoctorResponse])
async def list_doctors(
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    search: Optional[str] = Query(None, description="Search doctor name or license number"),
    branch_id: Optional[int] = Query(None, description="Filter doctors by branch ID"),
    conn: AsyncConnection = Depends(get_db),
):
    """Retrieve list of registered doctors with optional search and branch filtering."""
    query = """
        SELECT d.*
        FROM doctor d
        JOIN staff s ON d.staff_id = s.staff_id
        WHERE 1=1
    """
    params = []

    if branch_id is not None:
        query += " AND s.branch_id = %s"
        params.append(branch_id)

    if search:
        query += " AND (d.doctor_name ILIKE %s OR d.doctor_license_number ILIKE %s)"
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern])

    query += " ORDER BY d.doctor_id ASC LIMIT %s OFFSET %s;"
    params.extend([limit, skip])

    async with conn.cursor() as cur:
        await cur.execute(query, tuple(params))
        rows = await cur.fetchall()
        return [DoctorResponse(**row) for row in rows]


@router.get("/{doctor_id}", response_model=DoctorDetailResponse)
async def get_doctor(
    doctor_id: int,
    conn: AsyncConnection = Depends(get_db),
):
    """Retrieve full doctor profile including assigned specialties and branch."""
    async with conn.cursor() as cur:
        query = """
            SELECT d.*, s.branch_id, b.branch_name, s.email, s.contact_details
            FROM doctor d
            JOIN staff s ON d.staff_id = s.staff_id
            LEFT JOIN branch b ON s.branch_id = b.branch_id
            WHERE d.doctor_id = %s;
        """
        await cur.execute(query, (doctor_id,))
        doctor = await cur.fetchone()
        if not doctor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Doctor with id {doctor_id} not found",
            )

        spec_query = """
            SELECT sp.*
            FROM specialty sp
            JOIN doctor_specialty ds ON sp.specialty_id = ds.specialty_id
            WHERE ds.doctor_id = %s;
        """
        await cur.execute(spec_query, (doctor_id,))
        specialties = await cur.fetchall()

        doctor_data = dict(doctor)
        doctor_data["specialties"] = [SpecialtyResponse(**sp) for sp in specialties]
        return DoctorDetailResponse(**doctor_data)

