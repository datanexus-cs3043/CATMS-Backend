from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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


class InsuranceCoverageResponse(InsuranceCoverageBase):
    coverage_id: int
    treatment_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
