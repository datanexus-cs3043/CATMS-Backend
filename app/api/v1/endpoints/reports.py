from typing import List

from fastapi import APIRouter, Depends, HTTPException
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.api.v1.endpoints._guards import STAFF_ROLES
from app.auth.dependencies import get_current_user, require_role
from app.auth.schemas import JWTPayload
from app.core.database import get_db
from app.schemas.reports import (
    AppointmentSummaryResponse,
    AppointmentTypeSummary,
    DoctorRevenueResponse,
)

router = APIRouter(prefix="/reports", tags=["Reports"])


def _report_scope(current_user: JWTPayload, column: str) -> tuple[str, list[int]]:
    if current_user.user_type != "staff" or current_user.role.lower() not in STAFF_ROLES:
        raise HTTPException(403, "Staff credentials required for reports.")
    if current_user.role.lower() == "admin":
        return "", []
    if current_user.branch_id is None:
        raise HTTPException(403, "A branch assignment is required for this report.")
    return f" WHERE {column} = %s", [current_user.branch_id]


@router.get(
    "/appointments-summary",
    response_model=AppointmentSummaryResponse,
)
async def appointments_summary(
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*STAFF_ROLES)),
):
    scope, params = _report_scope(current_user, "a.branch_id")
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(f"SELECT COUNT(*) AS total_appointments FROM appointment a{scope};", params)
        total = (await cur.fetchone())["total_appointments"]
        await cur.execute(
            f"""SELECT a.appointment_type, COUNT(*) AS appointment_count
                FROM appointment a{scope}
                GROUP BY a.appointment_type
                ORDER BY appointment_count DESC, a.appointment_type ASC;""",
            params,
        )
        by_type = [AppointmentTypeSummary(**row) for row in await cur.fetchall()]
    return AppointmentSummaryResponse(
        total_appointments=total,
        appointments_by_type=by_type,
    )


@router.get("/doctor-revenue", response_model=List[DoctorRevenueResponse])
async def doctor_revenue(
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*STAFF_ROLES)),
):
    scope, params = _report_scope(current_user, "a.branch_id")
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"""SELECT d.doctor_id, d.doctor_name,
                       COUNT(DISTINCT a.appointment_id) AS appointment_count,
                       COUNT(DISTINCT i.invoice_id) AS invoice_count,
                       COALESCE(SUM(inv.billed_amount), 0) AS billed_revenue,
                       COALESCE(SUM(inv.collected_amount), 0) AS collected_revenue
                FROM doctor d
                JOIN appointment a ON a.doctor_id = d.doctor_id
                LEFT JOIN invoice i ON i.appointment_id = a.appointment_id
                LEFT JOIN (
                    SELECT invoice_id, amount_paid + balance AS billed_amount,
                           amount_paid AS collected_amount
                    FROM invoice
                ) inv ON inv.invoice_id = i.invoice_id{scope}
                GROUP BY d.doctor_id, d.doctor_name
                ORDER BY collected_revenue DESC, d.doctor_name ASC;""",
            params,
        )
        return [DoctorRevenueResponse(**row) for row in await cur.fetchall()]
