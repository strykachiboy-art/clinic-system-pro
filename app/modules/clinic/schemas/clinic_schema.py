from datetime import time
from typing import Optional
from pydantic import BaseModel, Field

from app.core.enums.clinic_enums import ClinicStatus, ClinicType


class ClinicCreateSchema(BaseModel):
    name: str = Field(..., max_length=150)
    clinic_type: ClinicType = Field(default=ClinicType.GENERAL)

    parent_clinic_id: Optional[int] = Field(None, description="Set for a branch of an existing clinic")
    is_headquarters: bool = Field(False)

    address: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=30)
    email: Optional[str] = Field(None)

    timezone: str = Field(default="UTC", max_length=50)
    opening_time: Optional[time] = Field(None)
    closing_time: Optional[time] = Field(None)

    class Config:
        from_attributes = True


class ClinicUpdateSchema(BaseModel):
    name: Optional[str] = Field(None, max_length=150)
    clinic_type: Optional[ClinicType] = Field(None)
    status: Optional[ClinicStatus] = Field(None)

    parent_clinic_id: Optional[int] = Field(None)
    is_headquarters: Optional[bool] = Field(None)

    address: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=30)
    email: Optional[str] = Field(None)

    timezone: Optional[str] = Field(None, max_length=50)
    opening_time: Optional[time] = Field(None)
    closing_time: Optional[time] = Field(None)

    class Config:
        from_attributes = True


class ClinicAICreditsUpdateSchema(BaseModel):
    """Separate from ClinicUpdateSchema on purpose — ai_credits/api_token are
    system-managed (deducted by app/modules/ai services on each call), not
    something a clinic admin should set through the general update endpoint.
    Wire this to its own admin-only route, e.g. POST /clinics/<id>/ai-credits."""
    ai_credits: int = Field(..., ge=0, description="New total AI credit balance for this clinic")
    api_token: Optional[str] = Field(None, max_length=255, description="Optional external API token for this clinic's AI usage")