from __future__ import annotations

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.core.enums.chat_enums import (
    AttachmentType,
    MentionType,
    MessagePriority,
    MessageStatus,
    PinStatus,
    ReadReceiptStatus,
)


# ---------------------------------------------------------------------------
# Message Query / Pagination
# ---------------------------------------------------------------------------


class MessagePaginationQuery(BaseModel):
    page: int = Field(
        default=1,
        ge=1,
    )

    per_page: int = Field(
        default=50,
        ge=1,
        le=500,
    )

    status: MessageStatus | None = None
    priority: MessagePriority | None = None

    search: str | None = Field(
        default=None,
        max_length=500,
    )

    patient_id: int | None = Field(
        default=None,
        ge=1,
    )

    created_from: datetime | None = None
    created_to: datetime | None = None

    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=True,
    )

    @field_validator("search")
    @classmethod
    def normalize_search(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None

    @model_validator(mode="after")
    def validate_date_range(self) -> "MessagePaginationQuery":
        if (
            self.created_from is not None
            and self.created_to is not None
            and self.created_to < self.created_from
        ):
            raise ValueError(
                "created_to must be greater than or equal to created_from"
            )

        return self


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------


class MessageCreate(BaseModel):
    content: str | None = None

    priority: MessagePriority = MessagePriority.NORMAL

    reply_to_message_id: int | None = Field(
        default=None,
        ge=1,
    )

    attachments: list["MessageAttachmentCreate"] = Field(
        default_factory=list,
    )

    mentions: list["MessageMentionCreate"] = Field(
        default_factory=list,
    )

    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=True,
    )

    @field_validator("content")
    @classmethod
    def normalize_content(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None

    @field_validator("attachments")
    @classmethod
    def validate_attachments(
        cls,
        value: list["MessageAttachmentCreate"],
    ) -> list["MessageAttachmentCreate"]:
        if len(value) > 20:
            raise ValueError(
                "A message cannot contain more than 20 attachments"
            )

        return value

    @field_validator("mentions")
    @classmethod
    def validate_mentions(
        cls,
        value: list["MessageMentionCreate"],
    ) -> list["MessageMentionCreate"]:
        if len(value) > 100:
            raise ValueError(
                "A message cannot contain more than 100 mentions"
            )

        return value


class MessageUpdate(BaseModel):
    content: str | None = None

    model_config = ConfigDict(
        extra="forbid",
    )

    @field_validator("content")
    @classmethod
    def normalize_content(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None


class MessagePriorityUpdate(BaseModel):
    """
    Client-facing priority change.

    Authorization and message lifecycle rules remain service-controlled.
    """

    priority: MessagePriority

    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=True,
    )


class MessageResponse(BaseModel):
    id: int
    clinic_id: int
    conversation_id: int
    sender_id: int

    reply_to_message_id: int | None

    content: str | None

    status: MessageStatus
    priority: MessagePriority

    created_at: datetime
    updated_at: datetime
    edited_at: datetime | None
    deleted_at: datetime | None

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
    )


class MessageListResponse(BaseModel):
    data: list[MessageResponse]

    page: int
    per_page: int
    total: int
    pages: int
    has_next: bool
    has_previous: bool


# ---------------------------------------------------------------------------
# Message Attachment
# ---------------------------------------------------------------------------


class MessageAttachmentCreate(BaseModel):
    attachment_type: AttachmentType

    file_name: str = Field(
        min_length=1,
        max_length=255,
    )

    mime_type: str = Field(
        min_length=1,
        max_length=255,
    )

    file_size_bytes: int = Field(
        ge=0,
    )

    storage_key: str = Field(
        min_length=1,
        max_length=500,
    )

    checksum: str | None = Field(
        default=None,
        max_length=255,
    )

    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=True,
    )

    @field_validator(
        "file_name",
        "mime_type",
        "storage_key",
        "checksum",
    )
    @classmethod
    def normalize_strings(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None


class MessageAttachmentResponse(BaseModel):
    id: int
    clinic_id: int
    message_id: int

    attachment_type: AttachmentType

    file_name: str
    mime_type: str
    file_size_bytes: int
    storage_key: str
    checksum: str | None

    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
    )


# ---------------------------------------------------------------------------
# Message Mention
# ---------------------------------------------------------------------------


class MessageMentionCreate(BaseModel):
    mention_type: MentionType

    mentioned_user_id: int | None = Field(
        default=None,
        ge=1,
    )

    mentioned_patient_id: int | None = Field(
        default=None,
        ge=1,
    )

    mentioned_conversation_id: int | None = Field(
        default=None,
        ge=1,
    )

    position_start: int | None = Field(
        default=None,
        ge=0,
    )

    position_end: int | None = Field(
        default=None,
        ge=0,
    )

    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=True,
    )

    @model_validator(mode="after")
    def validate_target(self) -> "MessageMentionCreate":
        targets = {
            MentionType.USER: self.mentioned_user_id,
            MentionType.STAFF: self.mentioned_user_id,
            MentionType.PATIENT: self.mentioned_patient_id,
            MentionType.GROUP: self.mentioned_conversation_id,
        }

        selected_targets = [
            self.mentioned_user_id,
            self.mentioned_patient_id,
            self.mentioned_conversation_id,
        ]

        if sum(target is not None for target in selected_targets) != 1:
            raise ValueError(
                "Exactly one mention target must be provided"
            )

        expected_target = targets.get(self.mention_type)

        if expected_target is None:
            raise ValueError(
                "Mention target does not match mention_type"
            )

        if (
            self.position_start is not None
            and self.position_end is not None
            and self.position_end < self.position_start
        ):
            raise ValueError(
                "position_end must be greater than or equal to "
                "position_start"
            )

        return self


class MessageMentionResponse(BaseModel):
    id: int
    clinic_id: int
    message_id: int

    mention_type: MentionType

    mentioned_user_id: int | None
    mentioned_patient_id: int | None
    mentioned_conversation_id: int | None

    position_start: int | None
    position_end: int | None

    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
    )


# ---------------------------------------------------------------------------
# Message Pin
# ---------------------------------------------------------------------------


class MessagePinCreate(BaseModel):
    expires_at: datetime | None = None

    model_config = ConfigDict(
        extra="forbid",
    )


class MessagePinResponse(BaseModel):
    id: int
    clinic_id: int
    message_id: int
    pinned_by_id: int

    status: PinStatus

    pinned_at: datetime
    expires_at: datetime | None
    unpinned_at: datetime | None

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
    )


# ---------------------------------------------------------------------------
# Message Read Receipt
# ---------------------------------------------------------------------------


class MessageReadReceiptCreate(BaseModel):
    status: ReadReceiptStatus = ReadReceiptStatus.DELIVERED

    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=True,
    )


class MessageReadReceiptUpdate(BaseModel):
    status: ReadReceiptStatus

    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=True,
    )


class MessageReadReceiptResponse(BaseModel):
    id: int
    clinic_id: int
    message_id: int
    user_id: int

    status: ReadReceiptStatus

    delivered_at: datetime | None
    read_at: datetime | None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
    )


# ---------------------------------------------------------------------------
# Forward References
# ---------------------------------------------------------------------------


MessageCreate.model_rebuild()