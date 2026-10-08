from datetime import date, time
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SpecialtyBase(BaseModel):
    specialty_name: str
    description: Optional[str] = None


class SpecialtyCreate(SpecialtyBase):
    pass


class DoctorSpecialtyCreate(SpecialtyCreate):
    specialty_name: str = Field(min_length=1, max_length=150)
    description: Optional[str] = Field(None, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("specialty_name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class SpecialtyUpdate(BaseModel):
    specialty_name: Optional[str] = None
    description: Optional[str] = None


class SpecialtyResponse(SpecialtyBase):
    specialty_id: int

    model_config = ConfigDict(from_attributes=True)


class DoctorBase(BaseModel):
    staff_id: int = Field(gt=0)
    doctor_name: str = Field(min_length=1, max_length=150)
    doctor_license_number: str = Field(min_length=1, max_length=100)

    @field_validator("doctor_name", "doctor_license_number", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class DoctorCreate(DoctorBase):
    model_config = ConfigDict(extra="forbid")


class DoctorUpdate(BaseModel):
    doctor_name: Optional[str] = Field(None, min_length=1, max_length=150)
    doctor_license_number: Optional[str] = Field(None, min_length=1, max_length=100)

    model_config = ConfigDict(extra="forbid")

    @field_validator("doctor_name", "doctor_license_number", mode="before")
    @classmethod
    def validate_supplied_text(cls, value):
        if value is None:
            raise ValueError("Supplied doctor fields cannot be null")
        return value.strip() if isinstance(value, str) else value


class DoctorResponse(DoctorBase):
    doctor_id: int

    model_config = ConfigDict(from_attributes=True)


class DoctorDirectoryResponse(DoctorResponse):
    branch_id: int
    branch_name: str
    email: Optional[str] = None
    contact_details: Optional[str] = None
    specialties: List[SpecialtyResponse] = Field(default_factory=list)


class DoctorDetailResponse(DoctorResponse):
    branch_id: Optional[int] = None
    branch_name: Optional[str] = None
    email: Optional[str] = None
    contact_details: Optional[str] = None
    specialties: List[SpecialtyResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

class DoctorAppointmentResponse(BaseModel):
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
    branch_name: Optional[str] = None
    treatment_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DoctorAvailabilitySlot(BaseModel):
    appointment_date: date
    booked_slots: List[str] = []  # List of "HH:MM-HH:MM" strings

    model_config = ConfigDict(from_attributes=True)
