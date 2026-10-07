from datetime import date, time
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PaymentBase(BaseModel):
    """Doctor compensation, not a patient receipt or invoice settlement."""

    doctor_id: int = Field(gt=0)
    appointment_id: int = Field(gt=0)
    invoice_item_id: Optional[int] = Field(None, gt=0)
    date: date
    time: time
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class PaymentCreate(PaymentBase):
    pass


class PaymentUpdate(BaseModel):
    doctor_id: Optional[int] = Field(None, gt=0)
    appointment_id: Optional[int] = Field(None, gt=0)
    invoice_item_id: Optional[int] = Field(None, gt=0)
    date: Optional[date] = None
    time: Optional[time] = None
    amount: Optional[Decimal] = Field(None, gt=0, max_digits=10, decimal_places=2)

    @field_validator("doctor_id", "appointment_id", "date", "time", "amount", mode="before")
    @classmethod
    def validate_required_fields(cls, value):
        if value is None:
            raise ValueError("Provided doctor payment fields cannot be null")
        return value


class PaymentResponse(PaymentBase):
    payment_id: int

    model_config = ConfigDict(from_attributes=True)
