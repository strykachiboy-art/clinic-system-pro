from __future__ import annotations

from typing import Any

from app.core.exceptions import ValidationError
from app.core.notifications.models.notification_models import Notification
from app.core.notifications.providers.base_provider import (
    NotificationProviderBase,
)


class SMSNotificationProvider(NotificationProviderBase):
    """
    SMS notification provider.
    """

    def __init__(
        self,
        *,
        credentials: dict[str, Any] | None = None,
    ):
        self.credentials = credentials or {}

    def send(
        self,
        *,
        notification: Notification,
        phone: str,
    ) -> bool:
        if notification is None:
            raise ValidationError(
                "Notification is required"
            )

        phone = self._normalize_phone(
            phone
        )

        message = self._build_message(
            notification
        )

        return self._deliver_sms(
            phone=phone,
            message=message,
        )

    @staticmethod
    def _normalize_phone(
        phone: str,
    ) -> str:
        if not isinstance(phone, str):
            raise ValidationError(
                "Notification recipient phone number is invalid"
            )

        phone = phone.strip()

        if not phone:
            raise ValidationError(
                "Notification recipient phone number is invalid"
            )

        if len(phone) > 30:
            raise ValidationError(
                "Notification recipient phone number is invalid"
            )

        return phone

    @staticmethod
    def _build_message(
        notification: Notification,
    ) -> str:
        message = getattr(
            notification,
            "message",
            None,
        )

        if not isinstance(message, str):
            raise ValidationError(
                "Notification message is invalid"
            )

        message = message.strip()

        if not message:
            raise ValidationError(
                "Notification message is required"
            )

        return message

    def _get_required_credential(
        self,
        name: str,
    ) -> str:
        value = self.credentials.get(
            name
        )

        if (
            not isinstance(value, str)
            or not value.strip()
        ):
            raise ValidationError(
                f"SMS provider credential "
                f"'{name}' is required"
            )

        return value.strip()

    def _deliver_sms(
        self,
        *,
        phone: str,
        message: str,
    ) -> bool:
        """
        SMS transport boundary.

        A concrete gateway implementation should use the
        provider credentials supplied by the integration
        configuration service.

        This method deliberately does not report success
        until an actual transport implementation returns
        successfully.
        """

        raise NotImplementedError(
            "SMS transport is not configured"
        )