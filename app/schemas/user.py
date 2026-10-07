from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=100, description="Unique username")
    password: str = Field(..., min_length=6, description="Plain text password (will be hashed with Argon2id)")
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=1, max_length=255)
    contact_details: Optional[str] = Field(None, max_length=255)

    @field_validator("username", "first_name", "last_name", "email", mode="before")
    @classmethod
    def trim_required_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class UserUpdate(BaseModel):
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=255)
    contact_details: Optional[str] = Field(None, max_length=255)
    password: Optional[str] = Field(None, min_length=6, description="Optional new password to update")

    @field_validator("first_name", "last_name", "email", "password", mode="before")
    @classmethod
    def validate_provided_required_fields(cls, value, info):
        if value is None:
            raise ValueError(f"{info.field_name} cannot be null")
        if isinstance(value, str) and info.field_name != "password":
            value = value.strip()
            if not value:
                raise ValueError(f"{info.field_name} cannot be blank")
        return value


class UserResponse(BaseModel):
    user_id: int
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    contact_details: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class LoginHistoryResponse(BaseModel):
    users_logins_id: int
    user_id: int
    login_time: datetime
    user_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
