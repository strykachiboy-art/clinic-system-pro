from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

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

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )

    @field_validator("reason")
    @classmethod
    def normalize_reason(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None

        value = value.strip()

        return value or None


class BedReservationCancelSchema(BaseModel):
    reason: Optional[str] = Field(
        default=None,
        max_length=255,
    )

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )

    @field_validator("reason")
    @classmethod
    def normalize_reason(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None

        value = value.strip()

        return value or None


class BedReservationResponseSchema(BaseModel):
    id: int = Field(..., gt=0)
    patient_id: int = Field(..., gt=0)
    bed_id: int = Field(..., gt=0)
    reserved_by_id: int = Field(..., gt=0)
    status: ReservationStatus
    reason: Optional[str] = None
    reserved_at: datetime
    expires_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    fulfilled_at: Optional[datetime] = None

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )