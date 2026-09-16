from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MessageReactionPaginationQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=50, ge=1, le=500)
    user_id: int | None = Field(default=None, ge=1)
    reaction: str | None = Field(default=None, min_length=1, max_length=32)

    model_config = ConfigDict(extra="forbid")

    @field_validator("reaction")
    @classmethod
    def normalize_reaction(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()
        return value or None


class MessageReactionCreate(BaseModel):
    reaction: str = Field(min_length=1, max_length=32)

    model_config = ConfigDict(extra="forbid")

    @field_validator("reaction")
    @classmethod
    def normalize_reaction(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Reaction cannot be empty")

        return value


class MessageReactionUpdate(BaseModel):
    reaction: str = Field(min_length=1, max_length=32)

    model_config = ConfigDict(extra="forbid")

    @field_validator("reaction")
    @classmethod
    def normalize_reaction(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Reaction cannot be empty")

        return value


class MessageReactionResponse(BaseModel):
    id: int
    clinic_id: int
    message_id: int
    user_id: int
    reaction: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageReactionListResponse(BaseModel):
    data: list[MessageReactionResponse]
    page: int
    per_page: int
    total: int
    pages: int
    has_next: bool
    has_previous: bool