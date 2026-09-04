from decimal import Decimal
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.core.enums.ambulance_enums import (
    TripStatus,
    TripType,
)


class AmbulanceTripRequestSchema(BaseModel):
    clinic_id: int = Field(
        ...,
        description="ID of the clinic",
    )

    trip_type: TripType = Field(
        ...,
        description="Type of ambulance trip",
    )

    patient_id: Optional[int] = Field(
        None,
        description=(
            "ID of the patient, if already identified"
        ),
    )

    admission_id: Optional[int] = Field(
        None,
        description=(
            "ID of the admission associated "
            "with the ambulance trip"
        ),
    )

    pickup_address: Optional[str] = Field(
        None,
        max_length=255,
    )

    pickup_lat: Optional[Decimal] = Field(
        None,
        ge=Decimal("-90"),
        le=Decimal("90"),
    )

    pickup_lng: Optional[Decimal] = Field(
        None,
        ge=Decimal("-180"),
        le=Decimal("180"),
    )

    destination_address: Optional[str] = Field(
        None,
        max_length=255,
    )

    destination_lat: Optional[Decimal] = Field(
        None,
        ge=Decimal("-90"),
        le=Decimal("90"),
    )

    destination_lng: Optional[Decimal] = Field(
        None,
        ge=Decimal("-180"),
        le=Decimal("180"),
    )

    notes: Optional[str] = Field(
        None,
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


class AmbulanceTripDispatchSchema(BaseModel):
    vehicle_id: int = Field(
        ...,
        description="ID of the ambulance vehicle",
    )

    driver_id: int = Field(
        ...,
        description="ID of the driver",
    )

    paramedic_id: Optional[int] = Field(
        None,
        description=(
            "ID of the paramedic or EMT"
        ),
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


class AmbulanceTripStatusSchema(BaseModel):
    status: TripStatus = Field(
        ...,
        description=(
            "Next status in the ambulance "
            "trip lifecycle"
        ),
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


class AmbulanceTripPatientSchema(BaseModel):
    patient_id: int = Field(
        ...,
        description="ID of the patient",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


class AmbulanceTripInvoiceSchema(BaseModel):
    invoice_id: int = Field(
        ...,
        description="ID of the invoice",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


class AmbulanceTripCancelSchema(BaseModel):
    reason: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description=(
            "Reason for cancelling the ambulance trip"
        ),
    )

    model_config = ConfigDict(
        from_attributes=True,
    )