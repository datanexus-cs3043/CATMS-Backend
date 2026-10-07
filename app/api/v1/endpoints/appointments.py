from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.auth.dependencies import require_csrf, require_role
from app.auth.schemas import JWTPayload
from app.api.v1.endpoints._guards import check_branch_scope, database_mutation

from app.core.database import get_db
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentUpdate,
    AppointmentResponse,
    AppointmentDetailResponse,
    ConsultationNoteCreate,
    ConsultationNoteUpdate,
    EmergencyAppointmentCreate,
    RescheduleRequest,
    ConsultationNoteResponse,
)

router = APIRouter(prefix="/appointments", tags=["Appointments"])
notes_router = APIRouter(prefix="/notes", tags=["Consultation Notes"])
STAFF_ROLES = ("admin", "branch_manager", "doctor", "receptionist_cashier")


def _check_action_scope(branch_id: int, doctor_id: int, current_user: JWTPayload) -> None:
    check_branch_scope(branch_id, current_user)
    if current_user.role.lower() == "doctor" and current_user.doctor_id != doctor_id:
        raise HTTPException(403, "Doctors can only manage their own appointments.")


async def _get_appointment_row(conn: AsyncConnection, appointment_id: int) -> dict:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT * FROM appointment WHERE appointment_id = %s;", (appointment_id,))
        appointment = await cur.fetchone()
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Appointment {appointment_id} not found")
    return appointment


@router.post(
    "/{appointment_id}/complete",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="Complete appointment",
)
async def complete_appointment(
    appointment_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*STAFF_ROLES)),
):
    appointment = await _get_appointment_row(conn, appointment_id)
    _check_action_scope(appointment["branch_id"], appointment["doctor_id"], current_user)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Appointment completion requires a persisted appointment status field.",
    )


@router.post(
    "/{appointment_id}/cancel",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="Cancel appointment",
)
async def cancel_appointment(
    appointment_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*STAFF_ROLES)),
):
    appointment = await _get_appointment_row(conn, appointment_id)
    _check_action_scope(appointment["branch_id"], appointment["doctor_id"], current_user)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Appointment cancellation requires a persisted appointment status field.",
    )


@router.post(
    "/{appointment_id}/reschedule",
    response_model=AppointmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Reschedule appointment",
    dependencies=[Depends(require_csrf)],
)
async def reschedule_appointment(
    appointment_id: int,
    payload: RescheduleRequest,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*STAFF_ROLES)),
):
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT * FROM appointment WHERE appointment_id = %s FOR UPDATE;", (appointment_id,))
        appointment = await cur.fetchone()
        if not appointment:
            raise HTTPException(404, f"Appointment {appointment_id} not found")
        _check_action_scope(appointment["branch_id"], appointment["doctor_id"], current_user)
        await cur.execute("SELECT appointment_id FROM appointment WHERE original_appointment_id = %s;", (appointment_id,))
        if await cur.fetchone():
            raise HTTPException(409, "This appointment has already been rescheduled.")
        await _check_booking(cur, appointment["doctor_id"], appointment["branch_id"],
                             payload.appointment_date, payload.start_time, payload.end_time,
                             original_id=appointment_id)
        created_by = str(current_user.user_id)
        await cur.execute(
            """INSERT INTO appointment
               (patient_id, doctor_id, branch_id, appointment_date, start_time,
                end_time, appointment_type, created_by, original_appointment_id, treatment_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *;""",
            (appointment["patient_id"], appointment["doctor_id"], appointment["branch_id"],
             payload.appointment_date, payload.start_time, payload.end_time,
             appointment["appointment_type"], created_by, appointment_id,
             appointment["treatment_id"]),
        )
        return AppointmentResponse(**await cur.fetchone())


@router.post(
    "/emergency",
    response_model=AppointmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create emergency appointment",
    dependencies=[Depends(require_csrf)],
)
async def create_emergency_appointment(
    payload: EmergencyAppointmentCreate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*STAFF_ROLES)),
):
    _check_action_scope(payload.branch_id, payload.doctor_id, current_user)
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        for table, column, value in (
            ("patient", "patient_id", payload.patient_id),
            ("doctor", "doctor_id", payload.doctor_id),
            ("branch", "branch_id", payload.branch_id),
        ):
            await cur.execute(f"SELECT {column} FROM {table} WHERE {column} = %s;", (value,))
            if not await cur.fetchone():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail=f"{table.title()} {value} does not exist")
        await _check_booking(cur, payload.doctor_id, payload.branch_id,
                             payload.appointment_date, payload.start_time, payload.end_time)
        await cur.execute(
            """INSERT INTO appointment
               (patient_id, doctor_id, branch_id, appointment_date, start_time,
                end_time, appointment_type, created_by, treatment_id)
               VALUES (%s, %s, %s, %s, %s, %s, 'Emergency', %s, %s) RETURNING *;""",
            (payload.patient_id, payload.doctor_id, payload.branch_id,
             payload.appointment_date, payload.start_time, payload.end_time,
             str(current_user.user_id), payload.treatment_id),
        )
        return AppointmentResponse(**await cur.fetchone())


async def _check_booking(cur, doctor_id, branch_id, appointment_date, start_time, end_time, original_id=None):
    # Serializes the new action handlers for one doctor; legacy booking routes are unchanged.
    await cur.execute(
        """SELECT s.branch_id FROM doctor d JOIN staff s ON s.staff_id = d.staff_id
           WHERE d.doctor_id = %s FOR UPDATE OF d;""", (doctor_id,))
    doctor = await cur.fetchone()
    if not doctor or doctor["branch_id"] != branch_id:
        raise HTTPException(422, "The doctor must belong to the appointment branch.")
    await cur.execute(
        """SELECT a.appointment_id FROM appointment a
           WHERE a.doctor_id = %s AND a.appointment_date = %s
             AND a.start_time < %s AND a.end_time > %s
             AND (%s::integer IS NULL OR a.appointment_id != %s)
             AND NOT EXISTS (SELECT 1 FROM appointment next_a
                             WHERE next_a.original_appointment_id = a.appointment_id)
           LIMIT 1;""",
        (doctor_id, appointment_date, end_time, start_time, original_id, original_id),
    )
    if await cur.fetchone():
        raise HTTPException(409, "The doctor already has an appointment in this time range.")


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


@router.post("", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    payload: AppointmentCreate,
    conn: AsyncConnection = Depends(get_db),
):
    """Schedule and record a new clinic appointment."""
    async with conn.cursor() as cur:
        # Validate patient
        await cur.execute("SELECT patient_id FROM patient WHERE patient_id = %s;", (payload.patient_id,))
        if not await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Patient with id {payload.patient_id} does not exist",
            )

        # Validate doctor
        await cur.execute("SELECT doctor_id FROM doctor WHERE doctor_id = %s;", (payload.doctor_id,))
        if not await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Doctor with id {payload.doctor_id} does not exist",
            )

        # Validate branch
        await cur.execute("SELECT branch_id FROM branch WHERE branch_id = %s;", (payload.branch_id,))
        if not await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Branch with id {payload.branch_id} does not exist",
            )

        insert_query = """
            INSERT INTO appointment (
                patient_id, doctor_id, branch_id, appointment_date,
                start_time, end_time, appointment_type, created_by,
                original_appointment_id, treatment_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *;
        """
        await cur.execute(
            insert_query,
            (
                payload.patient_id,
                payload.doctor_id,
                payload.branch_id,
                payload.appointment_date,
                payload.start_time,
                payload.end_time,
                payload.appointment_type,
                payload.created_by,
                payload.original_appointment_id,
                payload.treatment_id,
            ),
        )
        new_appt = await cur.fetchone()
        return AppointmentResponse(**new_appt)


@router.put("/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment(
    appointment_id: int,
    payload: AppointmentUpdate,
    conn: AsyncConnection = Depends(get_db),
):
    """Reschedule or update details of an existing appointment."""
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No update fields provided",
        )

    async with conn.cursor() as cur:
        await cur.execute("SELECT appointment_id FROM appointment WHERE appointment_id = %s;", (appointment_id,))
        if not await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Appointment with id {appointment_id} not found",
            )

        set_clauses = [f"{k} = %s" for k in update_data.keys()]
        values = list(update_data.values())
        values.append(appointment_id)

        update_query = f"""
            UPDATE appointment
            SET {', '.join(set_clauses)}
            WHERE appointment_id = %s
            RETURNING *;
        """
        await cur.execute(update_query, tuple(values))
        updated_row = await cur.fetchone()
        return AppointmentResponse(**updated_row)


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_appointment(
    appointment_id: int,
    conn: AsyncConnection = Depends(get_db),
):
    """Cancel and remove an appointment."""
    async with conn.cursor() as cur:
        await cur.execute("SELECT appointment_id FROM appointment WHERE appointment_id = %s;", (appointment_id,))
        if not await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Appointment with id {appointment_id} not found",
            )

        await cur.execute("DELETE FROM appointment WHERE appointment_id = %s;", (appointment_id,))
        return None


