from datetime import date
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.core.enums.ambulance_enums import (
    EquipmentLevel,
    VehicleStatus,
)


MAX_PLATE_NUMBER_LENGTH = 30


class AmbulanceVehicleCreateSchema(BaseModel):
    plate_number: str = Field(
        ...,
        min_length=1,
        max_length=MAX_PLATE_NUMBER_LENGTH,
    )

    equipment_level: EquipmentLevel = Field(
        default=EquipmentLevel.BLS,
    )

    capacity: int = Field(
        default=1,
        ge=1,
    )

    last_service_date: Optional[date] = Field(
        default=None,
    )

    @field_validator("plate_number")
    @classmethod
    def validate_plate_number(cls, value: str) -> str:
        value = value.strip().upper()

        if not value:
            raise ValueError(
                "Plate number is required"
            )

        return value

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


class AmbulanceVehicleStatusSchema(BaseModel):
    status: VehicleStatus = Field(...)

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )