from __future__ import annotations

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.core.enums.chat_enums import (
    ConversationStatus,
    ConversationType,
    ParticipantRole,
    ParticipantStatus,
)


# ---------------------------------------------------------------------------
# Shared / Pagination
# ---------------------------------------------------------------------------


class ConversationPaginationQuery(BaseModel):
    page: int = Field(
        default=1,
        ge=1,
    )

    per_page: int = Field(
        default=50,
        ge=1,
        le=500,
    )

    status: ConversationStatus | None = None

    conversation_type: ConversationType | None = None

    patient_id: int | None = Field(
        default=None,
        ge=1,
    )

    search: str | None = Field(
        default=None,
        max_length=200,
    )

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


class ConversationParticipantPaginationQuery(BaseModel):
    page: int = Field(
        default=1,
        ge=1,
    )

    per_page: int = Field(
        default=50,
        ge=1,
        le=500,
    )

    status: ParticipantStatus | None = None

    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=True,
    )


# ---------------------------------------------------------------------------
# Conversation Schemas
# ---------------------------------------------------------------------------


class ConversationCreate(BaseModel):
    conversation_type: ConversationType = ConversationType.DIRECT

    title: str | None = Field(
        default=None,
        max_length=200,
    )

    description: str | None = Field(
        default=None,
        max_length=1000,
    )

    # Storage-system key/reference for a conversation avatar.
    # The actual image file is not stored in the database.
    avatar_storage_key: str | None = Field(
        default=None,
        max_length=500,
    )

    patient_id: int | None = Field(
        default=None,
        ge=1,
    )

    appointment_id: int | None = Field(
        default=None,
        ge=1,
    )

    consultation_id: int | None = Field(
        default=None,
        ge=1,
    )

    participant_user_ids: list[int] = Field(
        default_factory=list,
    )

    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=True,
    )

    @field_validator(
        "title",
        "description",
        "avatar_storage_key",
    )
    @classmethod
    def normalize_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None

    @field_validator("participant_user_ids")
    @classmethod
    def validate_participant_user_ids(
        cls,
        value: list[int],
    ) -> list[int]:
        if len(value) > 500:
            raise ValueError(
                "A conversation cannot contain more than 500 initial "
                "participants"
            )

        if any(user_id < 1 for user_id in value):
            raise ValueError(
                "Participant user IDs must be greater than or equal to 1"
            )

        if len(value) != len(set(value)):
            raise ValueError(
                "Duplicate participant user IDs are not allowed"
            )

        return value


class ConversationUpdate(BaseModel):
    conversation_type: ConversationType | None = None

    title: str | None = Field(
        default=None,
        max_length=200,
    )

    description: str | None = Field(
        default=None,
        max_length=1000,
    )

    # Storage-system key/reference for a conversation avatar.
    avatar_storage_key: str | None = Field(
        default=None,
        max_length=500,
    )

    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=True,
    )

    @field_validator(
        "title",
        "description",
        "avatar_storage_key",
    )
    @classmethod
    def normalize_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None


class ConversationStatusUpdate(BaseModel):
    status: ConversationStatus

    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=True,
    )


class ConversationResponse(BaseModel):
    id: int
    clinic_id: int

    conversation_type: ConversationType
    status: ConversationStatus

    title: str | None
    description: str | None
    avatar_storage_key: str | None

    created_by_id: int

    patient_id: int | None
    appointment_id: int | None
    consultation_id: int | None

    last_message_at: datetime | None
    archived_at: datetime | None
    closed_at: datetime | None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
    )


class ConversationListResponse(BaseModel):
    data: list[ConversationResponse]

    page: int
    per_page: int
    total: int
    pages: int

    has_next: bool
    has_previous: bool


# ---------------------------------------------------------------------------
# Conversation Participant Schemas
# ---------------------------------------------------------------------------


class ConversationParticipantCreate(BaseModel):
    user_id: int = Field(
        ge=1,
    )

    role: ParticipantRole = ParticipantRole.MEMBER

    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=True,
    )


class ConversationParticipantUpdate(BaseModel):
    role: ParticipantRole | None = None

    status: ParticipantStatus | None = None

    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=True,
    )


class ConversationParticipantReadStateUpdate(BaseModel):
    last_read_message_id: int = Field(
        ge=1,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class ConversationParticipantResponse(BaseModel):
    id: int

    clinic_id: int
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

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
    )


class ConversationParticipantListResponse(BaseModel):
    data: list[ConversationParticipantResponse]

    page: int
    per_page: int
    total: int
    pages: int

    has_next: bool
    has_previous: bool