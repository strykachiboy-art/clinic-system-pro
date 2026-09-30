from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.core.enums.notification_enums import (
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)


class NotificationCreateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    user_id: int = Field(
        ...,
        gt=0,
    )

    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
    )

    message: str = Field(
        ...,
        min_length=1,
        max_length=10000,
    )

    notification_type: NotificationType

    priority: NotificationPriority = (
        NotificationPriority.NORMAL
    )

    channel: NotificationChannel = (
        NotificationChannel.IN_APP
    )

    reference_type: Optional[str] = Field(
        default=None,
        max_length=50,
    )

    reference_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    @field_validator(
        "title",
        "message",
    )
    @classmethod
    def validate_required_strings(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "must not be blank"
            )

        return value

    @field_validator("reference_type")
    @classmethod
    def normalize_reference_type(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None

        value = value.strip()

        return value or None


class NotificationReadSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )


class NotificationStatusUpdateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    status: NotificationStatus

    error_message: Optional[str] = Field(
        default=None,
        max_length=2000,
    )

    @field_validator("error_message")
    @classmethod
    def normalize_error_message(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None

        value = value.strip()

        return value or None


class NotificationResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int = Field(
        gt=0,
    )

    clinic_id: int = Field(
        gt=0,
    )

    user_id: int = Field(
        gt=0,
    )

    title: str = Field(
        min_length=1,
        max_length=255,
    )

    message: str = Field(
        min_length=1,
        max_length=10000,
    )

    notification_type: NotificationType

    priority: NotificationPriority

    channel: NotificationChannel

    status: NotificationStatus

    reference_type: Optional[str] = Field(
        default=None,
        max_length=50,
    )

    reference_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    is_read: bool

    read_at: Optional[datetime] = None

    sent_at: Optional[datetime] = None

    delivered_at: Optional[datetime] = None

    failed_at: Optional[datetime] = None

    error_message: Optional[str] = Field(
        default=None,
        max_length=2000,
    )

    retry_count: int = Field(
        ge=0,
    )

    created_at: datetime

    updated_at: datetime


class NotificationListQuerySchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    page: int = Field(
        default=1,
        ge=1,
    )

    per_page: int = Field(
        default=50,
        ge=1,
        le=500,
    )

    unread_only: bool = False