from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums.ward_enums import BedStatus


class BedCreateSchema(BaseModel):
    bed_number: str = Field(
        ...,
        min_length=1,
        max_length=30,
    )

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )

    @field_validator("bed_number")
    @classmethod
    def validate_bed_number(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "bed_number is required"
            )

        return value


class BedMaintenanceSchema(BaseModel):
    under_maintenance: bool = Field(...)

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )


class BedStatusResponseSchema(BaseModel):
    status: BedStatus

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )