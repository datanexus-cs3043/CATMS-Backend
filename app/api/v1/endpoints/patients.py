from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.core.database import get_db
from app.auth.dependencies import get_current_user, verify_patient_ownership, require_csrf
from app.auth.schemas import JWTPayload
from app.schemas.appointment import AppointmentDetailResponse
from app.schemas.patient import (
    PatientCreate,
    PatientUpdate,
    PatientResponse,
    PatientDetailResponse,
    EmergencyContactCreate,
    EmergencyContactUpdate,
    EmergencyContactResponse,
    PatientInvoiceResponse,
    PatientInsurancePolicyResponse,
    PatientInsuranceCoverageResponse,
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

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(query, tuple(params))
        rows = await cur.fetchall()
        return [PatientResponse(**row) for row in rows]


@router.get("/{patient_id}", response_model=PatientDetailResponse)
async def get_patient(
    patient_id: int,
    conn: AsyncConnection = Depends(get_db),
):
    """Retrieve full patient details including branch and emergency contacts."""
    async with conn.cursor(row_factory=dict_row) as cur:
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
    async with conn.cursor(row_factory=dict_row) as cur:
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

    async with conn.cursor(row_factory=dict_row) as cur:
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
    async with conn.cursor(row_factory=dict_row) as cur:
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
    async with conn.cursor(row_factory=dict_row) as cur:
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
    async with conn.cursor(row_factory=dict_row) as cur:
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


# =========================================================================
# 1. GET /api/patients/{patient_id}/appointments
# =========================================================================
@router.get(
    "/{patient_id}/appointments",
    response_model=List[AppointmentDetailResponse],
    summary="Get patient appointments",
    description="Retrieves all appointment records for a specific patient. Enforces patient ownership authorization.",
)
async def get_patient_appointments(
    patient_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    # Verify authorization (Staff can view, Patient can only view their own)
    verify_patient_ownership(patient_id, current_user)

    async with conn.cursor(row_factory=dict_row) as cur:
        # Check patient exists
        await cur.execute("SELECT patient_id FROM patient WHERE patient_id = %s;", (patient_id,))
        if not await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient with id {patient_id} not found",
            )

        query = """
            SELECT 
                a.*,
                (p.first_name || ' ' || p.last_name) AS patient_name,
                d.doctor_name,
                b.branch_name,
                t.treatment_name
            FROM appointment a
            JOIN patient p ON a.patient_id = p.patient_id
            JOIN doctor d ON a.doctor_id = d.doctor_id
            JOIN branch b ON a.branch_id = b.branch_id
            LEFT JOIN treatment t ON a.treatment_id = t.treatment_id
            WHERE a.patient_id = %s
            ORDER BY a.appointment_date DESC, a.start_time DESC;
        """
        await cur.execute(query, (patient_id,))
        rows = await cur.fetchall()
        return [AppointmentDetailResponse(**row) for row in rows]


# =========================================================================
# 2. GET /api/patients/{patient_id}/invoices
# =========================================================================
@router.get(
    "/{patient_id}/invoices",
    response_model=List[PatientInvoiceResponse],
    summary="Get patient invoices",
    description="Retrieves all invoices for appointments belonging to a patient.",
)
async def get_patient_invoices(
    patient_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    # Verify authorization
    verify_patient_ownership(patient_id, current_user)

    async with conn.cursor(row_factory=dict_row) as cur:
        # Check patient exists
        await cur.execute("SELECT patient_id FROM patient WHERE patient_id = %s;", (patient_id,))
        if not await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient with id {patient_id} not found",
            )

        query = """
            SELECT 
                i.invoice_id,
                i.appointment_id,
                i.staff_id,
                i.invoice_date,
                i.amount_paid,
                i.balance,
                i.status,
                d.doctor_name,
                a.appointment_date
            FROM invoice i
            JOIN appointment a ON a.appointment_id = i.appointment_id
            LEFT JOIN doctor d ON d.doctor_id = a.doctor_id
            WHERE a.patient_id = %s
            ORDER BY i.invoice_date DESC, i.invoice_id DESC;
        """
        await cur.execute(query, (patient_id,))
        rows = await cur.fetchall()
        return [PatientInvoiceResponse(**row) for row in rows]


# =========================================================================
# 3. GET /api/patients/{patient_id}/insurance
# =========================================================================
@router.get(
    "/{patient_id}/insurance",
    response_model=List[PatientInsurancePolicyResponse],
    summary="Get patient insurance policies",
    description="Retrieves insurance policies and coverage terms for a patient.",
)
async def get_patient_insurance(
    patient_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    # Verify authorization
    verify_patient_ownership(patient_id, current_user)

    async with conn.cursor(row_factory=dict_row) as cur:
        # Check patient exists
        await cur.execute("SELECT patient_id FROM patient WHERE patient_id = %s;", (patient_id,))
        if not await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient with id {patient_id} not found",
            )

        # Fetch policies
        policy_query = """
            SELECT 
                p.policy_id,
                p.patient_id,
                p.provider_id,
                ip.provider_name,
                p.policy_number,
                p.start_date,
                p.end_date,
                p.status
            FROM insurance_policy p
            LEFT JOIN insurance_provider ip ON ip.provider_id = p.provider_id
            WHERE p.patient_id = %s
            ORDER BY p.start_date DESC;
        """
        await cur.execute(policy_query, (patient_id,))
        policies = await cur.fetchall()

        if not policies:
            return []

        policy_ids = [p["policy_id"] for p in policies]

        # Fetch coverages for these policies
        coverage_query = """
            SELECT 
                c.coverage_id,
                c.policy_id,
                c.treatment_id,
                t.treatment_name,
                c.coverage_percentage,
                c.maximum_amount
            FROM insurance_coverage c
            LEFT JOIN treatment t ON t.treatment_id = c.treatment_id
            WHERE c.policy_id = ANY(%s)
            ORDER BY c.coverage_id ASC;
        """
        await cur.execute(coverage_query, (policy_ids,))
        coverages = await cur.fetchall()

        # Map coverages to policies
        coverage_map = {}
        for cov in coverages:
            pid = cov["policy_id"]
            if pid not in coverage_map:
                coverage_map[pid] = []
            coverage_map[pid].append(PatientInsuranceCoverageResponse(**cov))

        result = []
        for pol in policies:
            pol_dict = dict(pol)
            pol_dict["coverages"] = coverage_map.get(pol["policy_id"], [])
            result.append(PatientInsurancePolicyResponse(**pol_dict))

        return result


# =========================================================================
# 4. PUT /api/patients/{patient_id}/emergency-contacts/{contact_id}
# =========================================================================
@router.put(
    "/{patient_id}/emergency-contacts/{contact_id}",
    response_model=EmergencyContactResponse,
    summary="Update patient emergency contact",
    description="Updates an emergency contact record for a patient.",
    dependencies=[Depends(require_csrf)],
)
async def update_emergency_contact(
    patient_id: int,
    contact_id: int,
    payload: EmergencyContactUpdate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    verify_patient_ownership(patient_id, current_user)

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No update fields provided",
        )

    async with conn.cursor(row_factory=dict_row) as cur:
        # Verify contact exists for this patient
        await cur.execute(
            """
            SELECT emergency_contact_id 
            FROM emergency_contact 
            WHERE emergency_contact_id = %s AND patient_id = %s;
            """,
            (contact_id, patient_id),
        )
        if not await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Emergency contact {contact_id} for patient {patient_id} not found.",
            )

        set_clauses = [f"{key} = %s" for key in update_data.keys()]
        values = list(update_data.values())
        values.extend([contact_id, patient_id])

        update_query = f"""
            UPDATE emergency_contact
            SET {', '.join(set_clauses)}
            WHERE emergency_contact_id = %s AND patient_id = %s
            RETURNING *;
        """
        await cur.execute(update_query, tuple(values))
        updated_contact = await cur.fetchone()
        return EmergencyContactResponse(**updated_contact)


# =========================================================================
# 5. DELETE /api/patients/{patient_id}/emergency-contacts/{contact_id}
# =========================================================================
@router.delete(
    "/{patient_id}/emergency-contacts/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete patient emergency contact",
    description="Deletes an emergency contact record for a patient.",
    dependencies=[Depends(require_csrf)],
)
async def delete_emergency_contact(
    patient_id: int,
    contact_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    verify_patient_ownership(patient_id, current_user)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT emergency_contact_id 
            FROM emergency_contact 
            WHERE emergency_contact_id = %s AND patient_id = %s;
            """,
            (contact_id, patient_id),
        )
        if not await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Emergency contact {contact_id} for patient {patient_id} not found.",
            )

        await cur.execute(
            "DELETE FROM emergency_contact WHERE emergency_contact_id = %s AND patient_id = %s;",
            (contact_id, patient_id),
        )
        return None
