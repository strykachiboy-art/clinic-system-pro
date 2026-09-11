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

    The provider receives an already-resolved phone number and
    is responsible only for validating the SMS payload and
    delegating delivery to the configured SMS transport.

    Recipient resolution and domain ownership remain outside
    the provider.
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
        """
        Validate and normalize the already-resolved
        recipient phone number.

        The provider does not resolve users, patients,
        staff, or devices.
        """

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

    def _deliver_sms(
        self,
        *,
        phone: str,
        message: str,
    ) -> bool:
        """
        SMS gateway transport boundary.

        Provider-specific implementations such as Twilio,
        Africa's Talking, Vonage, or another SMS gateway
        can implement the actual delivery here.
        """

        raise NotImplementedError(
            "SMS transport is not configured"
        )