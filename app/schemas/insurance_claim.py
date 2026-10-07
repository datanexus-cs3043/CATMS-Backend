from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InsuranceClaimBase(BaseModel):
    invoice_id: int = Field(gt=0)
    policy_id: int = Field(gt=0)
    claim_date: date
    claim_amount: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    approved_amount: Decimal = Field(
        default=Decimal("0.00"), ge=0, max_digits=10, decimal_places=2
    )
    status: str = Field(min_length=1, max_length=100)

    @field_validator("status", mode="before")
    @classmethod
    def trim_status(cls, value):
        return value.strip() if isinstance(value, str) else value


class InsuranceClaimCreate(InsuranceClaimBase):
    pass


class InsuranceClaimUpdate(BaseModel):
    invoice_id: Optional[int] = Field(None, gt=0)
    policy_id: Optional[int] = Field(None, gt=0)
    claim_date: Optional[date] = None
    claim_amount: Optional[Decimal] = Field(None, ge=0, max_digits=10, decimal_places=2)
    approved_amount: Optional[Decimal] = Field(
        None, ge=0, max_digits=10, decimal_places=2
    )
    status: Optional[str] = Field(None, min_length=1, max_length=100)

    @field_validator("invoice_id", "policy_id", "claim_date", "claim_amount", "approved_amount", "status", mode="before")
    @classmethod
    def validate_required_fields(cls, value):
        if value is None:
            raise ValueError("Provided insurance claim fields cannot be null")
        return value.strip() if isinstance(value, str) else value


class InsuranceClaimResponse(InsuranceClaimBase):
    claim_id: int
    patient_id: Optional[int] = None
    patient_name: Optional[str] = None
    policy_number: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)
