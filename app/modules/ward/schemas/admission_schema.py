from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AdmissionCreateSchema(BaseModel):
    patient_id: int = Field(..., gt=0)
    bed_id: int = Field(..., gt=0)
    reason: Optional[str] = Field(
        default=None,
        max_length=255,
    )

    model_config = ConfigDict(from_attributes=True)


class AdmissionFromReservationSchema(BaseModel):
    reason: Optional[str] = Field(
        default=None,
        max_length=255,
    )

    model_config = ConfigDict(from_attributes=True)


class AdmissionDischargeSchema(BaseModel):
    reason: Optional[str] = Field(
        default=None,
        max_length=255,
    )

    model_config = ConfigDict(from_attributes=True)


class AdmissionTransferSchema(BaseModel):
    to_bed_id: int = Field(..., gt=0)
    reason: Optional[str] = Field(
        default=None,
        max_length=255,
    )

    model_config = ConfigDict(from_attributes=True)