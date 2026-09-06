from pydantic import BaseModel, ConfigDict, Field

from app.core.enums.ward_enums import WardType


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

    model_config = ConfigDict(from_attributes=True)


class WardOccupancyResponseSchema(BaseModel):
    ward_id: int
    clinic_id: int
    ward_name: str
    capacity: int
    total_beds: int
    occupied: int
    available: int
    reserved: int
    maintenance: int

    model_config = ConfigDict(from_attributes=True)