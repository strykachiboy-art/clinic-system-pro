from __future__ import annotations

from datetime import datetime

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


DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 500


class MessageCreateSchema(BaseModel):
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

    parent_message_id: int | None = Field(
        default=None,
        gt=0,
        description="Parent message ID when replying",
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class MessageUpdateSchema(BaseModel):
    subject: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Updated message subject",
    )

    body: str | None = Field(
        default=None,
        min_length=1,
        description="Updated message body",
    )

    priority: MessagePriority | None = Field(
        default=None,
        description="Updated message priority",
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class MessageStatusUpdateSchema(BaseModel):
    status: MessageStatus = Field(
        ...,
        description="New message status",
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class MessageReadSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )


class MessageListQuerySchema(BaseModel):
    page: int = Field(
        default=DEFAULT_PAGE,
        ge=1,
        description="Page number",
    )

    per_page: int = Field(
        default=DEFAULT_PER_PAGE,
        ge=1,
        le=MAX_PER_PAGE,
        description="Items per page",
    )

    unread_only: bool = Field(
        default=False,
        description="Return unread messages only",
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class MessageSentListQuerySchema(BaseModel):
    page: int = Field(
        default=DEFAULT_PAGE,
        ge=1,
        description="Page number",
    )

    per_page: int = Field(
        default=DEFAULT_PER_PAGE,
        ge=1,
        le=MAX_PER_PAGE,
        description="Items per page",
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class MessageThreadQuerySchema(BaseModel):
    page: int = Field(
        default=DEFAULT_PAGE,
        ge=1,
        description="Page number",
    )

    per_page: int = Field(
        default=DEFAULT_PER_PAGE,
        ge=1,
        le=MAX_PER_PAGE,
        description="Items per page",
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class MessageResponseSchema(BaseModel):
    id: int = Field(
        ...,
        gt=0,
    )

    clinic_id: int = Field(
        ...,
        gt=0,
    )

    sender_id: int = Field(
        ...,
        gt=0,
    )

    recipient_id: int = Field(
        ...,
        gt=0,
    )

    subject: str
    body: str

    message_type: MessageType
    status: MessageStatus
    priority: MessagePriority

    parent_message_id: int | None = Field(
        default=None,
        gt=0,
    )

    sent_at: datetime | None = None
    read_at: datetime | None = None
    deleted_at: datetime | None = None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class MessageListResponseSchema(BaseModel):
    items: list[MessageResponseSchema]
    total: int = Field(
        ...,
        ge=0,
    )
    page: int = Field(
        ...,
        ge=1,
    )
    per_page: int = Field(
        ...,
        ge=1,
        le=MAX_PER_PAGE,
    )

    model_config = ConfigDict(
        extra="forbid",
    )