from __future__ import annotations

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
)

from app.core.enums.emergency_access_enums import (
    ConsentGuardDecision,
    EmergencyAccessStatus,
)


class EmergencyAccessRequestSchema(BaseModel):
    patient_id: StrictInt = Field(
        ...,
        gt=0,
    )

    reason: str = Field(
        ...,
        min_length=1,
        max_length=500,
    )

    purpose: str = Field(
        ...,
        min_length=1,
        max_length=255,
    )

    scope: list[str] = Field(
        ...,
        min_length=1,
        max_length=50,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class EmergencyAccessDecisionSchema(BaseModel):
    duration_minutes: StrictInt = Field(
        ...,
        gt=0,
        le=60,
    )

    review_notes: str | None = Field(
        default=None,
        max_length=1000,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class EmergencyAccessRevokeSchema(BaseModel):
    reason: str = Field(
        ...,
        min_length=1,
        max_length=500,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class ConsentGuardEvaluationSchema(BaseModel):
    decision: ConsentGuardDecision
    consent_reference: str | None = Field(
        default=None,
        max_length=255,
    )
    emergency_exception: StrictBool
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    policy_context: dict | None = None

    model_config = ConfigDict(
        extra="forbid",
    )


class EmergencyAccessResponseSchema(BaseModel):
    id: StrictInt = Field(
        ...,
        gt=0,
    )

    clinic_id: StrictInt = Field(
        ...,
        gt=0,
    )

    patient_id: StrictInt = Field(
        ...,
        gt=0,
    )

    requester_user_id: StrictInt = Field(
        ...,
        gt=0,
    )

    requester_role: str
    reason: str
    purpose: str
    scope: list[str]
    status: EmergencyAccessStatus

    requested_at: datetime
    granted_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None
    reviewed_at: datetime | None
    reviewed_by_user_id: StrictInt | None
    review_notes: str | None

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )