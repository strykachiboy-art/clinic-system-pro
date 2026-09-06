from pydantic import BaseModel, ConfigDict, Field

from app.core.enums.ward_enums import BedStatus


class BedCreateSchema(BaseModel):
    bed_number: str = Field(
        ...,
        min_length=1,
        max_length=30,
    )

    model_config = ConfigDict(from_attributes=True)


class BedMaintenanceSchema(BaseModel):
    under_maintenance: bool = Field(...)

    model_config = ConfigDict(from_attributes=True)


class BedStatusResponseSchema(BaseModel):
    status: BedStatus

    model_config = ConfigDict(from_attributes=True)