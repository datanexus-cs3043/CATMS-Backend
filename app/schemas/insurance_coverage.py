from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InsuranceCoverageBase(BaseModel):
    policy_id: int = Field(gt=0)
    treatment_id: int = Field(gt=0)
    coverage_percentage: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)
    maximum_amount: Decimal = Field(ge=0, max_digits=10, decimal_places=2)


class InsuranceCoverageCreate(InsuranceCoverageBase):
    pass


class InsuranceCoverageUpdate(BaseModel):
    policy_id: Optional[int] = Field(None, gt=0)
    treatment_id: Optional[int] = Field(None, gt=0)
    coverage_percentage: Optional[Decimal] = Field(
        None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    maximum_amount: Optional[Decimal] = Field(
        None, ge=0, max_digits=10, decimal_places=2
    )

    @field_validator("policy_id", "treatment_id", "coverage_percentage", "maximum_amount", mode="before")
    @classmethod
    def validate_required_fields(cls, value):
        if value is None:
            raise ValueError("Provided insurance coverage fields cannot be null")
        return value


class InsuranceCoverageResponse(InsuranceCoverageBase):
    coverage_id: int
    treatment_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
