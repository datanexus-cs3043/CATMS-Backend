from datetime import date, time
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BranchBase(BaseModel):
    branch_name: str = Field(min_length=1, max_length=150)
    location: str = Field(min_length=1, max_length=255)
    contact_details: Optional[str] = Field(None, max_length=255)
    manager_staff_id: Optional[int] = None

    @field_validator("branch_name", "location", mode="before")
    @classmethod
    def trim_required_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class BranchCreate(BranchBase):
    pass


class BranchUpdate(BaseModel):
    branch_name: Optional[str] = Field(None, max_length=150)
    location: Optional[str] = Field(None, max_length=255)
    contact_details: Optional[str] = Field(None, max_length=255)
    manager_staff_id: Optional[int] = None

    @field_validator("branch_name", "location", mode="before")
    @classmethod
    def validate_provided_required_fields(cls, value):
        if value is None or isinstance(value, str) and not value.strip():
            raise ValueError("Provided branch fields cannot be null or blank")
        return value.strip() if isinstance(value, str) else value


class BranchResponse(BranchBase):
    branch_id: int

    model_config = ConfigDict(from_attributes=True)


class BranchStaffResponse(BaseModel):
    staff_id: int
    branch_id: int
    first_name: str
    last_name: str
    contact_details: Optional[str] = None
    email: str
    staff_type: str
    role: str

    model_config = ConfigDict(from_attributes=True)


class BranchDoctorResponse(BaseModel):
    doctor_id: int
    staff_id: int
    doctor_name: str
    doctor_license_number: str
    email: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BranchAppointmentResponse(BaseModel):
    appointment_id: int
    patient_id: int
    doctor_id: int
    branch_id: int
    appointment_date: date
    start_time: time
    end_time: time
    appointment_type: str
    created_by: str
    patient_name: Optional[str] = None
    doctor_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
