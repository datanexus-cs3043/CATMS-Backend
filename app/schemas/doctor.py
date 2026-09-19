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
