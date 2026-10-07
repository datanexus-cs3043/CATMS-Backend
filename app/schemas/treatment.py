from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TreatmentBase(BaseModel):
    category_id: int = Field(gt=0)
    service_code: str = Field(min_length=1, max_length=50)
    treatment_name: str = Field(min_length=1, max_length=150)
    standard_price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)

    @field_validator("service_code", "treatment_name", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class TreatmentCreate(TreatmentBase):
    pass


class TreatmentUpdate(BaseModel):
    category_id: Optional[int] = Field(None, gt=0)
    service_code: Optional[str] = Field(None, min_length=1, max_length=50)
    treatment_name: Optional[str] = Field(None, min_length=1, max_length=150)
    standard_price: Optional[Decimal] = Field(None, ge=0, max_digits=10, decimal_places=2)

    @field_validator("category_id", "service_code", "treatment_name", "standard_price", mode="before")
    @classmethod
    def validate_required_fields(cls, value):
        if value is None:
            raise ValueError("Provided treatment fields cannot be null")
        return value.strip() if isinstance(value, str) else value


class TreatmentResponse(TreatmentBase):
    treatment_id: int
    category_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
