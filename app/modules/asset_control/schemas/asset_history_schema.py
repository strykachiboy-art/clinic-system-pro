from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums.asset_enums import (
    AssetCondition,
    AssetHistoryEventType,
    AssetStatus,
)


class AssetHistoryResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )

    id: int
    clinic_id: int
    asset_id: int
    event_type: AssetHistoryEventType

    previous_status: AssetStatus | None = None
    new_status: AssetStatus | None = None

    previous_condition: AssetCondition | None = None
    new_condition: AssetCondition | None = None

    previous_assigned_to_id: int | None = None
    new_assigned_to_id: int | None = None

    previous_location: str | None = None
    new_location: str | None = None

    actor_user_id: int | None = None

    event_at: datetime
    reason: str | None = None
    notes: str | None = None
    event_metadata: dict[str, Any] | None = None

    created_at: datetime


class AssetHistoryListQuerySchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    asset_id: int | None = Field(
        default=None,
        gt=0,
    )

    event_type: AssetHistoryEventType | None = None

    actor_user_id: int | None = Field(
        default=None,
        gt=0,
    )

    event_from: datetime | None = None
    event_to: datetime | None = None

    page: int = Field(
        default=1,
        ge=1,
    )

    per_page: int = Field(
        default=50,
        ge=1,
        le=500,
    )