from enum import Enum
from typing import Optional, Any, Dict
from pydantic import BaseModel, Field, ConfigDict


class UserType(str, Enum):
    STAFF = "staff"
    PATIENT = "patient"


class UserRole(str, Enum):
    ADMIN = "admin"
    BRANCH_MANAGER = "branch_manager"
    DOCTOR = "doctor"
    RECEPTIONIST_CASHIER = "receptionist_cashier"
    PATIENT = "patient"


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, description="Username for login")
    password: str = Field(..., min_length=1, description="User password")


class AuthUser(BaseModel):
    user_id: int
    user_type: str
    role: str
    username: Optional[str] = None
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    staff_id: Optional[int] = None
    patient_id: Optional[int] = None
    doctor_id: Optional[int] = None
    branch_id: Optional[int] = None

    model_config = ConfigDict(extra="ignore")


class LoginResponse(BaseModel):
    message: str = "Login successful"
    user: AuthUser


class LogoutResponse(BaseModel):
    message: str = "Logout successful"


class CSRFResponse(BaseModel):
    csrf_token: str


class JWTPayload(BaseModel):
    user_id: int
    user_type: str
    role: str
    staff_id: Optional[int] = None
    patient_id: Optional[int] = None
    doctor_id: Optional[int] = None
    branch_id: Optional[int] = None
    exp: Optional[int] = None
    iat: Optional[int] = None

    model_config = ConfigDict(extra="ignore")

