from __future__ import annotations

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
)


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip()

    return value or None


class FeedbackCommentCreateSchema(BaseModel):
    body: str = Field(
        ...,
        min_length=1,
        max_length=10000,
    )

    model_config = ConfigDict(
        extra="forbid",
    )

    @field_validator("body", mode="before")
    @classmethod
    def normalize_body(cls, value):
        return _normalize_text(value)


class FeedbackCommentResponseSchema(BaseModel):
    id: StrictInt = Field(
        ...,
        gt=0,
    )

    feedback_id: StrictInt = Field(
        ...,
        gt=0,
    )

    author_user_id: StrictInt = Field(
        ...,
        gt=0,
    )

    body: str

    created_at: datetime

    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class FeedbackCommentListResponseSchema(BaseModel):
    items: list[FeedbackCommentResponseSchema]

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