from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MessageReactionCreateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    reaction: str = Field(
        min_length=1,
        max_length=32,
    )


class MessageReactionUpdateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    reaction: str = Field(
        min_length=1,
        max_length=32,
    )


class MessageReactionResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )

    id: int
    message_id: int
    user_id: int
    reaction: str
    created_at: datetime
    updated_at: datetime