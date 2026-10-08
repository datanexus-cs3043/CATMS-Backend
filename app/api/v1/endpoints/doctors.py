from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, Path, Query, Response, HTTPException, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.core.database import get_db
from app.auth.dependencies import get_current_user, require_role, require_csrf, require_session_csrf
from app.auth.schemas import JWTPayload
from app.api.v1.endpoints._guards import STAFF_ROLES, check_branch_scope, database_mutation
from app.api.v1.endpoints.specialties import create_specialty as create_catalogue_specialty
from app.schemas.doctor import (
    DoctorCreate,
    DoctorUpdate,
    DoctorResponse,
    DoctorDetailResponse,
    DoctorDirectoryResponse,
    DoctorSpecialtyCreate,
    SpecialtyResponse,
    DoctorAppointmentResponse,
    DoctorAvailabilitySlot,
)

router = APIRouter(prefix="/doctors", tags=["Doctors"])


def _split_doctor_name(display_name: str, current_last_name: str) -> tuple[str, str]:
    """Map the doctor's display name to the staff directory's first/last names."""
    parts = display_name.removeprefix("Dr.").strip().split()
    if len(parts) < 2:
        return parts[0], current_last_name
    return " ".join(parts[:-1]), parts[-1]


@router.get("", response_model=List[DoctorDirectoryResponse])
async def list_doctors(
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    search: Optional[str] = Query(None, description="Search doctor name or license number"),
    branch_id: Optional[int] = Query(None, gt=0, description="Filter doctors by branch ID"),
    specialty_id: Optional[int] = Query(None, gt=0, description="Filter doctors by specialty ID"),
    conn: AsyncConnection = Depends(get_db),
):
    """Retrieve list of registered doctors with optional search and branch filtering."""
    query = """
        SELECT d.*, s.branch_id, b.branch_name
        FROM doctor d
        JOIN staff s ON d.staff_id = s.staff_id
        JOIN branch b ON s.branch_id = b.branch_id
        WHERE 1=1
    """
    params = []

    if branch_id is not None:
        query += " AND s.branch_id = %s"
        params.append(branch_id)

    if specialty_id is not None:
        query += """ AND EXISTS (SELECT 1 FROM doctor_specialty ds
                    WHERE ds.doctor_id = d.doctor_id AND ds.specialty_id = %s)"""
        params.append(specialty_id)

    if search:
        query += " AND (d.doctor_name ILIKE %s OR d.doctor_license_number ILIKE %s)"
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern])

    query += " ORDER BY d.doctor_id ASC LIMIT %s OFFSET %s;"
    params.extend([limit, skip])

    async with conn.cursor() as cur:
        await cur.execute(query, tuple(params))
        rows = await cur.fetchall()
        if not rows:
            return []
        # Load specialties once for this page, rather than requesting each profile.
        await cur.execute("""
            SELECT ds.doctor_id, sp.*
            FROM doctor_specialty ds
            JOIN specialty sp ON ds.specialty_id = sp.specialty_id
            WHERE ds.doctor_id = ANY(%s)
            ORDER BY sp.specialty_name, sp.specialty_id;
        """, ([row["doctor_id"] for row in rows],))
        specialties_by_doctor = {}
        for specialty in await cur.fetchall():
            specialties_by_doctor.setdefault(specialty["doctor_id"], []).append(SpecialtyResponse(**specialty))
        return [DoctorDirectoryResponse(**row, specialties=specialties_by_doctor.get(row["doctor_id"], []))
                for row in rows]


@router.get("/{doctor_id}", response_model=DoctorDetailResponse)
async def get_doctor(
    doctor_id: int = Path(..., gt=0),
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


@router.post("", response_model=DoctorResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_session_csrf)])
async def create_doctor(
    payload: DoctorCreate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin")),
):
    """Register a new doctor profile linked to a staff record."""
    async with database_mutation(conn), conn.cursor() as cur:
        await cur.execute("SELECT staff_id FROM staff WHERE staff_id = %s;", (payload.staff_id,))
        if not await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Staff member with id {payload.staff_id} does not exist",
            )

        await cur.execute("SELECT doctor_id FROM doctor WHERE staff_id = %s;", (payload.staff_id,))
        if await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Doctor profile already exists for staff id {payload.staff_id}",
            )

        insert_query = """
            INSERT INTO doctor (staff_id, doctor_name, doctor_license_number)
            VALUES (%s, %s, %s)
            RETURNING *;
        """
        await cur.execute(
            insert_query,
            (payload.staff_id, payload.doctor_name, payload.doctor_license_number),
        )
        new_doc = await cur.fetchone()
        return DoctorResponse(**new_doc)


