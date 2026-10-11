from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PatientPaymentCreate(BaseModel):
    """Money a patient pays towards an invoice (full or partial)."""
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    payment_method: str = Field(default="Cash", min_length=1, max_length=50)
    reference_number: Optional[str] = Field(None, max_length=100)

    @field_validator("payment_method", "reference_number", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class PatientPaymentResponse(BaseModel):
    payment_id: int
    invoice_id: int
    payment_date: date
    amount: Decimal
    payment_method: str
    reference_number: Optional[str] = None
    payment_type: str
    received_by: Optional[int] = None
    received_by_name: Optional[str] = None
    patient_id: Optional[int] = None
    patient_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
