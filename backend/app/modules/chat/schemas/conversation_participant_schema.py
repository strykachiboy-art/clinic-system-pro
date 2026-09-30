from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums.chat_enums import (
    ParticipantRole,
    ParticipantStatus,
)


class ConversationParticipantCreateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int = Field(gt=0)
    role: ParticipantRole = ParticipantRole.MEMBER


class ConversationParticipantStatusUpdateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ParticipantStatus


class ConversationParticipantRoleUpdateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: ParticipantRole


class ConversationParticipantResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )

    id: int
    conversation_id: int
    user_id: int
    role: ParticipantRole
    status: ParticipantStatus
    joined_at: datetime | None
    left_at: datetime | None
    removed_at: datetime | None
    last_read_message_id: int | None
    created_at: datetime
    updated_at: datetime