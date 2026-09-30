from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums.chat_enums import PinStatus


class MessagePinCreateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    expires_at: datetime | None = None


class MessagePinStatusUpdateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    status: PinStatus


class MessagePinResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )

    id: int
    message_id: int
    pinned_by_id: int
    status: PinStatus
    pinned_at: datetime
    expires_at: datetime | None
    unpinned_at: datetime | None