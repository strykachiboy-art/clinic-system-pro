from pydantic import BaseModel, ConfigDict, Field

from app.core.enums.chat_enums import AttachmentType


class MessageAttachmentCreateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    attachment_type: AttachmentType

    file_name: str | None = Field(
        default=None,
        max_length=255,
    )

    mime_type: str = Field(
        min_length=1,
        max_length=150,
    )

    file_size_bytes: int | None = Field(
        default=None,
        ge=0,
    )


class MessageAttachmentResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )

    id: int
    attachment_type: AttachmentType
    file_name: str | None
    mime_type: str
    file_size_bytes: int | None
    created_at: str
    updated_at: str