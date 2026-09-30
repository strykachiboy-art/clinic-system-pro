from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.core.enums.ambulance_enums import (
    TripStatus,
    TripType,
)


MAX_ADDRESS_LENGTH = 255
MAX_NOTES_LENGTH = 2000
MAX_CANCELLATION_REASON_LENGTH = 255


class AmbulanceTripRequestSchema(BaseModel):
    trip_type: TripType = Field(...)

    patient_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    admission_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    pickup_address: Optional[str] = Field(
        default=None,
        max_length=MAX_ADDRESS_LENGTH,
    )

    destination_address: Optional[str] = Field(
        default=None,
        max_length=MAX_ADDRESS_LENGTH,
    )

    notes: Optional[str] = Field(
        default=None,
        max_length=MAX_NOTES_LENGTH,
    )

    @field_validator(
        "pickup_address",
        "destination_address",
        "notes",
    )
    @classmethod
    def validate_optional_strings(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("Value cannot be blank")

        return value

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


class AmbulanceTripDispatchSchema(BaseModel):
    vehicle_id: int = Field(
        ...,
        gt=0,
    )

    driver_id: int = Field(
        ...,
        gt=0,
    )

    paramedic_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


class AmbulanceTripStatusSchema(BaseModel):
    status: TripStatus = Field(...)

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


class AmbulanceTripPatientSchema(BaseModel):
    patient_id: int = Field(
        ...,
        gt=0,
    )

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


class AmbulanceTripInvoiceSchema(BaseModel):
    invoice_id: int = Field(
        ...,
        gt=0,
    )

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


class AmbulanceTripCancelSchema(BaseModel):
    reason: str = Field(
        ...,
        min_length=1,
        max_length=MAX_CANCELLATION_REASON_LENGTH,
    )

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "Cancellation reason is required"
            )

        return value

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )