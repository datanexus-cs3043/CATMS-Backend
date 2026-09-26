from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from psycopg import AsyncConnection

from app.core.database import get_db
from app.schemas.patient import (
    PatientCreate,
    PatientUpdate,
    PatientResponse,
    PatientDetailResponse,
    EmergencyContactCreate,
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


@router.put("/{patient_id}", response_model=PatientResponse)
async def update_patient(
    patient_id: int,
    payload: PatientUpdate,
    conn: AsyncConnection = Depends(get_db),
):
    """Update details of an existing patient."""
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No update fields provided",
        )

    async with conn.cursor() as cur:
        await cur.execute("SELECT patient_id FROM patient WHERE patient_id = %s;", (patient_id,))
        if not await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient with id {patient_id} not found",
            )

        if "branch_id" in update_data:
            await cur.execute("SELECT branch_id FROM branch WHERE branch_id = %s;", (update_data["branch_id"],))
            if not await cur.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Branch with id {update_data['branch_id']} does not exist",
                )

        set_clauses = [f"{key} = %s" for key in update_data.keys()]
        values = list(update_data.values())
        values.append(patient_id)

        update_query = f"""
            UPDATE patient
            SET {', '.join(set_clauses)}
            WHERE patient_id = %s
            RETURNING *;
        """
        await cur.execute(update_query, tuple(values))
        updated_row = await cur.fetchone()
        return PatientResponse(**updated_row)


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient(
    patient_id: int,
    conn: AsyncConnection = Depends(get_db),
):
    """Delete a patient record."""
    async with conn.cursor() as cur:
        await cur.execute("SELECT patient_id FROM patient WHERE patient_id = %s;", (patient_id,))
        if not await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient with id {patient_id} not found",
            )

        await cur.execute("DELETE FROM patient WHERE patient_id = %s;", (patient_id,))
        return None


@router.get("/{patient_id}/emergency-contacts", response_model=List[EmergencyContactResponse])
async def list_emergency_contacts(
    patient_id: int,
    conn: AsyncConnection = Depends(get_db),
):
    """List emergency contacts for a patient."""
    async with conn.cursor() as cur:
        await cur.execute("SELECT patient_id FROM patient WHERE patient_id = %s;", (patient_id,))
        if not await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient with id {patient_id} not found",
            )

        await cur.execute(
            "SELECT * FROM emergency_contact WHERE patient_id = %s ORDER BY emergency_contact_id ASC;",
            (patient_id,),
        )
        rows = await cur.fetchall()
        return [EmergencyContactResponse(**row) for row in rows]


@router.post(
    "/{patient_id}/emergency-contacts",
    response_model=EmergencyContactResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_emergency_contact(
    patient_id: int,
    payload: EmergencyContactCreate,
    conn: AsyncConnection = Depends(get_db),
):
    """Add a new emergency contact for a patient."""
    async with conn.cursor() as cur:
        await cur.execute("SELECT patient_id FROM patient WHERE patient_id = %s;", (patient_id,))
        if not await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient with id {patient_id} not found",
            )

        insert_query = """
            INSERT INTO emergency_contact (patient_id, contact_name, relationship, phone)
            VALUES (%s, %s, %s, %s)
            RETURNING *;
        """
        await cur.execute(
            insert_query,
            (patient_id, payload.contact_name, payload.relationship, payload.phone),
        )
        new_contact = await cur.fetchone()
        return EmergencyContactResponse(**new_contact)





