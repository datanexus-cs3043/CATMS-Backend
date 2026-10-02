from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StaffBase(BaseModel):
    branch_id: int
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    contact_details: Optional[str] = Field(None, max_length=255)
    email: str = Field(min_length=1, max_length=255)
    staff_type: str = Field(min_length=1, max_length=100)
    role: str = Field(min_length=1, max_length=100)
    users_logins_id: Optional[int] = None


class StaffCreate(StaffBase):
    @field_validator("first_name", "last_name", "email", "staff_type", "role", mode="before")
    @classmethod
    def trim_required_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class StaffUpdate(BaseModel):
    branch_id: Optional[int] = None
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    contact_details: Optional[str] = Field(None, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    staff_type: Optional[str] = Field(None, max_length=100)
    role: Optional[str] = Field(None, max_length=100)
    users_logins_id: Optional[int] = None

    @field_validator("branch_id", "first_name", "last_name", "email", "staff_type", "role", mode="before")
    @classmethod
    def validate_provided_required_fields(cls, value):
        if value is None or isinstance(value, str) and not value.strip():
            raise ValueError("Provided required staff fields cannot be null or blank")
        return value.strip() if isinstance(value, str) else value


class StaffResponse(StaffBase):
    staff_id: int

    model_config = ConfigDict(from_attributes=True)
