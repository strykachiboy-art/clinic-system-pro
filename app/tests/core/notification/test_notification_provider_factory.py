from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.core.enums.notification_enums import (
    NotificationChannel,
)
from app.core.notifications.providers.email_provider import (
    EmailNotificationProvider,
)
from app.core.notifications.providers.factory import (
    get_notification_provider,
)
from app.core.notifications.providers.push_provider import (
    PushNotificationProvider,
)
from app.core.notifications.providers.SMS_provider import (
    SMSNotificationProvider,
)


@pytest.mark.parametrize(
    (
        "channel",
        "provider_class",
        "credentials",
    ),
    [
        (
            NotificationChannel.EMAIL,
            EmailNotificationProvider,
            {
                "host": "smtp.example.com",
                "port": 587,
                "from_email": "noreply@example.com",
                "username": "smtp-user",
                "password": "smtp-password",
                "use_tls": True,
                "use_ssl": False,
            },
        ),
        (
            NotificationChannel.SMS,
            SMSNotificationProvider,
            {
                "provider": "test-gateway",
                "api_key": "test-api-key",
            },
        ),
        (
            NotificationChannel.PUSH,
            PushNotificationProvider,
            {
                "project_id": "test-project",
                "client_email": "test@example.com",
            },
        ),
    ],
)
def test_get_notification_provider(
    clinic,
    monkeypatch,
    channel,
    provider_class,
    credentials,
):
    get_credentials = Mock(
        return_value=credentials
    )

    monkeypatch.setattr(
        "app.core.notifications.providers.factory"
        ".get_integration_credentials",
        get_credentials,
    )

    provider = get_notification_provider(
        channel,
        clinic_id=clinic.id,
    )

    assert isinstance(
        provider,
        provider_class,
    )

    assert provider.credentials == credentials

    get_credentials.assert_called_once_with(
        clinic.id,
        channel.value,
    )


@pytest.mark.parametrize(
    (
        "channel",
        "provider_class",
    ),
    [
        (
            "email",
            EmailNotificationProvider,
        ),
        (
            "sms",
            SMSNotificationProvider,
        ),
        (
            "push",
            PushNotificationProvider,
        ),
    ],
)
def test_get_notification_provider_accepts_string(
    clinic,
    monkeypatch,
    channel,
    provider_class,
):
    credentials = {
        "test": "credentials",
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
        channel,
        clinic_id=clinic.id,
    )

    assert isinstance(
        provider,
        provider_class,
    )

    get_credentials.assert_called_once_with(
        clinic.id,
        channel,
    )


def test_factory_rejects_in_app_channel(
    clinic,
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
            NotificationChannel.IN_APP,
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


@pytest.mark.parametrize(
    "clinic_id",
    [
        0,
        -1,
        True,
        False,
    ],
)
def test_factory_rejects_invalid_clinic_id(
    clinic_id,
):
    with pytest.raises(
        ValueError,
        match="clinic_id must be a positive integer",
    ):
        get_notification_provider(
            NotificationChannel.EMAIL,
            clinic_id=clinic_id,
        )