@router.put("/{doctor_id}", response_model=DoctorResponse, dependencies=[Depends(require_session_csrf)])
async def update_doctor(
    payload: DoctorUpdate,
    doctor_id: int = Path(..., gt=0),
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin")),
):
    """Update details of a doctor profile."""
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No update fields provided",
        )

    async with database_mutation(conn), conn.cursor() as cur:
        await cur.execute(
            """
            SELECT d.doctor_id, d.staff_id, s.last_name
            FROM doctor d
            JOIN staff s ON s.staff_id = d.staff_id
            WHERE d.doctor_id = %s
            FOR UPDATE OF d, s;
            """,
            (doctor_id,),
        )
        existing = await cur.fetchone()
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Doctor with id {doctor_id} not found",
            )

        set_clauses = [f"{k} = %s" for k in update_data.keys()]
        values = list(update_data.values())
        values.append(doctor_id)

        update_query = f"""
            UPDATE doctor
            SET {', '.join(set_clauses)}
            WHERE doctor_id = %s
            RETURNING *;
        """
        await cur.execute(update_query, tuple(values))
        updated_doc = await cur.fetchone()

        if "doctor_name" in update_data:
            first_name, last_name = _split_doctor_name(
                update_data["doctor_name"],
                existing["last_name"],
            )
            await cur.execute(
                """
                UPDATE staff
                SET first_name = %s, last_name = %s
                WHERE staff_id = %s;
                """,
                (first_name, last_name, existing["staff_id"]),
            )

        return DoctorResponse(**updated_doc)


@router.get("/specialties/all", response_model=List[SpecialtyResponse])
async def list_specialties(
    conn: AsyncConnection = Depends(get_db),
):
    """List all available medical specialties."""
    async with conn.cursor() as cur:
        await cur.execute("SELECT * FROM specialty ORDER BY specialty_name ASC;")
        rows = await cur.fetchall()
        return [SpecialtyResponse(**row) for row in rows]


@router.post("/specialties", response_model=SpecialtyResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_session_csrf)])
async def create_specialty(
    payload: DoctorSpecialtyCreate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin")),
):
    """Create a specialty using the same catalogue rules as /specialties."""
    # This alias enforces its own admin/session-CSRF dependencies above.
    return await create_catalogue_specialty(payload=payload, conn=conn, current_user=current_user)


@router.post("/{doctor_id}/specialties/{specialty_id}", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_session_csrf)],
             responses={200: {"description": "Specialty was already assigned"}})
async def assign_specialty_to_doctor(
    response: Response,
    doctor_id: int = Path(..., gt=0),
    specialty_id: int = Path(..., gt=0),
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin")),
):
    """Assign a specialty; repeating an existing assignment returns 200."""
    async with database_mutation(conn), conn.cursor() as cur:
        await cur.execute("SELECT doctor_id FROM doctor WHERE doctor_id = %s;", (doctor_id,))
        if not await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Doctor with id {doctor_id} not found",
            )

        await cur.execute("SELECT specialty_id FROM specialty WHERE specialty_id = %s;", (specialty_id,))
        if not await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Specialty with id {specialty_id} not found",
            )

        insert_query = """
            INSERT INTO doctor_specialty (doctor_id, specialty_id)
            VALUES (%s, %s)
            ON CONFLICT (doctor_id, specialty_id) DO NOTHING
            RETURNING doctor_id, specialty_id;
        """
        await cur.execute(insert_query, (doctor_id, specialty_id))
        if not await cur.fetchone():
            response.status_code = status.HTTP_200_OK
            return {"message": "Specialty is already linked to this doctor"}
        return {"message": "Specialty linked to doctor successfully"}


# =========================================================================
# DELETE /api/doctors/{doctor_id}/specialties/{specialty_id} (Admin + CSRF)
# =========================================================================
@router.delete(
    "/{doctor_id}/specialties/{specialty_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unassign specialty from doctor",
    description="Removes a specialty assignment from a doctor. Admin only.",
    dependencies=[Depends(require_csrf)],
)
async def unassign_specialty_from_doctor(
    doctor_id: int,
    specialty_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin")),
):
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT doctor_id FROM doctor WHERE doctor_id = %s;", (doctor_id,))
        if not await cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Doctor {doctor_id} not found")
        await cur.execute(
            "SELECT doctor_id FROM doctor_specialty WHERE doctor_id = %s AND specialty_id = %s;",
            (doctor_id, specialty_id),
        )
        if not await cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Specialty {specialty_id} is not assigned to doctor {doctor_id}")
        await cur.execute(
            "DELETE FROM doctor_specialty WHERE doctor_id = %s AND specialty_id = %s;",
            (doctor_id, specialty_id),
        )
    return None

