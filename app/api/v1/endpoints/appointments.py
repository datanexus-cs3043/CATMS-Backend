from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from psycopg import AsyncConnection

from app.core.database import get_db
from app.schemas.appointment import (
    AppointmentResponse,
    AppointmentDetailResponse,
    ConsultationNoteResponse,
)

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


@router.get("/{appointment_id}", response_model=AppointmentDetailResponse)
async def get_appointment(
    appointment_id: int,
    conn: AsyncConnection = Depends(get_db),
):
    """Retrieve full appointment details including doctor, patient, treatment, and consultation notes."""
    async with conn.cursor() as cur:
        query = """
            SELECT 
                a.*,
                p.first_name || ' ' || p.last_name AS patient_name,
                d.doctor_name,
                b.branch_name,
                t.treatment_name
            FROM appointment a
            JOIN patient p ON a.patient_id = p.patient_id
            JOIN doctor d ON a.doctor_id = d.doctor_id
            JOIN branch b ON a.branch_id = b.branch_id
            LEFT JOIN treatment t ON a.treatment_id = t.treatment_id
            WHERE a.appointment_id = %s;
        """
        await cur.execute(query, (appointment_id,))
        appt = await cur.fetchone()
        if not appt:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Appointment with id {appointment_id} not found",
            )

        await cur.execute(
            "SELECT * FROM consultation_note WHERE appointment_id = %s ORDER BY created_at ASC;",
            (appointment_id,),
        )
        notes = await cur.fetchall()

        appt_data = dict(appt)
        appt_data["consultation_notes"] = [ConsultationNoteResponse(**n) for n in notes]
        return AppointmentDetailResponse(**appt_data)

