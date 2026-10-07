from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InsuranceProviderBase(BaseModel):
    provider_name: str = Field(min_length=1, max_length=200)
    contact_details: Optional[str] = Field(None, max_length=255)

    @field_validator("provider_name", mode="before")
    @classmethod
    def trim_provider_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class InsuranceProviderCreate(InsuranceProviderBase):
    pass


class InsuranceProviderUpdate(BaseModel):
    provider_name: Optional[str] = Field(None, min_length=1, max_length=200)
    contact_details: Optional[str] = Field(None, max_length=255)

    @field_validator("provider_name", mode="before")
    @classmethod
    def trim_provider_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class InsuranceProviderResponse(InsuranceProviderBase):
    provider_id: int

    model_config = ConfigDict(from_attributes=True)
