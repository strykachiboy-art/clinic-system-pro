from __future__ import annotations

from datetime import datetime

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


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip()

    return value or None


class FeedbackCreateSchema(BaseModel):
    feedback_type: FeedbackType

    category: FeedbackCategory

    subject: str = Field(
        ...,
        min_length=1,
        max_length=200,
    )

    message: str = Field(
        ...,
        min_length=1,
        max_length=10000,
    )

    target_module: str | None = Field(
        default=None,
        max_length=100,
    )

    target_resource_type: str | None = Field(
        default=None,
        max_length=100,
    )

    target_resource_id: StrictInt | None = Field(
        default=None,
        gt=0,
    )

    model_config = ConfigDict(
        extra="forbid",
    )

    @field_validator(
        "subject",
        "message",
        "target_module",
        "target_resource_type",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(cls, value):
        return _normalize_text(value)

    @model_validator(mode="after")
    def validate_target_fields(self):
        fields = (
            self.target_module,
            self.target_resource_type,
            self.target_resource_id,
        )

        supplied = sum(
            value is not None
            for value in fields
        )

        if supplied not in (0, 3):
            raise ValueError(
                "target_module, target_resource_type, and "
                "target_resource_id must either all be provided "
                "or all be omitted"
            )

        return self


class FeedbackManageSchema(BaseModel):
    status: FeedbackStatus | None = None

    priority: FeedbackPriority | None = None

    assigned_to_user_id: StrictInt | None = Field(
        default=None,
        gt=0,
    )

    resolution_note: str | None = Field(
        default=None,
        max_length=10000,
    )

    model_config = ConfigDict(
        extra="forbid",
    )

    @field_validator(
        "resolution_note",
        mode="before",
    )
    @classmethod
    def normalize_resolution_note(cls, value):
        return _normalize_text(value)


class FeedbackResponseSchema(BaseModel):
    id: StrictInt = Field(
        ...,
        gt=0,
    )

    clinic_id: StrictInt = Field(
        ...,
        gt=0,
    )

    submitted_by_user_id: StrictInt = Field(
        ...,
        gt=0,
    )

    feedback_type: FeedbackType

    category: FeedbackCategory

    subject: str

    message: str

    status: FeedbackStatus

    priority: FeedbackPriority

    source: FeedbackSource

    target_module: str | None

    target_resource_type: str | None

    target_resource_id: StrictInt | None = Field(
        default=None,
        gt=0,
    )

    assigned_to_user_id: StrictInt | None = Field(
        default=None,
        gt=0,
    )

    resolution_note: str | None

    created_at: datetime

    updated_at: datetime

    resolved_at: datetime | None

    closed_at: datetime | None

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class FeedbackListResponseSchema(BaseModel):
    items: list[FeedbackResponseSchema]

    total: StrictInt = Field(
        ...,
        ge=0,
    )

    page: StrictInt = Field(
        ...,
        ge=1,
    )

    per_page: StrictInt = Field(
        ...,
        ge=1,
        le=500,
    )

    pages: StrictInt = Field(
        ...,
        ge=0,
    )

    has_next: bool

    has_previous: bool

    model_config = ConfigDict(
        extra="forbid",
    )