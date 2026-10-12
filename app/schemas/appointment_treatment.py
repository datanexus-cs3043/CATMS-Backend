from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AppointmentTreatmentCreate(BaseModel):
    treatment_id: int = Field(gt=0)
    quantity: int = Field(default=1, gt=0, le=2147483647)


class AppointmentTreatmentResponse(BaseModel):
    appointment_treatment_id: int
    appointment_id: int
    treatment_id: int
    quantity: int
    unit_price: Decimal
    is_primary: bool
    treatment_name: Optional[str] = None
    service_code: Optional[str] = None
    category_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
