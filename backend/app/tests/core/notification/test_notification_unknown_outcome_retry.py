from __future__ import annotations

import pytest

from app.core.enums.notification_enums import (
    NotificationChannel,
    NotificationStatus,
)
from app.core.notifications.services import notification_service
from app.extensions import db


class UnknownOutcomeProvider:
    def __init__(self):
        self.calls = []
        self.accepted_keys = set()
        self.logical_deliveries = []

    def send(self, **kwargs):
        key = kwargs["idempotency_key"]

        self.calls.append(
            {
                "idempotency_key": key,
                "notification_id": (
                    kwargs["notification"].id
                ),
            }
        )

        if key in self.accepted_keys:
            return True

        self.accepted_keys.add(key)
        self.logical_deliveries.append(
            kwargs["notification"].id
        )

        raise TimeoutError(
            "provider outcome unknown after acceptance"
        )


def test_unknown_provider_outcome_retries_with_same_key_without_duplicate_delivery(
    app,
    clinic,
    user,
    make_notification,
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

        db.session.commit()

        provider = UnknownOutcomeProvider()

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            lambda channel, *, clinic_id: provider,
        )

        with pytest.raises(
            TimeoutError,
            match="provider outcome unknown after acceptance",
        ):
            notification_service.deliver_notification(
                clinic.id,
                notification.id,
            )

        failed_notification = db.session.get(
            type(notification),
            notification.id,
        )

        assert failed_notification is not None
        assert failed_notification.status is (
            NotificationStatus.FAILED
        )
        assert failed_notification.failed_at is not None
        assert failed_notification.retry_count == 1
        assert failed_notification.delivered_at is None
        assert failed_notification.error_message == (
            "provider outcome unknown after acceptance"
        )

        assert len(provider.calls) == 1
        assert len(provider.logical_deliveries) == 1

        first_key = provider.calls[0]["idempotency_key"]

        assert first_key == (
            f"clinic-notification-"
            f"{clinic.id}-{notification.id}"
        )

        retry_result = notification_service.deliver_notification(
            clinic.id,
            notification.id,
        )

        assert retry_result is True

        delivered_notification = db.session.get(
            type(notification),
            notification.id,
        )

        assert delivered_notification is not None
        assert delivered_notification.status is (
            NotificationStatus.DELIVERED
        )
        assert delivered_notification.failed_at is not None
        assert delivered_notification.retry_count == 1
        assert delivered_notification.delivered_at is not None
        assert delivered_notification.error_message is None

        assert len(provider.calls) == 2
        assert len(provider.logical_deliveries) == 1

        second_key = provider.calls[1]["idempotency_key"]

        assert second_key == first_key
        assert second_key == (
            f"clinic-notification-"
            f"{clinic.id}-{notification.id}"
        )


def test_repeated_unknown_provider_outcome_remains_retryable(
    app,
    clinic,
    user,
    make_notification,
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

        db.session.commit()

        calls = []

        class PersistentUnknownOutcomeProvider:
            def send(self, **kwargs):
                calls.append(
                    kwargs["idempotency_key"]
                )
                raise TimeoutError(
                    "provider outcome remains unknown"
                )

        provider = PersistentUnknownOutcomeProvider()

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            lambda channel, *, clinic_id: provider,
        )

        with pytest.raises(
            TimeoutError,
            match="provider outcome remains unknown",
        ):
            notification_service.deliver_notification(
                clinic.id,
                notification.id,
            )

        first_failure = db.session.get(
            type(notification),
            notification.id,
        )

        assert first_failure is not None
        assert first_failure.status is (
            NotificationStatus.FAILED
        )
        assert first_failure.retry_count == 1

        with pytest.raises(
            TimeoutError,
            match="provider outcome remains unknown",
        ):
            notification_service.deliver_notification(
                clinic.id,
                notification.id,
            )

        second_failure = db.session.get(
            type(notification),
            notification.id,
        )

        assert second_failure is not None
        assert second_failure.status is (
            NotificationStatus.FAILED
        )
        assert second_failure.retry_count == 2
        assert second_failure.delivered_at is None
        assert second_failure.error_message == (
            "provider outcome remains unknown"
        )

        assert len(calls) == 2
        assert calls[0] == calls[1]
        assert calls[0] == (
            f"clinic-notification-"
            f"{clinic.id}-{notification.id}"
        )
