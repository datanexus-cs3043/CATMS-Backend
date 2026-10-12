from datetime import date, datetime, timedelta, timezone
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def validate_patient_birth_date(value: date) -> date:
    # Asia/Colombo uses UTC+05:30. A fixed offset works on Windows without tzdata.
    clinic_today = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    if value > clinic_today:
        raise ValueError("Date of birth cannot be in the future")
    return value


def normalize_patient_text(value):
    return value.strip() if isinstance(value, str) else value


def validate_patient_email(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    local, separator, domain = value.rpartition("@")
    if (not separator or not local or "@" in local or "." not in domain
            or domain.startswith(".") or domain.endswith(".")
            or any(character.isspace() for character in value)):
        raise ValueError("Enter a valid patient email")
    return value


class EmergencyContactBase(BaseModel):
    contact_name: str
    relationship: str
    phone: str


class EmergencyContactCreate(EmergencyContactBase):
    model_config = ConfigDict(extra="forbid")
    contact_name: str = Field(min_length=1, max_length=150)
    relationship: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=1, max_length=50)

    @field_validator("contact_name", "relationship", "phone", mode="before")
    @classmethod
    def trim_required_contact_fields(cls, value: str) -> str:
        if isinstance(value, str) and not value.strip():
            raise ValueError("Contact fields cannot be blank")
        return normalize_patient_text(value)


class EmergencyContactUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contact_name: Optional[str] = Field(None, max_length=150)
    relationship: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)

    @field_validator("contact_name", "relationship", "phone", mode="before")
    @classmethod
    def validate_provided_required_fields(cls, value):
        if value is None or isinstance(value, str) and not value.strip():
            raise ValueError("Provided contact fields cannot be null or blank")
        return value.strip() if isinstance(value, str) else value


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
    model_config = ConfigDict(extra="forbid")
    branch_id: int = Field(gt=0)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    gender: str = Field(min_length=1, max_length=50)
    patient_type: Optional[str] = Field(None, max_length=100)
    contact_details: Optional[str] = Field(None, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = Field(None, max_length=500)
    portal_username: Optional[str] = Field(None, min_length=3, max_length=100)
    emergency_contact: Optional[EmergencyContactCreate] = None

    @field_validator("first_name", "last_name", "gender", "portal_username", "patient_type", "contact_details", "email", "address", mode="before")
    @classmethod
    def trim_registration_fields(cls, value):
        return normalize_patient_text(value)

    @field_validator("date_of_birth")
    @classmethod
    def validate_birth_date(cls, value: date) -> date:
        return validate_patient_birth_date(value)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: Optional[str]) -> Optional[str]:
        return validate_patient_email(value)

    @model_validator(mode="after")
    def validate_portal_email(self):
        if self.portal_username is not None:
            if not self.email:
                raise ValueError("An account email is required for portal access")
        return self


class PatientUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_id: Optional[int] = Field(None, gt=0)
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(None, min_length=1, max_length=50)
    patient_type: Optional[str] = Field(None, max_length=100)
    contact_details: Optional[str] = Field(None, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = Field(None, max_length=500)

    @field_validator("first_name", "last_name", "gender", "patient_type", "contact_details", "email", "address", mode="before")
    @classmethod
    def trim_update_fields(cls, value):
        return normalize_patient_text(value)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: Optional[str]) -> Optional[str]:
        return validate_patient_email(value)

    @model_validator(mode="after")
    def validate_required_updates(self):
        for field in self.model_fields_set & {"branch_id", "first_name", "last_name", "date_of_birth", "gender"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        if self.date_of_birth is not None:
            validate_patient_birth_date(self.date_of_birth)
        return self


class PatientResponse(PatientBase):
    patient_id: int

    model_config = ConfigDict(from_attributes=True)


class PatientDetailResponse(PatientResponse):
    branch_name: Optional[str] = None
    emergency_contacts: List[EmergencyContactResponse] = []


class PatientRegistrationResponse(PatientResponse):
    portal_username: Optional[str] = None


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
