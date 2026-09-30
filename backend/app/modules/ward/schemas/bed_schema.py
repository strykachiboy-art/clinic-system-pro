from __future__ import annotations

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.core.enums.ward_enums import BedStatus


DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 500


class PaginationSchema(BaseModel):
    page: int = Field(
        default=DEFAULT_PAGE,
        ge=1,
    )

    per_page: int = Field(
        default=DEFAULT_PER_PAGE,
        ge=1,
        le=MAX_PER_PAGE,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class PaginationResponseSchema(BaseModel):
    total: int = Field(
        ...,
        ge=0,
    )

    page: int = Field(
        ...,
        ge=1,
    )

    per_page: int = Field(
        ...,
        ge=1,
        le=MAX_PER_PAGE,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


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
    under_maintenance: bool = Field(
        ...
    )

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )


class BedListQuerySchema(PaginationSchema):
    status: BedStatus | None = Field(
        default=None,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class BedResponseSchema(BaseModel):
    id: int = Field(
        ...,
        gt=0,
    )

    ward_id: int = Field(
        ...,
        gt=0,
    )

    bed_number: str = Field(
        ...,
        min_length=1,
        max_length=30,
    )

    status: BedStatus

    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )


class BedListResponseSchema(
    PaginationResponseSchema
):
    items: list[BedResponseSchema] = Field(
        default_factory=list,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class BedStatusResponseSchema(BaseModel):
    status: BedStatus

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )