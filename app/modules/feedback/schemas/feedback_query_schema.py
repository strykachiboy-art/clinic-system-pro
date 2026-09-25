from __future__ import annotations

from datetime import datetime, timezone

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)

from app.core.enums.feedback_enums import (
    FeedbackCategory,
    FeedbackPriority,
    FeedbackSource,
    FeedbackStatus,
    FeedbackType,
)


class FeedbackListQuerySchema(BaseModel):
    page: StrictInt = Field(
        default=1,
        ge=1,
    )

    per_page: StrictInt = Field(
        default=50,
        ge=1,
        le=500,
    )

    feedback_type: FeedbackType | None = None

    category: FeedbackCategory | None = None

    status: FeedbackStatus | None = None

    priority: FeedbackPriority | None = None

    source: FeedbackSource | None = None

    assigned_to_user_id: StrictInt | None = Field(
        default=None,
        gt=0,
    )

    submitted_by_user_id: StrictInt | None = Field(
        default=None,
        gt=0,
    )

    target_module: str | None = Field(
        default=None,
        max_length=100,
    )

    created_from: datetime | None = None

    created_to: datetime | None = None

    model_config = ConfigDict(
        extra="forbid",
    )

    @field_validator("target_module", mode="before")
    @classmethod
    def normalize_target_module(cls, value):
        if value is None:
            return None

        value = value.strip()

        return value or None

    @field_validator(
        "created_from",
        "created_to",
    )
    @classmethod
    def validate_timezone_aware(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None

        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                "Datetime must include timezone information"
            )

        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_created_range(self):
        if (
            self.created_from is not None
            and self.created_to is not None
            and self.created_to < self.created_from
        ):
            raise ValueError(
                "created_to must be later than or equal to created_from"
            )

        return self