@router.get("/{appointment_id}/notes", response_model=List[ConsultationNoteResponse])
async def list_consultation_notes(
    appointment_id: int,
    conn: AsyncConnection = Depends(get_db),
):
    """List consultation notes for a given appointment."""
    async with conn.cursor() as cur:
        await cur.execute("SELECT appointment_id FROM appointment WHERE appointment_id = %s;", (appointment_id,))
        if not await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Appointment with id {appointment_id} not found",
            )

        await cur.execute(
            "SELECT * FROM consultation_note WHERE appointment_id = %s ORDER BY created_at ASC;",
            (appointment_id,),
        )
        rows = await cur.fetchall()
        return [ConsultationNoteResponse(**row) for row in rows]


@router.post(
    "/{appointment_id}/notes",
    response_model=ConsultationNoteResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def add_consultation_note(
    appointment_id: int,
    payload: ConsultationNoteCreate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin", "branch_manager", "doctor")),
):
    """Add a clinical consultation note to an appointment."""
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT appointment_id, branch_id, doctor_id FROM appointment "
            "WHERE appointment_id = %s FOR UPDATE;",
            (appointment_id,),
        )
        appointment = await cur.fetchone()
        if not appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Appointment with id {appointment_id} not found",
            )
        check_branch_scope(appointment["branch_id"], current_user)
        if current_user.role.lower() == "doctor" and current_user.doctor_id != appointment["doctor_id"]:
            raise HTTPException(403, "Doctors can only add notes to their own appointments.")

        insert_query = """
            INSERT INTO consultation_note (appointment_id, note_content)
            VALUES (%s, %s)
            RETURNING *;
        """
        await cur.execute(insert_query, (appointment_id, payload.note_content))
        new_note = await cur.fetchone()
        return ConsultationNoteResponse(**new_note)


async def _get_note_row(conn: AsyncConnection, note_id: int, current_user: JWTPayload) -> dict:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """SELECT n.*, a.branch_id, a.doctor_id FROM consultation_note n
               JOIN appointment a ON a.appointment_id = n.appointment_id
               WHERE n.note_id = %s;""", (note_id,))
        note = await cur.fetchone()
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Consultation note {note_id} not found")
    check_branch_scope(note["branch_id"], current_user)
    if current_user.role.lower() == "doctor" and current_user.doctor_id != note["doctor_id"]:
        raise HTTPException(403, "Doctors can only access notes for their own appointments.")
    return note


@notes_router.get("/{note_id}", response_model=ConsultationNoteResponse, summary="Get consultation note")
async def get_consultation_note(
    note_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin", "branch_manager", "doctor")),
):
    return ConsultationNoteResponse(**await _get_note_row(conn, note_id, current_user))


@notes_router.put(
    "/{note_id}",
    response_model=ConsultationNoteResponse,
    summary="Update consultation note",
    dependencies=[Depends(require_csrf)],
)
async def update_consultation_note(
    note_id: int,
    payload: ConsultationNoteUpdate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin", "branch_manager", "doctor")),
):
    await _get_note_row(conn, note_id, current_user)
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "UPDATE consultation_note SET note_content = %s WHERE note_id = %s RETURNING *;",
            (payload.note_content, note_id),
        )
        return ConsultationNoteResponse(**await cur.fetchone())


@notes_router.delete(
    "/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete consultation note",
    dependencies=[Depends(require_csrf)],
)
async def delete_consultation_note(
    note_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin", "branch_manager", "doctor")),
):
    await _get_note_row(conn, note_id, current_user)
    async with database_mutation(conn), conn.cursor() as cur:
        await cur.execute("DELETE FROM consultation_note WHERE note_id = %s;", (note_id,))
    return None




