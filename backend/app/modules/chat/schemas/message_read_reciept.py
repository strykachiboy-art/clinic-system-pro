from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums.chat_enums import ReadReceiptStatus


class MessageReadReceiptCreateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ReadReceiptStatus = ReadReceiptStatus.DELIVERED


class MessageReadReceiptStatusUpdateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ReadReceiptStatus


class MessageReadReceiptResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )

    id: int
    message_id: int
    user_id: int
    status: ReadReceiptStatus
    delivered_at: datetime | None
    read_at: datetime | None
    created_at: datetime
    updated_at: datetime