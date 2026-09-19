from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from psycopg import AsyncConnection

from app.core.database import get_db
from app.schemas.appointment import AppointmentResponse

router = APIRouter(prefix="/appointments", tags=["Appointments"])


@router.get("", response_model=List[AppointmentResponse])
async def list_appointments(
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    doctor_id: Optional[int] = Query(None, description="Filter by doctor ID"),
    patient_id: Optional[int] = Query(None, description="Filter by patient ID"),
    branch_id: Optional[int] = Query(None, description="Filter by branch ID"),
    appointment_date: Optional[date] = Query(None, description="Filter by appointment date"),
    conn: AsyncConnection = Depends(get_db),
):
    """List appointments with optional filtering by doctor, patient, branch, or date."""
    query = "SELECT * FROM appointment WHERE 1=1"
    params = []

    if doctor_id is not None:
        query += " AND doctor_id = %s"
        params.append(doctor_id)

    if patient_id is not None:
        query += " AND patient_id = %s"
        params.append(patient_id)

    if branch_id is not None:
        query += " AND branch_id = %s"
        params.append(branch_id)

    if appointment_date is not None:
        query += " AND appointment_date = %s"
        params.append(appointment_date)

    query += " ORDER BY appointment_date DESC, start_time DESC LIMIT %s OFFSET %s;"
    params.extend([limit, skip])

    async with conn.cursor() as cur:
        await cur.execute(query, tuple(params))
        rows = await cur.fetchall()
        return [AppointmentResponse(**row) for row in rows]
