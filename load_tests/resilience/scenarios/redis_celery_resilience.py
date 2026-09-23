from __future__ import annotations

import pytest
from celery.exceptions import OperationalError
from redis.exceptions import ConnectionError

from app import extensions
from app.core.enums.notification_enums import (
    NotificationChannel,
    NotificationStatus,
)
from app.core.notifications.services import (
    notification_service,
)
from app.extensions import celery, db


PROFILE_ENDPOINT = "/api/v1/profile/me"


def test_redis_auth_fails_closed_during_outage(
    client,
    user,
    auth_headers_for,
    monkeypatch,
):
    redis_client = extensions.redis_client

    def fail_exists(_key):
        raise ConnectionError(
            "Synthetic Redis outage"
        )

    monkeypatch.setattr(
        redis_client,
        "exists",
        fail_exists,
    )

    response = client.get(
        PROFILE_ENDPOINT,
        headers=auth_headers_for(user),
    )

    assert response.status_code == 401


def test_redis_auth_recovers_after_outage(
    client,
    user,
    auth_headers_for,
    monkeypatch,
):
    redis_client = extensions.redis_client

    calls = {
        "count": 0,
    }

    def fail_once_then_recover(_key):
        calls["count"] += 1

        if calls["count"] == 1:
            raise ConnectionError(
                "Synthetic transient Redis outage"
            )

        return 0

    monkeypatch.setattr(
        redis_client,
        "exists",
        fail_once_then_recover,
    )

    first_response = client.get(
        PROFILE_ENDPOINT,
        headers=auth_headers_for(user),
    )

    assert first_response.status_code == 401

    second_response = client.get(
        PROFILE_ENDPOINT,
        headers=auth_headers_for(user),
    )

    assert second_response.status_code == 200
    assert calls["count"] == 2


def test_celery_broker_failure_leaves_notification_pending(
    clinic,
    user,
    make_notification,
    monkeypatch,
):
    notification = make_notification(
        clinic_id=clinic.id,
        user_id=user.id,
        channel=NotificationChannel.EMAIL,
        status=NotificationStatus.PENDING,
    )

    def fail_publish(notification_id):
        raise OperationalError(
            "Synthetic Redis broker outage"
        )

    monkeypatch.setattr(
        notification_service.deliver_notification,
        "delay",
        fail_publish,
    )

    with pytest.raises(
        OperationalError,
        match="Synthetic Redis broker outage",
    ):
        notification_service.queue_notification_delivery(
            notification.id,
            clinic_id=clinic.id,
            user_id=user.id,
        )

    db.session.refresh(notification)

    assert notification.status == (
        NotificationStatus.PENDING
    )
    assert notification.retry_count == 0
    assert notification.sent_at is None
    assert notification.delivered_at is None
    assert notification.failed_at is None


def test_celery_broker_recovers_without_duplicate_state_change(
    clinic,
    user,
    make_notification,
    monkeypatch,
):
    notification = make_notification(
        clinic_id=clinic.id,
        user_id=user.id,
        channel=NotificationChannel.EMAIL,
        status=NotificationStatus.PENDING,
    )

    attempts = {
        "count": 0,
    }

    def publish(notification_id):
        attempts["count"] += 1

        if attempts["count"] == 1:
            raise OperationalError(
                "Synthetic transient broker failure"
            )

        assert notification_id == notification.id

        return object()

    monkeypatch.setattr(
        notification_service.deliver_notification,
        "delay",
        publish,
    )

    with pytest.raises(
        OperationalError,
        match="Synthetic transient broker failure",
    ):
        notification_service.queue_notification_delivery(
            notification.id,
            clinic_id=clinic.id,
            user_id=user.id,
        )

    result = (
        notification_service.queue_notification_delivery(
            notification.id,
            clinic_id=clinic.id,
            user_id=user.id,
        )
    )

    assert result is notification
    assert attempts["count"] == 2

    db.session.refresh(notification)

    assert notification.status == (
        NotificationStatus.PENDING
    )
    assert notification.retry_count == 0
    assert notification.sent_at is None
    assert notification.delivered_at is None


def test_celery_beat_schedule_references_registered_tasks(
    app,
):
    expected_tasks = {
        "check_upcoming_appointments",
        "mark_overdue_invoices",
        "reset_monthly_ai_usage",
    }

    scheduled_tasks = {
        entry["task"]
        for entry in celery.conf.beat_schedule.values()
    }

    assert expected_tasks.issubset(
        scheduled_tasks
    )

    registered_tasks = set(
        celery.tasks.keys()
    )

    assert expected_tasks.issubset(
        registered_tasks
    )