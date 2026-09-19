from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.core.enums.role_enums import Role


class DashboardContextSchema(BaseModel):
    role: Role

    scope: Literal[
        "system",
        "clinic",
        "personal",
    ]

    clinic_id: int | None = Field(
        default=None,
        gt=0,
    )

    generated_at: datetime

    model_config = ConfigDict(
        extra="forbid",
    )


class DashboardPeriodSchema(BaseModel):
    date_from: date

    date_to: date

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.date_to < self.date_from:
            raise ValueError(
                "date_to must be greater than or equal to date_from"
            )

        return self

    model_config = ConfigDict(
        extra="forbid",
    )


class DashboardQuerySchema(BaseModel):
    date_from: date | None = None

    date_to: date | None = None

    @model_validator(mode="after")
    def validate_date_range(self):
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_to < self.date_from
        ):
            raise ValueError(
                "date_to must be greater than or equal to date_from"
            )

        return self

    model_config = ConfigDict(
        extra="forbid",
    )


class DashboardTrendSchema(BaseModel):
    direction: Literal[
        "up",
        "down",
        "flat",
    ]

    percentage: Decimal | None = None

    model_config = ConfigDict(
        extra="forbid",
    )


class DashboardMetricSchema(BaseModel):
    key: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    label: str = Field(
        ...,
        min_length=1,
        max_length=150,
    )

    value: int | float | Decimal

    unit: str | None = Field(
        default=None,
        max_length=50,
    )

    trend: DashboardTrendSchema | None = None

    model_config = ConfigDict(
        extra="forbid",
    )


class DashboardAlertSchema(BaseModel):
    key: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    severity: Literal[
        "info",
        "warning",
        "critical",
    ]

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
    )

    count: int = Field(
        ...,
        ge=0,
    )

    description: str | None = Field(
        default=None,
        max_length=500,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class DashboardActivitySchema(BaseModel):
    entity_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    entity_id: int = Field(
        ...,
        gt=0,
    )

    action: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    occurred_at: datetime

    model_config = ConfigDict(
        extra="forbid",
    )


class DashboardChatSummarySchema(BaseModel):
    unread_messages: int = Field(
        ...,
        ge=0,
    )

    unread_conversations: int = Field(
        ...,
        ge=0,
    )

    mentions: int = Field(
        ...,
        ge=0,
    )

    priority_messages: int = Field(
        ...,
        ge=0,
    )

    recent_messages: int = Field(
        ...,
        ge=0,
    )

    model_config = ConfigDict(
        extra="forbid",
    )