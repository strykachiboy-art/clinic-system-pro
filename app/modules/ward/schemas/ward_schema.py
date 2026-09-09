from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums.ward_enums import WardType


class WardCreateSchema(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=150,
    )

    ward_type: WardType = Field(
        default=WardType.GENERAL,
    )

    capacity: int = Field(
        default=0,
        ge=0,
    )

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )

    @field_validator("name")
    @classmethod
    def validate_name(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "Ward name is required"
            )

        return value


class WardUpdateSchema(BaseModel):
    name: str | None = Field(
        default=None,
        max_length=150,
    )

    ward_type: WardType | None = Field(
        default=None,
    )

    capacity: int | None = Field(
        default=None,
        ge=0,
    )

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )

    @field_validator("name")
    @classmethod
    def validate_name(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError(
                "Ward name cannot be empty"
            )

        return value


class WardOccupancyResponseSchema(BaseModel):
    ward_id: int = Field(..., gt=0)
    clinic_id: int = Field(..., gt=0)
    ward_name: str
    capacity: int = Field(..., ge=0)
    total_beds: int = Field(..., ge=0)
    occupied: int = Field(..., ge=0)
    available: int = Field(..., ge=0)
    reserved: int = Field(..., ge=0)
    maintenance: int = Field(..., ge=0)

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )