from pydantic import BaseModel, Field


class AppointmentTreatmentCreate(BaseModel):
    treatment_id: int = Field(gt=0)
