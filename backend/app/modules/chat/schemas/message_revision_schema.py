from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums.chat_enums import MessageType


class MessageRevisionPaginationQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=50, ge=1, le=500)
    edited_by_id: int | None = Field(default=None, ge=1)

    model_config = ConfigDict(extra="forbid")


class MessageRevisionResponse(BaseModel):
    id: int
    clinic_id: int
    message_id: int
    edited_by_id: int
    revision_number: int
    previous_content: str | None
    previous_message_type: MessageType
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
    )


class MessageRevisionListResponse(BaseModel):
    data: list[MessageRevisionResponse]
    page: int
    per_page: int
    total: int
    pages: int
    has_next: bool
    has_previous: bool