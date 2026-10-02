from typing import Optional

from pydantic import BaseModel, ConfigDict


class StaffBase(BaseModel):
    branch_id: int
    first_name: str
    last_name: str
    contact_details: Optional[str] = None
    email: str
    staff_type: str
    role: str
    users_logins_id: Optional[int] = None


class StaffCreate(StaffBase):
    pass


class StaffUpdate(BaseModel):
    branch_id: Optional[int] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    contact_details: Optional[str] = None
    email: Optional[str] = None
    staff_type: Optional[str] = None
    role: Optional[str] = None
    users_logins_id: Optional[int] = None


class StaffResponse(StaffBase):
    staff_id: int

    model_config = ConfigDict(from_attributes=True)