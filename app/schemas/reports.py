from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class BranchDailySummaryResponse(BaseModel):
    """Report 1: appointments per branch per day by status."""
    branch_id: int
    branch_name: str
    appointment_date: date
    scheduled: int
    completed: int
    cancelled: int
    total: int


class DoctorRevenueResponse(BaseModel):
    """Report 2: revenue per doctor from invoices in the period."""
    doctor_id: int
    doctor_name: str
    branch_id: int
    branch_name: str
    appointment_count: int
    total_revenue: Decimal
    collected: Decimal
    avg_revenue: Decimal

    model_config = ConfigDict(from_attributes=True)


class OutstandingBalanceResponse(BaseModel):
    """Report 3: one row per patient who still owes money."""
    patient_id: int
    patient_name: str
    contact_details: Optional[str] = None
    total_outstanding: Decimal
    invoice_count: int
    oldest_invoice_date: date


class TreatmentCategoryReportResponse(BaseModel):
    """Report 4: how many times each treatment (grouped by category) was given."""
    category_id: int
    category_name: str
    treatment_id: int
    treatment_name: str
    count: int
    total_revenue: Decimal


class InsuranceComparisonResponse(BaseModel):
    """Current values for an invoice-date cohort; out_of_pocket_amount is the legacy net-payment alias.

    Approved claims are coverage decisions, not insurer receipts. Estimated patient
    exposure is invoiced_amount minus insurance_approved_amount, not cash paid.
    """
    invoiced_amount: Decimal
    insurance_approved_amount: Decimal
    patient_paid_amount: Decimal
    out_of_pocket_amount: Decimal
    outstanding_amount: Decimal
