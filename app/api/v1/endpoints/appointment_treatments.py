from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.api.v1.endpoints._guards import STAFF_ROLES, check_branch_scope, database_mutation
from app.auth.dependencies import get_current_user, require_csrf, require_role, verify_patient_ownership
from app.auth.schemas import JWTPayload, UserType
from app.core.database import get_db
from app.schemas.appointment_treatment import AppointmentTreatmentCreate
from app.schemas.treatment import TreatmentResponse

router = APIRouter(prefix="/appointments", tags=["Appointment Treatments"])


async def _get_appointment(cur, appointment_id: int) -> dict:
    await cur.execute(
        """SELECT appointment_id, patient_id, branch_id, doctor_id, treatment_id
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


@router.get("/{appointment_id}/treatments", response_model=List[TreatmentResponse])
async def list_appointment_treatments(
    appointment_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        appointment = await _get_appointment(cur, appointment_id)
        _authorize_appointment(appointment, current_user)
        if appointment["treatment_id"] is None:
            return []
        await cur.execute(
            """SELECT t.*, c.category_name
               FROM treatment t JOIN treatment_category c ON c.category_id = t.category_id
               WHERE t.treatment_id = %s;""",
            (appointment["treatment_id"],),
        )
        treatment = await cur.fetchone()
    return [TreatmentResponse(**treatment)] if treatment else []


@router.post(
    "/{appointment_id}/treatments",
    response_model=TreatmentResponse,
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
        if appointment["treatment_id"] is not None:
            raise HTTPException(409, "This appointment already has a treatment assigned.")
        await cur.execute(
            """SELECT t.*, c.category_name
               FROM treatment t JOIN treatment_category c ON c.category_id = t.category_id
               WHERE t.treatment_id = %s;""",
            (payload.treatment_id,),
        )
        treatment = await cur.fetchone()
        if not treatment:
            raise HTTPException(404, f"Treatment {payload.treatment_id} not found")
        await cur.execute(
            "UPDATE appointment SET treatment_id = %s WHERE appointment_id = %s;",
            (payload.treatment_id, appointment_id),
        )
    return TreatmentResponse(**treatment)


@router.delete(
    "/{appointment_id}/treatments/{treatment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def remove_appointment_treatment(
    appointment_id: int,
    treatment_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*STAFF_ROLES)),
):
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        appointment = await _get_appointment(cur, appointment_id)
        _authorize_appointment(appointment, current_user, write=True)
        if appointment["treatment_id"] != treatment_id:
            raise HTTPException(404, "Treatment is not assigned to this appointment.")
        await cur.execute(
            "UPDATE appointment SET treatment_id = NULL WHERE appointment_id = %s;",
            (appointment_id,),
        )
    return None
