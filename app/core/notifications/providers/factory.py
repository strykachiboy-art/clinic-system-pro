from __future__ import annotations

from app.core.enums.notification_enums import (
    NotificationChannel,
)
from app.core.notifications.providers.base_provider import (
    NotificationProviderBase,
)
from app.core.notifications.providers.push_provider import (
    PushNotificationProvider,
)
from app.modules.settings.services.integration_config_service import (
    get_integration_credentials,
)


_NOTIFICATION_PROVIDER_IMPLEMENTATIONS: dict[
    NotificationChannel,
    type[NotificationProviderBase],
] = {
    NotificationChannel.PUSH: PushNotificationProvider,
}


def get_notification_provider(
    channel: NotificationChannel | str,
    *,
    clinic_id: int,
) -> NotificationProviderBase:
    if isinstance(channel, str):
        channel_value = channel.strip().lower()

        try:
            channel = NotificationChannel(
                channel_value
            )
        except ValueError as exc:
            raise ValueError(
                f"Unsupported notification channel: "
                f"{channel}"
            ) from exc

    provider_class = (
        _NOTIFICATION_PROVIDER_IMPLEMENTATIONS.get(
            channel
        )
    )

    if provider_class is None:
        raise ValueError(
            f"No provider configured for notification "
            f"channel: {channel}"
        )

    credentials = get_integration_credentials(
        clinic_id,
        channel.value,
    )

    return provider_class(
        credentials=credentials,
    )