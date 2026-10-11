from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.auth.dependencies import require_role
from app.auth.schemas import JWTPayload
from app.core.database import get_db
from app.schemas.reports import (
    BranchDailySummaryResponse,
    DoctorRevenueResponse,
    InsuranceComparisonResponse,
    OutstandingBalanceResponse,
    TreatmentCategoryReportResponse,
)

router = APIRouter(prefix="/reports", tags=["Reports"])
REPORT_ROLES = ("admin", "branch_manager")


def _report_scope(current_user: JWTPayload, column: str) -> tuple[str, list[int]]:
    if current_user.user_type != "staff" or current_user.role.lower() not in REPORT_ROLES:
        raise HTTPException(403, "Management credentials required for reports.")
    if current_user.role.lower() == "admin":
        return "", []
    if current_user.branch_id is None:
        raise HTTPException(403, "A branch assignment is required for this report.")
    return f" WHERE {column} = %s", [current_user.branch_id]


def _filters(current_user: JWTPayload, branch_col: str, date_col: str, branch_id: Optional[int],
             from_date: Optional[date], to_date: Optional[date]) -> tuple[str, list]:
    """WHERE clause for branch scope (managers: own branch only) and an optional date range."""
    scope, params = _report_scope(current_user, branch_col)
    conditions = [scope.removeprefix(" WHERE ")] if scope else []
    if not scope and branch_id is not None:
        conditions.append(f"{branch_col} = %s")
        params.append(branch_id)
    if from_date is not None:
        conditions.append(f"{date_col} >= %s")
        params.append(from_date)
    if to_date is not None:
        conditions.append(f"{date_col} <= %s")
        params.append(to_date)
    return (" WHERE " + " AND ".join(conditions)) if conditions else "", params


@router.get("/appointments-summary", response_model=List[BranchDailySummaryResponse])
async def appointments_summary(
    day: Optional[date] = Query(None, alias="date", description="One day; overrides from/to"),
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    branch_id: Optional[int] = Query(None, gt=0, description="Admin only"),
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*REPORT_ROLES)),
):
    """Report 1: branch-wise appointment summary per day (scheduled, completed, cancelled)."""
    if day is not None:
        from_date = to_date = day
    where, params = _filters(current_user, "v.branch_id", "v.appointment_date", branch_id, from_date, to_date)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"""SELECT v.branch_id, v.branch_name, v.appointment_date,
                       v.scheduled_count AS scheduled, v.completed_count AS completed,
                       v.cancelled_count AS cancelled, v.total_appointments AS total
                FROM v_branch_daily_appointment_summary v{where}
                ORDER BY v.appointment_date DESC, v.branch_name;""",
            params,
        )
        return [BranchDailySummaryResponse(**row) for row in await cur.fetchall()]


@router.get("/doctor-revenue", response_model=List[DoctorRevenueResponse])
async def doctor_revenue(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    branch_id: Optional[int] = Query(None, gt=0, description="Admin only"),
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*REPORT_ROLES)),
):
    """Report 2: doctor-wise revenue (billed and collected) for invoices dated in the period."""
    where, params = _filters(current_user, "s.branch_id", "i.invoice_date", branch_id, from_date, to_date)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"""SELECT d.doctor_id, d.doctor_name, b.branch_name,
                       COUNT(DISTINCT i.appointment_id) AS appointment_count,
                       SUM(i.amount_paid + i.balance) AS total_revenue,
                       SUM(i.amount_paid) AS collected,
                       ROUND(SUM(i.amount_paid + i.balance) / COUNT(DISTINCT i.appointment_id), 2) AS avg_revenue
                FROM invoice i
                JOIN appointment a ON a.appointment_id = i.appointment_id
                JOIN doctor d ON d.doctor_id = a.doctor_id
                JOIN staff s ON s.staff_id = d.staff_id
                JOIN branch b ON b.branch_id = s.branch_id{where}
                GROUP BY d.doctor_id, d.doctor_name, b.branch_name
                ORDER BY total_revenue DESC, d.doctor_name;""",
            params,
        )
        return [DoctorRevenueResponse(**row) for row in await cur.fetchall()]


@router.get("/outstanding-balances", response_model=List[OutstandingBalanceResponse])
async def outstanding_balances(
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*REPORT_ROLES)),
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
    current_user: JWTPayload = Depends(require_role(*REPORT_ROLES)),
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
    current_user: JWTPayload = Depends(require_role(*REPORT_ROLES)),
):
    """Compare declared invoice payments and claim approvals, not insurer cash receipts."""
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
                       COALESCE(SUM(si.amount_paid), 0) AS out_of_pocket_amount,
                       COALESCE(SUM(si.balance), 0) AS outstanding_amount
                FROM scoped_invoices si
                LEFT JOIN claim_totals ct ON ct.invoice_id = si.invoice_id;""",
            params,
        )
        return InsuranceComparisonResponse(**(await cur.fetchone()))
