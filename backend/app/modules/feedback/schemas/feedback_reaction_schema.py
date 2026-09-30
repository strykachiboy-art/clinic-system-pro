from __future__ import annotations

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
)

from app.core.enums.feedback_reaction_enums import (
    FeedbackReactionType,
)


class FeedbackReactionCreateSchema(BaseModel):
    reaction_type: FeedbackReactionType

    model_config = ConfigDict(
        extra="forbid",
    )


class FeedbackReactionResponseSchema(BaseModel):
    id: StrictInt = Field(
        ...,
        gt=0,
    )

    feedback_id: StrictInt = Field(
        ...,
        gt=0,
    )

    user_id: StrictInt = Field(
        ...,
        gt=0,
    )

    reaction_type: FeedbackReactionType

    created_at: datetime

    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class FeedbackReactionSummarySchema(BaseModel):
    helpful: StrictInt = Field(
        ...,
        ge=0,
    )

    appreciated: StrictInt = Field(
        ...,
        ge=0,
    )

    not_helpful: StrictInt = Field(
        ...,
        ge=0,
    )

    my_reaction: FeedbackReactionType | None = None

    model_config = ConfigDict(
        extra="forbid",
    )