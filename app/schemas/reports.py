from datetime import date
from decimal import Decimal
from typing import List

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
    doctor_id: int
    doctor_name: str
    appointment_count: int
    invoice_count: int
    billed_revenue: Decimal
    collected_revenue: Decimal

    model_config = ConfigDict(from_attributes=True)


class OutstandingBalanceResponse(BaseModel):
    invoice_id: int
    patient_id: int
    patient_name: str
    invoice_date: date
    balance: Decimal
    status: str


class TreatmentCategoryReportResponse(BaseModel):
    category_id: int
    category_name: str
    treatment_count: int
    usage_count: int
    treatment_revenue: Decimal


class InsuranceComparisonResponse(BaseModel):
    invoiced_amount: Decimal
    insurance_approved_amount: Decimal
    patient_paid_amount: Decimal
    out_of_pocket_amount: Decimal
    outstanding_amount: Decimal
