from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AdmissionCreateSchema(BaseModel):
    patient_id: int = Field(...)
    bed_id: int = Field(...)
    admitted_by_id: int = Field(...)
    reason: Optional[str] = Field(None)

    model_config = ConfigDict(from_attributes=True)


class AdmissionFromReservationSchema(BaseModel):
    admitted_by_id: int = Field(...)
    reason: Optional[str] = Field(
        None,
        max_length=255,
    )

    model_config = ConfigDict(from_attributes=True)


class AdmissionDischargeSchema(BaseModel):
    reason: Optional[str] = Field(
        None,
        max_length=255,
    )

    model_config = ConfigDict(from_attributes=True)


class AdmissionTransferSchema(BaseModel):
    to_bed_id: int = Field(...)
    reason: Optional[str] = Field(
        None,
        max_length=255,
    )

    model_config = ConfigDict(from_attributes=True)