from pydantic import BaseModel, ConfigDict

from app.core.enums.feedback_reaction_enums import FeedbackReactionType


class FeedbackReactionCreateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reaction_type: FeedbackReactionType


class FeedbackReactionResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    feedback_id: int
    user_id: int
    reaction_type: FeedbackReactionType
    created_at: object
    updated_at: object


class FeedbackReactionSummarySchema(BaseModel):
    helpful: int
    appreciated: int
    not_helpful: int
    my_reaction: FeedbackReactionType | None = None