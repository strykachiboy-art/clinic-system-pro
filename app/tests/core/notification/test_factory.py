from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.core.enums.notification_enums import (
    NotificationChannel,
)
from app.core.notifications.providers.factory import (
    get_notification_provider,
)
from app.core.notifications.providers.push_provider import (
    PushNotificationProvider,
)


def test_get_push_notification_provider(
    clinic,
    monkeypatch,
):
    credentials = {
        "project_id": "test-project",
        "client_email": "test@example.com",
    }

    monkeypatch.setattr(
        "app.core.notifications.providers.factory"
        ".get_integration_credentials",
        Mock(return_value=credentials),
    )

    provider = get_notification_provider(
        NotificationChannel.PUSH,
        clinic_id=clinic.id,
    )

    assert isinstance(
        provider,
        PushNotificationProvider,
    )

    assert provider.credentials == credentials


def test_get_push_notification_provider_accepts_string(
    clinic,
    monkeypatch,
):
    credentials = {
        "project_id": "test-project",
    }

    get_credentials = Mock(
        return_value=credentials
    )

    monkeypatch.setattr(
        "app.core.notifications.providers.factory"
        ".get_integration_credentials",
        get_credentials,
    )

    provider = get_notification_provider(
        "push",
        clinic_id=clinic.id,
    )

    assert isinstance(
        provider,
        PushNotificationProvider,
    )

    get_credentials.assert_called_once_with(
        clinic.id,
        "push",
    )


@pytest.mark.parametrize(
    "channel",
    [
        NotificationChannel.IN_APP,
        NotificationChannel.EMAIL,
        NotificationChannel.SMS,
    ],
)
def test_factory_rejects_channels_without_provider(
    clinic,
    channel,
    monkeypatch,
):
    get_credentials = Mock()

    monkeypatch.setattr(
        "app.core.notifications.providers.factory"
        ".get_integration_credentials",
        get_credentials,
    )

    with pytest.raises(
        ValueError,
        match="No provider configured",
    ):
        get_notification_provider(
            channel,
            clinic_id=clinic.id,
        )

    get_credentials.assert_not_called()


def test_factory_rejects_invalid_channel(
    clinic,
):
    with pytest.raises(
        ValueError,
        match="Unsupported notification channel",
    ):
        get_notification_provider(
            "invalid-channel",
            clinic_id=clinic.id,
        )