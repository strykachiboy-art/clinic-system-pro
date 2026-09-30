from __future__ import annotations

from datetime import date, datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.core.enums.ward_enums import (
    AdmissionStatus,
    BedStatus,
    ReservationStatus,
    WardType,
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
        min_length=1,
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


class WardListQuerySchema(PaginationSchema):
    ward_type: WardType | None = Field(
        default=None,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class BedListQuerySchema(PaginationSchema):
    status: BedStatus | None = Field(
        default=None,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class BedReservationListQuerySchema(PaginationSchema):
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


class AdmissionListQuerySchema(PaginationSchema):
    model_config = ConfigDict(
        extra="forbid",
    )


class WardResponseSchema(BaseModel):
    id: int = Field(
        ...,
        gt=0,
    )

    clinic_id: int = Field(
        ...,
        gt=0,
    )

    name: str = Field(
        ...,
        min_length=1,
        max_length=150,
    )

    ward_type: WardType

    capacity: int = Field(
        ...,
        ge=0,
    )

    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )


class WardListResponseSchema(
    PaginationResponseSchema
):
    items: list[WardResponseSchema] = Field(
        default_factory=list,
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

    reserved_at: datetime | None = None
    expires_at: datetime | None = None
    cancelled_at: datetime | None = None
    fulfilled_at: datetime | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None

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


class AdmissionResponseSchema(BaseModel):
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

    admitted_by_id: int = Field(
        ...,
        gt=0,
    )

    reservation_id: int | None = Field(
        default=None,
        gt=0,
    )

    status: AdmissionStatus

    reason: str | None = Field(
        default=None,
        max_length=255,
    )

    admitted_at: datetime | None = None
    discharged_at: datetime | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )


class AdmissionListResponseSchema(
    PaginationResponseSchema
):
    items: list[AdmissionResponseSchema] = Field(
        default_factory=list,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class WardTransferResponseSchema(BaseModel):
    id: int = Field(
        ...,
        gt=0,
    )

    admission_id: int = Field(
        ...,
        gt=0,
    )

    from_bed_id: int = Field(
        ...,
        gt=0,
    )

    to_bed_id: int = Field(
        ...,
        gt=0,
    )

    reason: str | None = Field(
        default=None,
        max_length=255,
    )

    transferred_at: datetime | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )


class WardOccupancyResponseSchema(BaseModel):
    ward_id: int = Field(
        ...,
        gt=0,
    )

    clinic_id: int = Field(
        ...,
        gt=0,
    )

    ward_name: str = Field(
        ...,
        min_length=1,
        max_length=150,
    )

    capacity: int = Field(
        ...,
        ge=0,
    )

    total_beds: int = Field(
        ...,
        ge=0,
    )

    occupied: int = Field(
        ...,
        ge=0,
    )

    available: int = Field(
        ...,
        ge=0,
    )

    reserved: int = Field(
        ...,
        ge=0,
    )

    maintenance: int = Field(
        ...,
        ge=0,
    )

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )