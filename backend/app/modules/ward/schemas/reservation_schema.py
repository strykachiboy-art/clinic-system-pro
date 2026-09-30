from __future__ import annotations

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.core.enums.ward_enums import (
    ReservationStatus,
)


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


class BedReservationCreateSchema(BaseModel):
    patient_id: int = Field(
        ...,
        gt=0,
    )

    bed_id: int = Field(
        ...,
        gt=0,
    )

    reason: str | None = Field(
        default=None,
        max_length=255,
    )

    expires_at: datetime | None = Field(
        default=None,
    )

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )

    @field_validator("reason")
    @classmethod
    def normalize_reason(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None


class BedReservationCancelSchema(BaseModel):
    reason: str | None = Field(
        default=None,
        max_length=255,
    )

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )

    @field_validator("reason")
    @classmethod
    def normalize_reason(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None


class BedReservationListQuerySchema(
    PaginationSchema
):
    status: ReservationStatus | None = Field(
        default=None,
    )

    patient_id: int | None = Field(
        default=None,
        gt=0,
    )

    bed_id: int | None = Field(
        default=None,
        gt=0,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class BedReservationResponseSchema(BaseModel):
    id: int = Field(
        ...,
        gt=0,
    )

    patient_id: int = Field(
        ...,
        gt=0,
    )

    bed_id: int = Field(
        ...,
        gt=0,
    )

    reserved_by_id: int = Field(
        ...,
        gt=0,
    )

    status: ReservationStatus

    reason: str | None = Field(
        default=None,
        max_length=255,
    )

    reserved_at: datetime

    expires_at: datetime | None = None

    cancelled_at: datetime | None = None

    fulfilled_at: datetime | None = None

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )


class BedReservationListResponseSchema(
    PaginationResponseSchema
):
    items: list[
        BedReservationResponseSchema
    ] = Field(
        default_factory=list,
    )

    model_config = ConfigDict(
        extra="forbid",
    )