from datetime import date, time
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class SpecialtyBase(BaseModel):
    specialty_name: str
    description: Optional[str] = None


class SpecialtyCreate(SpecialtyBase):
    pass


class SpecialtyResponse(SpecialtyBase):
    specialty_id: int

    model_config = ConfigDict(from_attributes=True)


class DoctorBase(BaseModel):
    staff_id: int
    doctor_name: str
    doctor_license_number: str


class DoctorCreate(DoctorBase):
    pass


class DoctorUpdate(BaseModel):
    doctor_name: Optional[str] = None
    doctor_license_number: Optional[str] = None


class DoctorResponse(DoctorBase):
    doctor_id: int

    model_config = ConfigDict(from_attributes=True)


class DoctorDetailResponse(DoctorResponse):
    branch_id: Optional[int] = None
    branch_name: Optional[str] = None
    email: Optional[str] = None
    contact_details: Optional[str] = None
    specialties: List[SpecialtyResponse] = []


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
