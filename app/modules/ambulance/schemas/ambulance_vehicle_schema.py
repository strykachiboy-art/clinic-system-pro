from datetime import date
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.core.enums.ambulance_enums import (
    EquipmentLevel,
    VehicleStatus,
)


class AmbulanceVehicleCreateSchema(BaseModel):
    clinic_id: int = Field(
        ...,
        description="ID of the clinic",
    )

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
        description="Number of patients the ambulance can carry",
    )

    last_service_date: Optional[date] = Field(
        None,
        description="Date the ambulance was last serviced",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


class AmbulanceVehicleStatusSchema(BaseModel):
    status: VehicleStatus = Field(
        ...,
        description="New ambulance vehicle status",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )