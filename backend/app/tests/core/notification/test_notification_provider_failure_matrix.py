from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.core.enums.notification_enums import (
    NotificationChannel,
    NotificationStatus,
)
from app.core.notifications.models.notification_models import Notification
from app.core.notifications.services import notification_service


@pytest.mark.parametrize(
    ("failure", "expected_message"),
    [
        (
            TimeoutError("provider timeout"),
            "provider timeout",
        ),
        (
            ConnectionError("provider connection failed"),
            "provider connection failed",
        ),
        (
            RuntimeError("HTTP 503 Service Unavailable"),
            "HTTP 503 Service Unavailable",
        ),
        (
            RuntimeError("provider internal failure"),
            "provider internal failure",
        ),
    ],
)
def test_notification_provider_failure_matrix_is_retryable(
    app,
    make_notification,
    clinic,
    user,
    db_session,
    monkeypatch,
    failure,
    expected_message,
):
    with app.app_context():
        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            channel=NotificationChannel.PUSH,
            status=NotificationStatus.PENDING,
            retry_count=0,
        )
        notification_id = notification.id

        db_session.commit()

        provider = Mock()
        provider.send.side_effect = failure

        factory = Mock(return_value=provider)

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            factory,
        )

        with pytest.raises(type(failure), match=expected_message):
            notification_service.deliver_notification(
                clinic.id,
                notification_id,
            )

        failed_notification = db_session.get(
            Notification,
            notification_id,
        )

        assert failed_notification is not None
        assert failed_notification.status is NotificationStatus.FAILED
        assert failed_notification.failed_at is not None
        assert failed_notification.retry_count == 1
        assert failed_notification.delivered_at is None
        assert failed_notification.error_message == expected_message

        assert provider.send.call_count == 1

        first_call = provider.send.call_args
        first_key = first_call.kwargs["idempotency_key"]

        assert first_key == (
            f"clinic-notification-{clinic.id}-{notification.id}"
        )

        provider.send.side_effect = None
        provider.send.return_value = True

        retry_result = notification_service.deliver_notification(
            clinic.id,
            notification_id,
        )

        assert retry_result is True

        delivered_notification = db_session.get(
            Notification,
            notification_id,
        )

        assert delivered_notification is not None
        assert delivered_notification.status is NotificationStatus.DELIVERED
        assert delivered_notification.retry_count == 1
        assert delivered_notification.failed_at is not None
        assert delivered_notification.delivered_at is not None
        assert delivered_notification.error_message is None

        assert provider.send.call_count == 2

        second_call = provider.send.call_args
        second_key = second_call.kwargs["idempotency_key"]

        assert second_key == first_key
        assert second_key == (
            f"clinic-notification-{clinic.id}-{notification.id}"
        )


def test_notification_provider_false_result_is_retryable(
    app,
    make_notification,
    clinic,
    user,
    db_session,
    monkeypatch,
):
    with app.app_context():
        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            channel=NotificationChannel.PUSH,
            status=NotificationStatus.PENDING,
            retry_count=0,
        )
        notification_id = notification.id

        db_session.commit()

        provider = Mock()
        provider.send.return_value = False

        factory = Mock(return_value=provider)

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            factory,
        )

        with pytest.raises(
            RuntimeError,
            match="Notification provider rejected delivery",
        ):
            notification_service.deliver_notification(
                clinic.id,
                notification_id,
            )

        failed_notification = db_session.get(
            Notification,
            notification_id,
        )

        assert failed_notification is not None
        assert failed_notification.status is NotificationStatus.FAILED
        assert failed_notification.failed_at is not None
        assert failed_notification.retry_count == 1
        assert failed_notification.delivered_at is None
        assert failed_notification.error_message == (
            "Notification provider rejected delivery"
        )

        assert provider.send.call_count == 1

        first_key = provider.send.call_args.kwargs["idempotency_key"]

        assert first_key == (
            f"clinic-notification-{clinic.id}-{notification.id}"
        )

        provider.send.return_value = True

        retry_result = notification_service.deliver_notification(
            clinic.id,
            notification_id,
        )

        assert retry_result is True

        delivered_notification = db_session.get(
            Notification,
            notification_id,
        )

        assert delivered_notification is not None
        assert delivered_notification.status is NotificationStatus.DELIVERED
        assert delivered_notification.retry_count == 1
        assert delivered_notification.failed_at is not None
        assert delivered_notification.delivered_at is not None
        assert delivered_notification.error_message is None

        assert provider.send.call_count == 2

        second_key = provider.send.call_args.kwargs["idempotency_key"]

        assert second_key == first_key
        assert second_key == (
            f"clinic-notification-{clinic.id}-{notification.id}"
        )
