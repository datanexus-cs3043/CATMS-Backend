from datetime import date
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class EmergencyContactBase(BaseModel):
    contact_name: str
    relationship: str
    phone: str


class EmergencyContactCreate(EmergencyContactBase):
    pass


class EmergencyContactUpdate(BaseModel):
    contact_name: Optional[str] = None
    relationship: Optional[str] = None
    phone: Optional[str] = None


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


class PatientInvoiceResponse(BaseModel):
    invoice_id: int
    appointment_id: Optional[int] = None
    staff_id: Optional[int] = None
    invoice_date: Optional[date] = None
    amount_paid: Optional[float] = None
    balance: Optional[float] = None
    status: Optional[str] = None
    doctor_name: Optional[str] = None
    appointment_date: Optional[date] = None

    model_config = ConfigDict(from_attributes=True)


class PatientInsuranceCoverageResponse(BaseModel):
    coverage_id: int
    policy_id: int
    treatment_id: int
    treatment_name: Optional[str] = None
    coverage_percentage: Optional[float] = None
    maximum_amount: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class PatientInsurancePolicyResponse(BaseModel):
    policy_id: int
    patient_id: int
    provider_id: Optional[int] = None
    provider_name: Optional[str] = None
    policy_number: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None
    coverages: List[PatientInsuranceCoverageResponse] = []

    model_config = ConfigDict(from_attributes=True)
