from datetime import date, time, datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def validate_appointment_times(start_time: time, end_time: time) -> None:
    if start_time.tzinfo is not None or end_time.tzinfo is not None:
        raise ValueError("Appointment times must be local times without a timezone")
    if end_time <= start_time:
        raise ValueError("end_time must be after start_time")


class ConsultationNoteBase(BaseModel):
    note_content: str


class ConsultationNoteCreate(ConsultationNoteBase):
    note_content: str = Field(min_length=1)

    @field_validator("note_content")
    @classmethod
    def validate_note(cls, value):
        if not value.strip():
            raise ValueError("Consultation note cannot be blank")
        return value


class ConsultationNoteUpdate(BaseModel):
    note_content: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_note(self):
        if not self.note_content.strip():
            raise ValueError("Consultation note cannot be blank")
        return self


class RescheduleRequest(BaseModel):
    appointment_date: date
    start_time: time
    end_time: time
    created_by: Optional[str] = Field(None, deprecated=True, description="Ignored; derived from authenticated user")

    @model_validator(mode="after")
    def validate_times(self):
        validate_appointment_times(self.start_time, self.end_time)
        return self


class EmergencyAppointmentCreate(BaseModel):
    patient_id: int = Field(gt=0)
    doctor_id: int = Field(gt=0)
    branch_id: int = Field(gt=0)
    appointment_date: date
    start_time: time
    end_time: time
    created_by: Optional[str] = Field(None, deprecated=True, description="Ignored; derived from authenticated user")
    treatment_id: Optional[int] = Field(None, gt=0)

    @model_validator(mode="after")
    def validate_times(self):
        validate_appointment_times(self.start_time, self.end_time)
        return self


class ConsultationNoteResponse(ConsultationNoteBase):
    note_id: int
    appointment_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppointmentBase(BaseModel):
    patient_id: int
    doctor_id: int
    branch_id: int
    appointment_date: date
    start_time: time
    end_time: time
    appointment_type: str
    created_by: str
    original_appointment_id: Optional[int] = None
    treatment_id: Optional[int] = None


class AppointmentCreate(AppointmentBase):
    patient_id: int = Field(gt=0)
    doctor_id: int = Field(gt=0)
    branch_id: int = Field(gt=0)
    appointment_type: str = Field(min_length=1, max_length=100)
    original_appointment_id: Optional[int] = Field(None, gt=0)
    treatment_id: Optional[int] = Field(None, gt=0)
    created_by: Optional[str] = Field(
        None,
        deprecated=True,
        description="Ignored; derived from authenticated user",
    )

    @field_validator("appointment_type")
    @classmethod
    def validate_type(cls, value):
        if not value.strip():
            raise ValueError("Appointment type cannot be blank")
        return value.strip()

    @model_validator(mode="after")
    def validate_times(self):
        validate_appointment_times(self.start_time, self.end_time)
        return self


class AppointmentUpdate(BaseModel):
    doctor_id: Optional[int] = Field(None, gt=0)
    branch_id: Optional[int] = Field(None, gt=0)
    appointment_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    appointment_type: Optional[str] = Field(None, min_length=1, max_length=100)
    treatment_id: Optional[int] = Field(None, gt=0)

    @model_validator(mode="after")
    def validate_update(self):
        for field in self.model_fields_set - {"treatment_id"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        if self.appointment_type is not None:
            self.appointment_type = self.appointment_type.strip()
            if not self.appointment_type:
                raise ValueError("Appointment type cannot be blank")
        for value in (self.start_time, self.end_time):
            if value is not None and value.tzinfo is not None:
                raise ValueError("Appointment times must be local times without a timezone")
        if self.start_time is not None and self.end_time is not None:
            validate_appointment_times(self.start_time, self.end_time)
        return self


class AppointmentResponse(AppointmentBase):
    appointment_id: int
    invoice_id: Optional[int] = None
    rescheduled_to: Optional[int] = None
    status: Literal["Scheduled", "Completed", "Cancelled"] = "Scheduled"
    patient_name: Optional[str] = None
    doctor_name: Optional[str] = None
    branch_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AppointmentDetailResponse(AppointmentResponse):
    patient_name: Optional[str] = None
    doctor_name: Optional[str] = None
    branch_name: Optional[str] = None
    treatment_name: Optional[str] = None
    consultation_notes: List[ConsultationNoteResponse] = Field(default_factory=list)
