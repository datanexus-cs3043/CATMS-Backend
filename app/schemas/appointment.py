from datetime import date, time, datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class ConsultationNoteBase(BaseModel):
    note_content: str


class ConsultationNoteCreate(ConsultationNoteBase):
    pass


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
