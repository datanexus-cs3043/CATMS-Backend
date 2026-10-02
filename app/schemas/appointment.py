from datetime import date, time, datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConsultationNoteBase(BaseModel):
    note_content: str


class ConsultationNoteCreate(ConsultationNoteBase):
    pass


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
        if self.start_time.tzinfo is not None or self.end_time.tzinfo is not None:
            raise ValueError("Appointment times must be local times without a timezone")
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class EmergencyAppointmentCreate(BaseModel):
    patient_id: int
    doctor_id: int
    branch_id: int
    appointment_date: date
    start_time: time
    end_time: time
    created_by: Optional[str] = Field(None, deprecated=True, description="Ignored; derived from authenticated user")
    treatment_id: Optional[int] = None

    @model_validator(mode="after")
    def validate_times(self):
        if self.start_time.tzinfo is not None or self.end_time.tzinfo is not None:
            raise ValueError("Appointment times must be local times without a timezone")
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
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
    pass


class AppointmentUpdate(BaseModel):
    doctor_id: Optional[int] = None
    branch_id: Optional[int] = None
    appointment_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    appointment_type: Optional[str] = None
    treatment_id: Optional[int] = None


class AppointmentResponse(AppointmentBase):
    appointment_id: int

    model_config = ConfigDict(from_attributes=True)


class AppointmentDetailResponse(AppointmentResponse):
    patient_name: Optional[str] = None
    doctor_name: Optional[str] = None
    branch_name: Optional[str] = None
    treatment_name: Optional[str] = None
    consultation_notes: List[ConsultationNoteResponse] = []
