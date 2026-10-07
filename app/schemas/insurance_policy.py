from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InsurancePolicyBase(BaseModel):
    patient_id: int = Field(gt=0)
    provider_id: int = Field(gt=0)
    policy_number: int = Field(gt=0)
    start_date: date
    end_date: date
    status: str = Field(min_length=1, max_length=100)

    @field_validator("status", mode="before")
    @classmethod
    def trim_status(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, value, info):
        start_date = info.data.get("start_date")
        if start_date is not None and value < start_date:
            raise ValueError("end_date must be on or after start_date")
        return value


class InsurancePolicyCreate(InsurancePolicyBase):
    pass


class InsurancePolicyUpdate(BaseModel):
    patient_id: Optional[int] = Field(None, gt=0)
    provider_id: Optional[int] = Field(None, gt=0)
    policy_number: Optional[int] = Field(None, gt=0)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = Field(None, min_length=1, max_length=100)

    @field_validator("patient_id", "provider_id", "policy_number", "start_date", "end_date", "status", mode="before")
    @classmethod
    def validate_required_fields(cls, value):
        if value is None:
            raise ValueError("Provided insurance policy fields cannot be null")
        return value.strip() if isinstance(value, str) else value


class InsurancePolicyResponse(InsurancePolicyBase):
    policy_id: int
    provider_name: Optional[str] = None
    patient_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
