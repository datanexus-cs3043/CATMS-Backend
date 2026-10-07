from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InvoiceBase(BaseModel):
    appointment_id: int = Field(gt=0)
    staff_id: int = Field(gt=0)
    invoice_date: date
    amount_paid: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=10, decimal_places=2)
    balance: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=10, decimal_places=2)
    status: str = Field(min_length=1, max_length=100)

    @field_validator("status", mode="before")
    @classmethod
    def trim_status(cls, value):
        return value.strip() if isinstance(value, str) else value


class InvoiceCreate(InvoiceBase):
    pass


class InvoiceUpdate(BaseModel):
    staff_id: Optional[int] = Field(None, gt=0)
    invoice_date: Optional[date] = None
    amount_paid: Optional[Decimal] = Field(None, ge=0, max_digits=10, decimal_places=2)
    balance: Optional[Decimal] = Field(None, ge=0, max_digits=10, decimal_places=2)
    status: Optional[str] = Field(None, min_length=1, max_length=100)

    @field_validator("status", mode="before")
    @classmethod
    def trim_status(cls, value):
        return value.strip() if isinstance(value, str) else value


class InvoiceResponse(InvoiceBase):
    invoice_id: int
    patient_id: Optional[int] = None
    patient_name: Optional[str] = None
    doctor_name: Optional[str] = None
    appointment_date: Optional[date] = None

    model_config = ConfigDict(from_attributes=True)


class InvoiceItemBase(BaseModel):
    treatment_id: int = Field(gt=0)
    quantity: int = Field(default=1, gt=0)
    unitprice: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    description: Optional[str] = Field(None, max_length=255)


class InvoiceItemCreate(InvoiceItemBase):
    pass


class InvoiceItemUpdate(BaseModel):
    treatment_id: Optional[int] = Field(None, gt=0)
    quantity: Optional[int] = Field(None, gt=0)
    unitprice: Optional[Decimal] = Field(None, gt=0, max_digits=10, decimal_places=2)
    description: Optional[str] = Field(None, max_length=255)


class InvoiceItemResponse(InvoiceItemBase):
    invoice_item_id: int
    invoice_id: int
    treatment_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
