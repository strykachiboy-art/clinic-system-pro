from datetime import date
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.core.enums.ambulance_enums import (
    EquipmentLevel,
    TripStatus,
    TripType,
    VehicleStatus,
)


# ============================================================================
# Ambulance Trip Schemas
# ============================================================================


class AmbulanceTripRequestSchema(BaseModel):
    """
    Request schema for creating an ambulance trip.

    clinic_id is intentionally excluded.
    The clinic is derived from the authenticated user's JWT context
    by the route layer.
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
        description=(
            "ID of the paramedic or EMT"
        ),
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
        description=(
            "Reason for cancelling the ambulance trip"
        ),
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


# ============================================================================
# Ambulance Vehicle Schemas
# ============================================================================


class AmbulanceVehicleCreateSchema(BaseModel):
    """
    Request schema for registering an ambulance vehicle.

    clinic_id is intentionally excluded.
    The clinic is derived from the authenticated user's JWT context.
    """

    plate_number: str = Field(
        ...,
        min_length=1,
        max_length=30,
        description="Unique ambulance plate number",
    )

    equipment_level: EquipmentLevel = Field(
        default=EquipmentLevel.BLS,
        description="Ambulance equipment level",
    )

    capacity: int = Field(
        default=1,
        ge=1,
        description=(
            "Number of patients the ambulance can carry"
        ),
    )

    last_service_date: Optional[date] = Field(
        default=None,
        description="Date the ambulance was last serviced",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


class AmbulanceVehicleStatusSchema(BaseModel):
    """
    Changes the current status of an ambulance vehicle.
    """

    status: VehicleStatus = Field(
        ...,
        description="New ambulance vehicle status",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )