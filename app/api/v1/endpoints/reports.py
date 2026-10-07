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
    InsuranceComparisonResponse,
    OutstandingBalanceResponse,
    TreatmentCategoryReportResponse,
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


@router.get("/outstanding-balances", response_model=List[OutstandingBalanceResponse])
async def outstanding_balances(
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*STAFF_ROLES)),
):
    scope, params = _report_scope(current_user, "a.branch_id")
    scope = f"{scope} AND i.balance > 0" if scope else " WHERE i.balance > 0"
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"""SELECT i.invoice_id, a.patient_id,
                       p.first_name || ' ' || p.last_name AS patient_name,
                       i.invoice_date, i.balance, i.status
                FROM invoice i
                JOIN appointment a ON a.appointment_id = i.appointment_id
                JOIN patient p ON p.patient_id = a.patient_id{scope}
                ORDER BY i.balance DESC, i.invoice_date ASC;""",
            params,
        )
        return [OutstandingBalanceResponse(**row) for row in await cur.fetchall()]


@router.get(
    "/treatments-by-category",
    response_model=List[TreatmentCategoryReportResponse],
)
async def treatments_by_category(
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*STAFF_ROLES)),
):
    scope, params = _report_scope(current_user, "a.branch_id")
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"""SELECT tc.category_id, tc.category_name,
                       COUNT(DISTINCT t.treatment_id) AS treatment_count,
                       COALESCE(SUM(ii.quantity), 0) AS usage_count,
                       COALESCE(SUM(ii.quantity * ii.unitprice), 0) AS treatment_revenue
                FROM treatment_category tc
                JOIN treatment t ON t.category_id = tc.category_id
                LEFT JOIN invoice_item ii ON ii.treatment_id = t.treatment_id
                LEFT JOIN invoice i ON i.invoice_id = ii.invoice_id
                LEFT JOIN appointment a ON a.appointment_id = i.appointment_id
                {scope}
                GROUP BY tc.category_id, tc.category_name
                ORDER BY treatment_revenue DESC, tc.category_name ASC;""",
            params,
        )
        return [TreatmentCategoryReportResponse(**row) for row in await cur.fetchall()]


@router.get(
    "/insurance-vs-out-of-pocket",
    response_model=InsuranceComparisonResponse,
)
async def insurance_vs_out_of_pocket(
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*STAFF_ROLES)),
):
    scope, params = _report_scope(current_user, "a.branch_id")
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"""WITH scoped_invoices AS (
                    SELECT i.invoice_id, i.amount_paid, i.balance
                    FROM invoice i
                    JOIN appointment a ON a.appointment_id = i.appointment_id{scope}
                ),
                claim_totals AS (
                    SELECT c.invoice_id, SUM(c.approved_amount) AS approved_amount
                    FROM insurance_claim c
                    JOIN scoped_invoices si ON si.invoice_id = c.invoice_id
                    GROUP BY c.invoice_id
                )
                SELECT COALESCE(SUM(si.amount_paid + si.balance), 0) AS invoiced_amount,
                       COALESCE(SUM(ct.approved_amount), 0) AS insurance_approved_amount,
                       COALESCE(SUM(si.amount_paid), 0) AS patient_paid_amount,
                       GREATEST(
                           COALESCE(SUM(si.amount_paid), 0) -
                           COALESCE(SUM(ct.approved_amount), 0), 0
                       ) AS out_of_pocket_amount,
                       COALESCE(SUM(si.balance), 0) AS outstanding_amount
                FROM scoped_invoices si
                LEFT JOIN claim_totals ct ON ct.invoice_id = si.invoice_id;""",
            params,
        )
        return InsuranceComparisonResponse(**(await cur.fetchone()))
