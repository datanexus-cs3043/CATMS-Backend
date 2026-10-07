from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TreatmentCategoryBase(BaseModel):
    category_name: str = Field(min_length=1, max_length=150)
    description: Optional[str] = Field(None, max_length=500)

    @field_validator("category_name", mode="before")
    @classmethod
    def trim_category_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class TreatmentCategoryCreate(TreatmentCategoryBase):
    pass


class TreatmentCategoryUpdate(BaseModel):
    category_name: Optional[str] = Field(None, min_length=1, max_length=150)
    description: Optional[str] = Field(None, max_length=500)

    @field_validator("category_name", mode="before")
    @classmethod
    def trim_category_name(cls, value):
        if isinstance(value, str):
            value = value.strip()
        if value is None:
            raise ValueError("Provided category name cannot be null")
        return value


class TreatmentCategoryResponse(TreatmentCategoryBase):
    category_id: int

    model_config = ConfigDict(from_attributes=True)
