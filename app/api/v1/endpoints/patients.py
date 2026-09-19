from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from psycopg import AsyncConnection

from app.core.database import get_db
from app.schemas.patient import (
    PatientCreate,
    PatientResponse,
    PatientDetailResponse,
    EmergencyContactResponse,
)

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


@router.get("/{patient_id}", response_model=PatientDetailResponse)
async def get_patient(
    patient_id: int,
    conn: AsyncConnection = Depends(get_db),
):
    """Retrieve full patient details including branch and emergency contacts."""
    async with conn.cursor() as cur:
        query = """
            SELECT p.*, b.branch_name
            FROM patient p
            LEFT JOIN branch b ON p.branch_id = b.branch_id
            WHERE p.patient_id = %s;
        """
        await cur.execute(query, (patient_id,))
        patient = await cur.fetchone()
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient with id {patient_id} not found",
            )

        await cur.execute(
            "SELECT * FROM emergency_contact WHERE patient_id = %s ORDER BY emergency_contact_id ASC;",
            (patient_id,),
        )
        contacts = await cur.fetchall()

        patient_data = dict(patient)
        patient_data["emergency_contacts"] = [EmergencyContactResponse(**c) for c in contacts]
        return PatientDetailResponse(**patient_data)


@router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
async def create_patient(
    payload: PatientCreate,
    conn: AsyncConnection = Depends(get_db),
):
    """Register a new patient into the system."""
    async with conn.cursor() as cur:
        await cur.execute("SELECT branch_id FROM branch WHERE branch_id = %s;", (payload.branch_id,))
        if not await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Branch with id {payload.branch_id} does not exist",
            )

        insert_query = """
            INSERT INTO patient (
                branch_id, first_name, last_name, date_of_birth, gender,
                patient_type, contact_details, email, address
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *;
        """
        await cur.execute(
            insert_query,
            (
                payload.branch_id,
                payload.first_name,
                payload.last_name,
                payload.date_of_birth,
                payload.gender,
                payload.patient_type,
                payload.contact_details,
                payload.email,
                payload.address,
            ),
        )
        new_patient = await cur.fetchone()
        return PatientResponse(**new_patient)


