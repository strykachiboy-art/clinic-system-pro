from datetime import datetime
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.core.enums.message_enums import (
    MessagePriority,
    MessageStatus,
    MessageType,
)


# ============================================================================
# Message Creation
# ============================================================================


class MessageCreateSchema(BaseModel):
    """
    Request schema for creating a message.

    clinic_id and sender_id are intentionally excluded.

    The clinic is derived from the authenticated user's
    clinic assignment by the route/service layer.

    The sender is the authenticated user.
    """

    recipient_id: int = Field(
        ...,
        gt=0,
        description="ID of the message recipient",
    )

    subject: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Message subject",
    )

    body: str = Field(
        ...,
        min_length=1,
        description="Message body",
    )

    message_type: MessageType = Field(
        default=MessageType.DIRECT,
        description="Type of the message",
    )

    priority: MessagePriority = Field(
        default=MessagePriority.NORMAL,
        description="Priority of the message",
    )

    parent_message_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="ID of the parent message when replying to a thread",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


# ============================================================================
# Message Update
# ============================================================================


class MessageUpdateSchema(BaseModel):
    """
    Request schema for updating a message.

    Only fields that are safe to modify after creation
    should be accepted here.
    """

    subject: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Updated message subject",
    )

    body: Optional[str] = Field(
        default=None,
        min_length=1,
        description="Updated message body",
    )

    priority: Optional[MessagePriority] = Field(
        default=None,
        description="Updated message priority",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


# ============================================================================
# Message Status Update
# ============================================================================


class MessageStatusUpdateSchema(BaseModel):
    """
    Request schema for updating message status.
    """

    status: MessageStatus = Field(
        ...,
        description="New message status",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


# ============================================================================
# Message Read State
# ============================================================================


class MessageReadSchema(BaseModel):
    """
    Request schema for marking a message as read.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )


# ============================================================================
# Message Response
# ============================================================================


class MessageResponseSchema(BaseModel):
    """
    Response schema for a message.
    """

    id: int
    clinic_id: int

    sender_id: int
    recipient_id: int

    subject: str
    body: str

    message_type: MessageType
    status: MessageStatus
    priority: MessagePriority

    parent_message_id: Optional[int]

    sent_at: Optional[datetime]
    read_at: Optional[datetime]
    deleted_at: Optional[datetime]

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )