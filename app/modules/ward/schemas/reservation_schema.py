from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums.ward_enums import ReservationStatus


class BedReservationCreateSchema(BaseModel):
    patient_id: int = Field(..., gt=0)
    bed_id: int = Field(..., gt=0)
    reason: Optional[str] = Field(
        default=None,
        max_length=255,
    )
    expires_at: Optional[datetime] = Field(
        default=None,
    )

    model_config = ConfigDict(from_attributes=True)


class BedReservationCancelSchema(BaseModel):
    reason: Optional[str] = Field(
        default=None,
        max_length=255,
    )

    model_config = ConfigDict(from_attributes=True)


class BedReservationResponseSchema(BaseModel):
    id: int
    patient_id: int
    bed_id: int
    reserved_by_id: int
    status: ReservationStatus
    reason: Optional[str]
    reserved_at: datetime
    expires_at: Optional[datetime]
    cancelled_at: Optional[datetime]
    fulfilled_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)