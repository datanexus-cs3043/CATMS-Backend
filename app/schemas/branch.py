from datetime import date, time
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class BranchBase(BaseModel):
    branch_name: str
    location: str
    contact_details: Optional[str] = None
    manager_staff_id: Optional[int] = None


class BranchCreate(BranchBase):
    pass


class BranchUpdate(BaseModel):
    branch_name: Optional[str] = None
    location: Optional[str] = None
    contact_details: Optional[str] = None
    manager_staff_id: Optional[int] = None


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