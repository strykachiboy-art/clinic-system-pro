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


# ============================================================================
# Ambulance Trip Schemas
# ============================================================================


class AmbulanceTripRequestSchema(BaseModel):
    """
    Request schema for creating an ambulance trip.
    """

    trip_type: TripType = Field(
        ...,
        description="Type of ambulance trip",
    )

    patient_id: Optional[int] = Field(
        default=None,
        gt=0,
        description=(
            "ID of the patient, if already identified"
        ),
    )

    admission_id: Optional[int] = Field(
        default=None,
        gt=0,
        description=(
            "ID of the admission associated "
            "with the ambulance trip"
        ),
    )

    pickup_address: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Pickup location/address",
    )

    destination_address: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Destination location/address",
    )

    notes: Optional[str] = Field(
        default=None,
        description="Additional notes for the ambulance trip",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


class AmbulanceTripDispatchSchema(BaseModel):
    """
    Assigns an ambulance vehicle and crew to a requested trip.
    """

    vehicle_id: int = Field(
        ...,
        gt=0,
        description="ID of the ambulance vehicle",
    )

    driver_id: int = Field(
        ...,
        gt=0,
        description="ID of the driver",
    )

    paramedic_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="ID of the paramedic or EMT",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


class AmbulanceTripStatusSchema(BaseModel):
    """
    Requests the next valid status in the ambulance
    trip lifecycle.
    """

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
    """
    Links a patient to an ambulance trip.
    """

    patient_id: int = Field(
        ...,
        gt=0,
        description="ID of the patient",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


class AmbulanceTripInvoiceSchema(BaseModel):
    """
    Links an invoice to a completed ambulance trip.
    """

    invoice_id: int = Field(
        ...,
        gt=0,
        description="ID of the invoice",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


class AmbulanceTripCancelSchema(BaseModel):
    """
    Cancels an ambulance trip.
    """

    reason: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Reason for cancelling the ambulance trip",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )