from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.extensions import db

from app.core.auth.user.models.user_device_model import (
    UserDevice,
)
from app.core.exceptions import ValidationError
from app.core.notifications.providers.base_provider import (
    NotificationProviderBase,
)


class PushNotificationProvider(
    NotificationProviderBase
):
    def __init__(
        self,
        *,
        credentials: dict[str, Any] | None = None,
    ):
        self.credentials = credentials or {}

    def send(
        self,
        *,
        notification,
    ) -> bool:
        if notification is None:
            raise ValidationError(
                "Notification is required"
            )

        user_id = getattr(
            notification,
            "user_id",
            None,
        )

        if (
            isinstance(user_id, bool)
            or not isinstance(user_id, int)
            or user_id <= 0
        ):
            raise ValidationError(
                "Invalid notification user ID"
            )

        devices = self._get_active_devices(
            user_id=user_id,
        )

        if not devices:
            return False

        payload = self._build_payload(
            notification=notification,
        )

        delivered = False

        for device in devices:
            try:
                if self._send_to_device(
                    device=device,
                    payload=payload,
                ):
                    delivered = True
            except Exception:
                continue

        return delivered

    def _get_active_devices(
        self,
        *,
        user_id: int,
    ) -> list[UserDevice]:
        statement = (
            select(UserDevice)
            .where(
                UserDevice.user_id == user_id,
                UserDevice.is_active.is_(True),
            )
            .order_by(
                UserDevice.id.asc(),
            )
        )

        return list(
            db.session.scalars(statement).all()
        )

    def _build_payload(
        self,
        *,
        notification,
    ) -> dict[str, Any]:
        return {
            "title": notification.title,
            "message": notification.message,
            "notification_type": (
                notification.notification_type.value
                if hasattr(
                    notification.notification_type,
                    "value",
                )
                else notification.notification_type
            ),
            "priority": (
                notification.priority.value
                if hasattr(
                    notification.priority,
                    "value",
                )
                else notification.priority
            ),
            "reference_type": (
                notification.reference_type
            ),
            "reference_id": (
                notification.reference_id
            ),
        }

    def _send_to_device(
        self,
        *,
        device: UserDevice,
        payload: dict[str, Any],
    ) -> bool:
        device_token = getattr(
            device,
            "device_token",
            None,
        )

        if (
            not isinstance(device_token, str)
            or not device_token.strip()
        ):
            return False

        platform = getattr(
            device,
            "platform",
            None,
        )

        if (
            not isinstance(platform, str)
            or not platform.strip()
        ):
            return False

        return self._deliver_to_device(
            device_token=device_token.strip(),
            platform=platform.strip().lower(),
            payload=payload,
        )

    def _deliver_to_device(
        self,
        *,
        device_token: str,
        platform: str,
        payload: dict[str, Any],
    ) -> bool:
        raise NotImplementedError(
            "Push notification transport is not configured"
        )