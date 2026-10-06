from __future__ import annotations

import pytest
from app.core.enums.notification_enums import (
    NotificationChannel,
    NotificationStatus,
)
from app.core.notifications.services import notification_service
from app.extensions import db


class DeduplicatingProvider:
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

        if key not in self.accepted_keys:
            self.accepted_keys.add(key)
            self.logical_deliveries.append(
                kwargs["notification"].id
            )

        return True


def test_provider_success_with_local_ack_failure_retries_without_duplicate_delivery(
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

        provider = DeduplicatingProvider()

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            lambda channel, *, clinic_id: provider,
        )

        real_commit = db.session.commit
        commit_calls = {
            "count": 0,
        }

        def flaky_commit():
            commit_calls["count"] += 1

            if commit_calls["count"] == 1:
                raise RuntimeError(
                    "local acknowledgement failure"
                )

            real_commit()

        monkeypatch.setattr(
            db.session,
            "commit",
            flaky_commit,
        )

        try:
            with pytest.raises(
                RuntimeError,
                match="local acknowledgement failure",
            ):
                notification_service.deliver_notification(
                    clinic.id,
                    notification.id,
                )
        finally:
            monkeypatch.setattr(
                db.session,
                "commit",
                real_commit,
            )

        failed_notification = db.session.get(
            type(notification),
            notification.id,
        )

        assert failed_notification is not None
        assert failed_notification.status is (
            NotificationStatus.FAILED
        )
        assert failed_notification.retry_count == 1
        assert failed_notification.error_message == (
            "local acknowledgement failure"
        )

        assert len(provider.calls) == 1
        assert len(provider.logical_deliveries) == 1

        first_key = provider.calls[0]["idempotency_key"]

        assert first_key == (
            f"clinic-notification-"
            f"{clinic.id}-{notification.id}"
        )

        result = notification_service.deliver_notification(
            clinic.id,
            notification.id,
        )

        assert result is True

        delivered_notification = db.session.get(
            type(notification),
            notification.id,
        )

        assert delivered_notification is not None
        assert delivered_notification.status is (
            NotificationStatus.DELIVERED
        )
        assert delivered_notification.retry_count == 1
        assert delivered_notification.failed_at is not None
        assert delivered_notification.error_message is None
        assert delivered_notification.delivered_at is not None

        assert len(provider.calls) == 2
        assert len(provider.logical_deliveries) == 1

        second_key = provider.calls[1]["idempotency_key"]

        assert second_key == first_key
        assert second_key == (
            f"clinic-notification-"
            f"{clinic.id}-{notification.id}"
        )


def test_provider_idempotency_key_is_stable_across_direct_delivery_attempts(
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
        )

        db.session.commit()

        provider = DeduplicatingProvider()

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            lambda channel, *, clinic_id: provider,
        )

        first_result = notification_service.deliver_notification(
            clinic.id,
            notification.id,
        )

        assert first_result is True

        delivered_notification = db.session.get(
            type(notification),
            notification.id,
        )

        assert delivered_notification.status is (
            NotificationStatus.DELIVERED
        )

        # Terminal-state delivery must not invoke the provider again.
        second_result = notification_service.deliver_notification(
            clinic.id,
            notification.id,
        )

        assert second_result is True

        assert len(provider.calls) == 1
        assert len(provider.logical_deliveries) == 1

        assert provider.calls[0]["idempotency_key"] == (
            f"clinic-notification-"
            f"{clinic.id}-{notification.id}"
        )