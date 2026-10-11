from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.api.v1.endpoints._guards import STAFF_ROLES, check_branch_scope, database_mutation
from app.auth.dependencies import get_current_user, require_csrf, require_role, verify_patient_ownership
from app.auth.schemas import JWTPayload, UserType
from app.core.database import get_db
from app.schemas.appointment_treatment import AppointmentTreatmentCreate, AppointmentTreatmentResponse

router = APIRouter(prefix="/appointments", tags=["Appointment Treatments"])

# One appointment can have several treatments (appointment_treatment bridge table).
# unitprice is copied from the catalogue when recorded, so later price changes do not
# alter past visits. The row marked is_primary mirrors appointment.treatment_id (the
# service chosen at booking) and is kept in sync by trg_appointment_treatment_sync.
_TREATMENT_ROWS = """
    SELECT at.appointment_treatment_id, at.appointment_id, at.treatment_id, at.quantity,
           at.unitprice AS unit_price, at.is_primary,
           t.treatment_name, t.service_code, c.category_name
      FROM appointment_treatment at
      JOIN treatment t ON t.treatment_id = at.treatment_id
      LEFT JOIN treatment_category c ON c.category_id = t.category_id
"""


async def _get_appointment(cur, appointment_id: int) -> dict:
    await cur.execute(
        """SELECT appointment_id, patient_id, branch_id, doctor_id, treatment_id, status
           FROM appointment WHERE appointment_id = %s FOR UPDATE;""",
        (appointment_id,),
    )
    appointment = await cur.fetchone()
    if not appointment:
        raise HTTPException(404, f"Appointment {appointment_id} not found")
    return appointment


def _authorize_appointment(appointment: dict, current_user: JWTPayload, *, write: bool = False) -> None:
    if current_user.user_type == UserType.PATIENT.value:
        if write:
            raise HTTPException(403, "Patients cannot modify appointment treatments.")
        verify_patient_ownership(appointment["patient_id"], current_user)
        return
    if current_user.role.lower() not in STAFF_ROLES:
        raise HTTPException(403, "Staff credentials required for this resource.")
    check_branch_scope(appointment["branch_id"], current_user)
    if current_user.role.lower() == "doctor" and current_user.doctor_id != appointment["doctor_id"]:
        raise HTTPException(403, "Doctors can only access their own appointments.")


async def _ensure_editable(cur, appointment: dict) -> None:
    """Treatments can change until the visit is cancelled or billed."""
    if appointment["status"] == "Cancelled":
        raise HTTPException(409, "Treatments cannot be recorded for a cancelled appointment.")
    await cur.execute("SELECT 1 FROM invoice WHERE appointment_id = %s;", (appointment["appointment_id"],))
    if await cur.fetchone():
        raise HTTPException(409, "Treatments are locked because an invoice has been generated.")


@router.get("/{appointment_id}/treatments", response_model=List[AppointmentTreatmentResponse])
async def list_appointment_treatments(
    appointment_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        appointment = await _get_appointment(cur, appointment_id)
        _authorize_appointment(appointment, current_user)
        await cur.execute(
            _TREATMENT_ROWS + " WHERE at.appointment_id = %s ORDER BY at.appointment_treatment_id;",
            (appointment_id,),
        )
        rows = await cur.fetchall()
    return [AppointmentTreatmentResponse(**row) for row in rows]


@router.post(
    "/{appointment_id}/treatments",
    response_model=AppointmentTreatmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def add_appointment_treatment(
    appointment_id: int,
    payload: AppointmentTreatmentCreate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*STAFF_ROLES)),
):
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        appointment = await _get_appointment(cur, appointment_id)
        _authorize_appointment(appointment, current_user, write=True)
        await _ensure_editable(cur, appointment)
        await cur.execute("SELECT standard_price FROM treatment WHERE treatment_id = %s;", (payload.treatment_id,))
        treatment = await cur.fetchone()
        if not treatment:
            raise HTTPException(404, f"Treatment {payload.treatment_id} not found")
        await cur.execute(
            "SELECT 1 FROM appointment_treatment WHERE appointment_id = %s AND treatment_id = %s;",
            (appointment_id, payload.treatment_id),
        )
        if await cur.fetchone():
            raise HTTPException(409, "This treatment is already recorded for the appointment.")
        await cur.execute(
            """INSERT INTO appointment_treatment (appointment_id, treatment_id, quantity, unitprice)
               VALUES (%s, %s, %s, %s) RETURNING appointment_treatment_id;""",
            (appointment_id, payload.treatment_id, payload.quantity, treatment["standard_price"]),
        )
        row_id = (await cur.fetchone())["appointment_treatment_id"]
        await cur.execute(_TREATMENT_ROWS + " WHERE at.appointment_treatment_id = %s;", (row_id,))
        row = await cur.fetchone()
    return AppointmentTreatmentResponse(**row)


@router.delete(
    "/{appointment_id}/treatments/{appointment_treatment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def remove_appointment_treatment(
    appointment_id: int,
    appointment_treatment_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*STAFF_ROLES)),
):
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        appointment = await _get_appointment(cur, appointment_id)
        _authorize_appointment(appointment, current_user, write=True)
        await _ensure_editable(cur, appointment)
        await cur.execute(
            "SELECT is_primary FROM appointment_treatment "
            "WHERE appointment_treatment_id = %s AND appointment_id = %s;",
            (appointment_treatment_id, appointment_id),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Treatment is not recorded for this appointment.")
        if row["is_primary"]:
            # Clear the booked service too, otherwise the sync trigger would re-add it.
            await cur.execute(
                "UPDATE appointment SET treatment_id = NULL WHERE appointment_id = %s;",
                (appointment_id,),
            )
        await cur.execute(
            "DELETE FROM appointment_treatment WHERE appointment_treatment_id = %s;",
            (appointment_treatment_id,),
        )
    return None
