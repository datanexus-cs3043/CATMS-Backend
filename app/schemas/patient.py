from datetime import date
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class EmergencyContactBase(BaseModel):
    contact_name: str
    relationship: str
    phone: str


class EmergencyContactCreate(EmergencyContactBase):
    pass


class EmergencyContactResponse(EmergencyContactBase):
    emergency_contact_id: int
    patient_id: int

    model_config = ConfigDict(from_attributes=True)


class PatientBase(BaseModel):
    branch_id: int
    first_name: str
    last_name: str
    date_of_birth: date
    gender: str
    patient_type: Optional[str] = None
    contact_details: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None


class PatientCreate(PatientBase):
    pass


class PatientUpdate(BaseModel):
    branch_id: Optional[int] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    patient_type: Optional[str] = None
    contact_details: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None


class PatientResponse(PatientBase):
    patient_id: int

    model_config = ConfigDict(from_attributes=True)


class PatientDetailResponse(PatientResponse):
    branch_name: Optional[str] = None
    emergency_contacts: List[EmergencyContactResponse] = []
