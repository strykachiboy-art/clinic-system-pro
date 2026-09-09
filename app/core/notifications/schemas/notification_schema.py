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


# ============================================================================
# CREATE NOTIFICATION
# ============================================================================


class NotificationCreateSchema(BaseModel):
    """
    Schema for creating a notification.

    clinic_id is intentionally excluded.
    It must come from the authenticated user's clinic.

    status, is_read, retry_count and delivery timestamps
    are service-controlled and cannot be supplied by clients.
    """

    model_config = ConfigDict(
        extra="forbid",
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

    @field_validator("title", "message")
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("must not be blank")

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


# ============================================================================
# READ REQUEST
# ============================================================================


class NotificationReadSchema(BaseModel):
    """
    Empty request schema used by read/read-all endpoints.
    """
    model_config = ConfigDict(
        extra="forbid",
    )


# ============================================================================
# DELIVERY STATUS UPDATE
# ============================================================================


class NotificationStatusUpdateSchema(BaseModel):
    """
    Internal schema for delivery workers.

    it is not exposed through ordinary
    authenticated notification routes.
    """

    model_config = ConfigDict(
        extra="forbid",
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


# ============================================================================
# NOTIFICATION RESPONSE
# ============================================================================


class NotificationResponseSchema(BaseModel):
    """
    Serialized notification returned by the API.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    clinic_id: int
    user_id: int

    title: str
    message: str

    notification_type: NotificationType
    priority: NotificationPriority
    channel: NotificationChannel
    status: NotificationStatus

    reference_type: Optional[str] = None
    reference_id: Optional[int] = None

    is_read: bool
    read_at: Optional[datetime] = None

    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None

    error_message: Optional[str] = None
    retry_count: int

    created_at: datetime
    updated_at: datetime
    
# ============================================================================
# NOTIFICATION LIST QUERY
# ============================================================================


class NotificationListQuerySchema(BaseModel):
    """
    Query parameters for listing the authenticated user's notifications.

    Pagination is mandatory at the API boundary so notification collections
    cannot be returned unbounded.
    """

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