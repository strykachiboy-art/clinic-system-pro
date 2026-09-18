from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums.asset_enums import MaintenanceStatus


class AssetMaintenanceScheduleSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    scheduled_date: date | None = None

    description: str = Field(
        min_length=1,
        max_length=5000,
    )

    notes: str | None = Field(
        default=None,
        max_length=5000,
    )


class AssetMaintenanceStartSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    notes: str | None = Field(
        default=None,
        max_length=5000,
    )


class AssetMaintenanceCompleteSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    cost: Decimal | None = Field(
        default=None,
        ge=0,
    )

    notes: str | None = Field(
        default=None,
        max_length=5000,
    )


class AssetMaintenanceCancelSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    reason: str = Field(
        min_length=1,
        max_length=500,
    )


class AssetMaintenanceResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )

    id: int
    clinic_id: int
    asset_id: int

    status: MaintenanceStatus

    scheduled_date: date | None = None

    started_at: datetime | None = None
    completed_at: datetime | None = None

    performed_by_user_id: int | None = None

    cost: Decimal | None = None

    description: str
    notes: str | None = None

    created_at: datetime
    updated_at: datetime


class AssetMaintenanceListQuerySchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    asset_id: int | None = Field(
        default=None,
        gt=0,
    )

    status: MaintenanceStatus | None = None

    scheduled_from: date | None = None
    scheduled_to: date | None = None

    performed_by_user_id: int | None = Field(
        default=None,
        gt=0,
    )

    page: int = Field(
        default=1,
        ge=1,
    )

    per_page: int = Field(
        default=50,
        ge=1,
        le=500,
    )

    @model_validator(mode="after")
    def validate_date_range(self) -> "AssetMaintenanceListQuerySchema":
        if (
            self.scheduled_from is not None
            and self.scheduled_to is not None
            and self.scheduled_to < self.scheduled_from
        ):
            raise ValueError(
                "scheduled_to must be greater than or equal to scheduled_from"
            )

        return self