# =========================================================================
# DELETE /api/doctors/{doctor_id}  (Admin only + CSRF)
# =========================================================================
@router.delete(
    "/{doctor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete doctor",
    description="Removes a doctor profile. Admin only.",
    dependencies=[Depends(require_csrf)],
)
async def delete_doctor(
    doctor_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role("admin")),
):
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT doctor_id FROM doctor WHERE doctor_id = %s;", (doctor_id,))
        if not await cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Doctor with id {doctor_id} not found")
        await cur.execute("DELETE FROM doctor_specialty WHERE doctor_id = %s;", (doctor_id,))
        await cur.execute("DELETE FROM doctor WHERE doctor_id = %s;", (doctor_id,))
    return None


# =========================================================================
# GET /api/doctors/{doctor_id}/appointments  (Staff or authenticated)
# =========================================================================
@router.get(
    "/{doctor_id}/appointments",
    response_model=List[DoctorAppointmentResponse],
    summary="Get doctor appointments",
    description="Returns all appointments assigned to a doctor.",
)
async def get_doctor_appointments(
    doctor_id: int,
    appointment_date: Optional[date] = Query(None, description="Filter by date (YYYY-MM-DD)"),
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*STAFF_ROLES)),
):
    if current_user.user_type != "staff":
        raise HTTPException(403, "Staff credentials required.")
    if current_user.role.lower() == "doctor" and current_user.doctor_id != doctor_id:
        raise HTTPException(403, "Doctors can only access their own appointment list.")
    if current_user.role.lower() != "admin":
        check_branch_scope(current_user.branch_id, current_user)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT doctor_id FROM doctor WHERE doctor_id = %s;", (doctor_id,))
        if not await cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Doctor with id {doctor_id} not found")
        query = """
            SELECT a.*,
                   (p.first_name || ' ' || p.last_name) AS patient_name,
                   b.branch_name,
                   t.treatment_name
            FROM appointment a
            JOIN patient p ON a.patient_id = p.patient_id
            JOIN branch b  ON a.branch_id  = b.branch_id
            LEFT JOIN treatment t ON a.treatment_id = t.treatment_id
            WHERE a.doctor_id = %s
        """
        params: list = [doctor_id]
        if current_user.role.lower() != "admin":
            query += " AND a.branch_id = %s"
            params.append(current_user.branch_id)
        if appointment_date:
            query += " AND a.appointment_date = %s"
            params.append(appointment_date)
        query += " ORDER BY a.appointment_date DESC, a.start_time ASC;"
        await cur.execute(query, tuple(params))
        rows = await cur.fetchall()
        return [DoctorAppointmentResponse(**r) for r in rows]


# =========================================================================
# GET /api/doctors/{doctor_id}/specialties
# =========================================================================
@router.get(
    "/{doctor_id}/specialties",
    response_model=List[SpecialtyResponse],
    summary="Get doctor specialties",
    description="Returns all specialties assigned to a doctor.",
)
async def get_doctor_specialties(
    doctor_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT doctor_id FROM doctor WHERE doctor_id = %s;", (doctor_id,))
        if not await cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Doctor with id {doctor_id} not found")
        await cur.execute("""
            SELECT sp.*
            FROM specialty sp
            JOIN doctor_specialty ds ON sp.specialty_id = ds.specialty_id
            WHERE ds.doctor_id = %s
            ORDER BY sp.specialty_name ASC;
        """, (doctor_id,))
        rows = await cur.fetchall()
        return [SpecialtyResponse(**r) for r in rows]


# =========================================================================
# GET /api/doctors/{doctor_id}/availability
# =========================================================================
@router.get(
    "/{doctor_id}/availability",
    response_model=List[DoctorAvailabilitySlot],
    summary="Get doctor booked slots",
    description="Returns booked slots only; does not calculate working hours or free availability.",
)
async def get_doctor_availability(
    doctor_id: int,
    from_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    to_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    if to_date < from_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="to_date must be >= from_date")
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT doctor_id FROM doctor WHERE doctor_id = %s;", (doctor_id,))
        if not await cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Doctor with id {doctor_id} not found")
        await cur.execute("""
            SELECT appointment_date,
                   TO_CHAR(start_time, 'HH24:MI') || '-' || TO_CHAR(end_time, 'HH24:MI') AS slot
            FROM appointment
            WHERE doctor_id = %s
              AND appointment_date BETWEEN %s AND %s
              AND NOT EXISTS (SELECT 1 FROM appointment next_a
                              WHERE next_a.original_appointment_id = appointment.appointment_id)
            ORDER BY appointment_date ASC, start_time ASC;
        """, (doctor_id, from_date, to_date))
        rows = await cur.fetchall()
        slots_by_date: dict = {}
        for row in rows:
            d = row["appointment_date"]
            slots_by_date.setdefault(d, []).append(row["slot"])
        return [
            DoctorAvailabilitySlot(appointment_date=d, booked_slots=slots)
            for d, slots in sorted(slots_by_date.items())
        ]
