from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.enums.notification_enums import (
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.notifications.models.notification_models import Notification
from app.core.notifications.services import notification_service


# ============================================================================
# CREATE NOTIFICATION
# ============================================================================


def test_create_notification_success(
    app,
    clinic,
    user,
):
    with app.app_context():
        notification = notification_service.create_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            title="Test notification",
            message="Hello user",
            notification_type=NotificationType.SYSTEM,
            priority=NotificationPriority.NORMAL,
            channel=NotificationChannel.IN_APP,
        )

        assert notification.id is not None
        assert notification.clinic_id == clinic.id
        assert notification.user_id == user.id
        assert notification.title == "Test notification"
        assert notification.message == "Hello user"
        assert notification.notification_type == NotificationType.SYSTEM
        assert notification.priority == NotificationPriority.NORMAL
        assert notification.channel == NotificationChannel.IN_APP
        assert notification.status == NotificationStatus.PENDING
        assert notification.is_read is False
        assert notification.retry_count == 0


def test_create_notification_normalizes_strings(
    app,
    clinic,
    user,
):
    with app.app_context():
        notification = notification_service.create_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            title="  Test title  ",
            message="  Test message  ",
            notification_type=NotificationType.SYSTEM,
            priority=NotificationPriority.NORMAL,
            channel=NotificationChannel.IN_APP,
            reference_type="  appointment  ",
        )

        assert notification.title == "Test title"
        assert notification.message == "Test message"
        assert notification.reference_type == "appointment"


def test_create_notification_rejects_invalid_clinic_id(
    app,
    user,
):
    with app.app_context():
        with pytest.raises(ValidationError):
            notification_service.create_notification(
                clinic_id=0,
                user_id=user.id,
                title="Test",
                message="Message",
                notification_type=NotificationType.SYSTEM,
            )


def test_create_notification_rejects_invalid_user_id(
    app,
    clinic,
):
    with app.app_context():
        with pytest.raises(ValidationError):
            notification_service.create_notification(
                clinic_id=clinic.id,
                user_id=0,
                title="Test",
                message="Message",
                notification_type=NotificationType.SYSTEM,
            )


def test_create_notification_rejects_missing_user(
    app,
    clinic,
):
    with app.app_context():
        with pytest.raises(NotFoundError):
            notification_service.create_notification(
                clinic_id=clinic.id,
                user_id=999999,
                title="Test",
                message="Message",
                notification_type=NotificationType.SYSTEM,
            )


def test_create_notification_rejects_wrong_clinic_user(
    app,
    make_clinic,
    make_user,
    clinic,
):
    with app.app_context():
        other_clinic = make_clinic()
        other_user = make_user(clinic=other_clinic)

        with pytest.raises(NotFoundError):
            notification_service.create_notification(
                clinic_id=clinic.id,
                user_id=other_user.id,
                title="Test",
                message="Message",
                notification_type=NotificationType.SYSTEM,
            )


def test_create_notification_rejects_inactive_user(
    app,
    clinic,
    make_user,
):
    with app.app_context():
        inactive_user = make_user(
            clinic=clinic,
            is_active=False,
        )

        with pytest.raises(ValidationError):
            notification_service.create_notification(
                clinic_id=clinic.id,
                user_id=inactive_user.id,
                title="Test",
                message="Message",
                notification_type=NotificationType.SYSTEM,
            )


def test_create_notification_rejects_blank_title(
    app,
    clinic,
    user,
):
    with app.app_context():
        with pytest.raises(ValidationError):
            notification_service.create_notification(
                clinic_id=clinic.id,
                user_id=user.id,
                title="   ",
                message="Message",
                notification_type=NotificationType.SYSTEM,
            )


def test_create_notification_rejects_blank_message(
    app,
    clinic,
    user,
):
    with app.app_context():
        with pytest.raises(ValidationError):
            notification_service.create_notification(
                clinic_id=clinic.id,
                user_id=user.id,
                title="Title",
                message="   ",
                notification_type=NotificationType.SYSTEM,
            )


def test_create_notification_rejects_long_title(
    app,
    clinic,
    user,
):
    with app.app_context():
        with pytest.raises(ValidationError):
            notification_service.create_notification(
                clinic_id=clinic.id,
                user_id=user.id,
                title="x" * 256,
                message="Message",
                notification_type=NotificationType.SYSTEM,
            )


def test_create_notification_rejects_long_reference_type(
    app,
    clinic,
    user,
):
    with app.app_context():
        with pytest.raises(ValidationError):
            notification_service.create_notification(
                clinic_id=clinic.id,
                user_id=user.id,
                title="Title",
                message="Message",
                notification_type=NotificationType.SYSTEM,
                reference_type="x" * 51,
            )


def test_create_notification_rejects_invalid_reference_id(
    app,
    clinic,
    user,
):
    with app.app_context():
        with pytest.raises(ValidationError):
            notification_service.create_notification(
                clinic_id=clinic.id,
                user_id=user.id,
                title="Title",
                message="Message",
                notification_type=NotificationType.SYSTEM,
                reference_id=0,
            )


# ============================================================================
# QUEUE DELIVERY
# ============================================================================


def test_queue_in_app_notification_does_not_queue_celery(
    app,
    notification,
    monkeypatch,
):
    with app.app_context():
        notification_id = notification.id
        called = False

        def fake_delay(*args, **kwargs):
            nonlocal called
            called = True

        monkeypatch.setattr(
            notification_service.deliver_notification,
            "delay",
            fake_delay,
        )

        result = notification_service.queue_notification_delivery(
            notification_id
        )

        assert result.id == notification_id
        assert called is False


@pytest.mark.parametrize(
    "channel",
    [
        NotificationChannel.EMAIL,
        NotificationChannel.SMS,
        NotificationChannel.PUSH,
    ],
)
def test_queue_external_notification(
    app,
    make_notification,
    clinic,
    user,
    channel,
    monkeypatch,
):
    with app.app_context():
        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            channel=channel,
        )
        notification_id = notification.id

        queued_ids = []

        def fake_delay(notification_id):
            queued_ids.append(notification_id)

        monkeypatch.setattr(
            notification_service.deliver_notification,
            "delay",
            fake_delay,
        )

        result = notification_service.queue_notification_delivery(
            notification_id
        )

        assert result.id == notification_id
        assert queued_ids == [notification_id]


@pytest.mark.parametrize(
    "status",
    [
        NotificationStatus.SENT,
        NotificationStatus.DELIVERED,
        NotificationStatus.READ,
    ],
)
def test_queue_rejects_invalid_status(
    app,
    make_notification,
    clinic,
    user,
    status,
):
    with app.app_context():
        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            channel=NotificationChannel.EMAIL,
            status=status,
        )
        notification_id = notification.id

        with pytest.raises(ConflictError):
            notification_service.queue_notification_delivery(
                notification_id
            )


def test_queue_allows_failed_notification(
    app,
    make_notification,
    clinic,
    user,
    monkeypatch,
):
    with app.app_context():
        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            channel=NotificationChannel.EMAIL,
            status=NotificationStatus.FAILED,
        )
        notification_id = notification.id

        queued_ids = []

        monkeypatch.setattr(
            notification_service.deliver_notification,
            "delay",
            lambda notification_id: queued_ids.append(notification_id),
        )

        result = notification_service.queue_notification_delivery(
            notification_id
        )

        assert result.id == notification_id
        assert queued_ids == [notification_id]


# ============================================================================
# CELERY DELIVERY
# ============================================================================


def test_deliver_notification_invalid_id_returns_false(
    app,
):
    with app.app_context():
        assert notification_service.deliver_notification(0) is False
        assert notification_service.deliver_notification(-1) is False


def test_deliver_notification_missing_notification_returns_false(
    app,
):
    with app.app_context():
        assert (
            notification_service.deliver_notification(999999)
            is False
        )


@pytest.mark.parametrize(
    "status",
    [
        NotificationStatus.DELIVERED,
        NotificationStatus.READ,
    ],
)
def test_deliver_notification_is_idempotent(
    app,
    make_notification,
    clinic,
    user,
    status,
    monkeypatch,
):
    with app.app_context():
        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            channel=NotificationChannel.EMAIL,
            status=status,
        )
        notification_id = notification.id

        called = False

        def fake_provider(_notification):
            nonlocal called
            called = True
            return True

        monkeypatch.setattr(
            notification_service,
            "_deliver_with_provider",
            fake_provider,
        )

        result = notification_service.deliver_notification(
            notification_id
        )

        assert result is True
        assert called is False


def test_deliver_in_app_notification_returns_false(
    app,
    notification,
):
    with app.app_context():
        notification_id = notification.id

        assert (
            notification_service.deliver_notification(
                notification_id
            )
            is False
        )


def test_deliver_notification_success(
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
            channel=NotificationChannel.EMAIL,
        )
        notification_id = notification.id

        monkeypatch.setattr(
            notification_service,
            "_deliver_with_provider",
            lambda _notification: True,
        )

        result = notification_service.deliver_notification(
            notification_id
        )

        notification = db_session.get(
            Notification,
            notification_id,
        )

        assert notification is not None
        assert result is True
        assert notification.status == NotificationStatus.DELIVERED
        assert notification.sent_at is not None
        assert notification.delivered_at is not None
        assert notification.error_message is None


def test_deliver_notification_provider_rejection_marks_failed(
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
            channel=NotificationChannel.EMAIL,
        )
        notification_id = notification.id

        # The Celery failure path performs a rollback.
        # Commit the fixture record first so the rollback does not
        # remove the notification itself.
        db_session.commit()

        monkeypatch.setattr(
            notification_service,
            "_deliver_with_provider",
            lambda _notification: False,
        )

        with pytest.raises(RuntimeError):
            notification_service.deliver_notification(
                notification_id
            )

        notification = db_session.get(
            Notification,
            notification_id,
        )

        assert notification is not None
        assert notification.status == NotificationStatus.FAILED
        assert notification.failed_at is not None
        assert notification.retry_count == 1
        assert (
            notification.error_message
            == "Notification provider rejected delivery"
        )


def test_deliver_notification_provider_exception_marks_failed(
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
            channel=NotificationChannel.EMAIL,
        )
        notification_id = notification.id

        # Persist the notification before the worker transaction.
        # The worker rolls back when the provider raises.
        db_session.commit()

        def failing_provider(_notification):
            raise RuntimeError("Provider timeout")

        monkeypatch.setattr(
            notification_service,
            "_deliver_with_provider",
            failing_provider,
        )

        with pytest.raises(RuntimeError, match="Provider timeout"):
            notification_service.deliver_notification(
                notification_id
            )

        notification = db_session.get(
            Notification,
            notification_id,
        )

        assert notification is not None
        assert notification.status == NotificationStatus.FAILED
        assert notification.failed_at is not None
        assert notification.retry_count == 1
        assert notification.error_message == "Provider timeout"


def test_deliver_notification_truncates_provider_error(
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
            channel=NotificationChannel.EMAIL,
        )
        notification_id = notification.id

        # Persist the notification before the worker transaction.
        # Otherwise the worker rollback can roll back the fixture insert.
        db_session.commit()

        long_error = "x" * 5000

        def failing_provider(_notification):
            raise RuntimeError(long_error)

        monkeypatch.setattr(
            notification_service,
            "_deliver_with_provider",
            failing_provider,
        )

        with pytest.raises(RuntimeError):
            notification_service.deliver_notification(
                notification_id
            )

        notification = db_session.get(
            Notification,
            notification_id,
        )

        assert notification is not None
        assert notification.status == NotificationStatus.FAILED
        assert notification.failed_at is not None
        assert notification.retry_count == 1
        assert len(notification.error_message) == 2000


# ============================================================================
# GET USER NOTIFICATIONS
# ============================================================================


def test_get_user_notifications_returns_user_notifications(
    app,
    make_notification,
    clinic,
    user,
):
    with app.app_context():
        first = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            title="First",
        )

        second = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            title="Second",
        )

        result = notification_service.get_user_notifications(
            user_id=user.id,
            clinic_id=clinic.id,
        )

        ids = [item.id for item in result]

        assert first.id in ids
        assert second.id in ids


def test_get_user_notifications_unread_only(
    app,
    make_notification,
    clinic,
    user,
):
    with app.app_context():
        unread = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            is_read=False,
        )

        make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            is_read=True,
            status=NotificationStatus.READ,
        )

        result = notification_service.get_user_notifications(
            user_id=user.id,
            clinic_id=clinic.id,
            unread_only=True,
        )

        assert [item.id for item in result] == [unread.id]


def test_get_user_notifications_is_tenant_scoped(
    app,
    make_notification,
    make_clinic,
    make_user,
    clinic,
    user,
):
    with app.app_context():
        other_clinic = make_clinic()
        other_user = make_user(clinic=other_clinic)

        make_notification(
            clinic_id=other_clinic.id,
            user_id=other_user.id,
        )

        result = notification_service.get_user_notifications(
            user_id=user.id,
            clinic_id=clinic.id,
        )

        assert all(
            item.clinic_id == clinic.id
            and item.user_id == user.id
            for item in result
        )


def test_get_user_notifications_orders_newest_first(
    app,
    make_notification,
    clinic,
    user,
):
    with app.app_context():
        first = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
        )

        second = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
        )

        result = notification_service.get_user_notifications(
            user_id=user.id,
            clinic_id=clinic.id,
        )

        assert result[0].id == second.id
        assert result[1].id == first.id


# ============================================================================
# GET SINGLE NOTIFICATION
# ============================================================================


def test_get_notification_for_user_success(
    app,
    notification,
    user,
    clinic,
):
    with app.app_context():
        notification_id = notification.id

        result = notification_service.get_notification_for_user(
            notification_id=notification_id,
            user_id=user.id,
            clinic_id=clinic.id,
        )

        assert result.id == notification_id


def test_get_notification_for_user_rejects_wrong_user(
    app,
    notification,
    make_user,
    clinic,
):
    with app.app_context():
        notification_id = notification.id
        other_user = make_user(clinic=clinic)

        with pytest.raises(NotFoundError):
            notification_service.get_notification_for_user(
                notification_id=notification_id,
                user_id=other_user.id,
                clinic_id=clinic.id,
            )


def test_get_notification_for_user_rejects_wrong_clinic(
    app,
    notification,
    make_clinic,
    make_user,
):
    with app.app_context():
        notification_id = notification.id
        other_clinic = make_clinic()
        other_user = make_user(clinic=other_clinic)

        with pytest.raises(NotFoundError):
            notification_service.get_notification_for_user(
                notification_id=notification_id,
                user_id=other_user.id,
                clinic_id=other_clinic.id,
            )


# ============================================================================
# MARK NOTIFICATION READ
# ============================================================================


def test_mark_notification_read(
    app,
    notification,
    user,
    clinic,
    db_session,
):
    with app.app_context():
        notification_id = notification.id

        result = notification_service.mark_notification_read(
            notification_id=notification_id,
            user_id=user.id,
            clinic_id=clinic.id,
        )

        notification = db_session.get(
            Notification,
            notification_id,
        )

        assert notification is not None
        assert result.id == notification_id
        assert notification.is_read is True
        assert notification.read_at is not None
        assert notification.status == NotificationStatus.READ


def test_mark_notification_read_is_idempotent(
    app,
    make_notification,
    clinic,
    user,
):
    with app.app_context():
        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            is_read=True,
            status=NotificationStatus.READ,
        )

        notification_id = notification.id
        original_read_at = notification.read_at

        result = notification_service.mark_notification_read(
            notification_id=notification_id,
            user_id=user.id,
            clinic_id=clinic.id,
        )

        assert result.id == notification_id
        assert result.is_read is True
        assert result.read_at == original_read_at


def test_mark_notification_read_rejects_wrong_user(
    app,
    notification,
    make_user,
    clinic,
):
    with app.app_context():
        notification_id = notification.id
        other_user = make_user(clinic=clinic)

        with pytest.raises(NotFoundError):
            notification_service.mark_notification_read(
                notification_id=notification_id,
                user_id=other_user.id,
                clinic_id=clinic.id,
            )


# ============================================================================
# MARK ALL READ
# ============================================================================


def test_mark_all_notifications_read(
    app,
    make_notification,
    clinic,
    user,
):
    with app.app_context():
        make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            is_read=False,
        )

        make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            is_read=False,
        )

        count = notification_service.mark_all_notifications_read(
            user_id=user.id,
            clinic_id=clinic.id,
        )

        assert count == 2


def test_mark_all_notifications_read_returns_zero_when_none_unread(
    app,
    make_notification,
    clinic,
    user,
):
    with app.app_context():
        make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            is_read=True,
            status=NotificationStatus.READ,
        )

        count = notification_service.mark_all_notifications_read(
            user_id=user.id,
            clinic_id=clinic.id,
        )

        assert count == 0


# ============================================================================
# UPDATE DELIVERY STATUS
# ============================================================================


def test_update_delivery_status_sent(
    app,
    notification,
    db_session,
):
    with app.app_context():
        notification_id = notification.id

        result = notification_service.update_notification_delivery_status(
            notification_id=notification_id,
            status=NotificationStatus.SENT,
        )

        notification = db_session.get(
            Notification,
            notification_id,
        )

        assert notification is not None
        assert result.id == notification_id
        assert notification.status == NotificationStatus.SENT
        assert notification.sent_at is not None


def test_update_delivery_status_delivered(
    app,
    notification,
    db_session,
):
    with app.app_context():
        notification_id = notification.id

        result = notification_service.update_notification_delivery_status(
            notification_id=notification_id,
            status=NotificationStatus.DELIVERED,
        )

        notification = db_session.get(
            Notification,
            notification_id,
        )

        assert notification is not None
        assert result.id == notification_id
        assert notification.status == NotificationStatus.DELIVERED
        assert notification.sent_at is not None
        assert notification.delivered_at is not None
        assert notification.error_message is None


def test_update_delivery_status_read(
    app,
    notification,
    db_session,
):
    with app.app_context():
        notification_id = notification.id

        result = notification_service.update_notification_delivery_status(
            notification_id=notification_id,
            status=NotificationStatus.READ,
        )

        notification = db_session.get(
            Notification,
            notification_id,
        )

        assert notification is not None
        assert result.id == notification_id
        assert notification.status == NotificationStatus.READ
        assert notification.is_read is True
        assert notification.read_at is not None
        assert notification.delivered_at is not None


def test_update_delivery_status_failed(
    app,
    notification,
    db_session,
):
    with app.app_context():
        notification_id = notification.id

        result = notification_service.update_notification_delivery_status(
            notification_id=notification_id,
            status=NotificationStatus.FAILED,
            error_message="Provider timeout",
        )

        notification = db_session.get(
            Notification,
            notification_id,
        )

        assert notification is not None
        assert result.id == notification_id
        assert notification.status == NotificationStatus.FAILED
        assert notification.failed_at is not None
        assert notification.retry_count == 1
        assert notification.error_message == "Provider timeout"


def test_update_delivery_status_pending_clears_error(
    app,
    make_notification,
    clinic,
    user,
    db_session,
):
    with app.app_context():
        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            status=NotificationStatus.FAILED,
            error_message="Previous failure",
            retry_count=2,
        )
        notification_id = notification.id

        result = notification_service.update_notification_delivery_status(
            notification_id=notification_id,
            status=NotificationStatus.PENDING,
        )

        notification = db_session.get(
            Notification,
            notification_id,
        )

        assert notification is not None
        assert result.id == notification_id
        assert notification.status == NotificationStatus.PENDING
        assert notification.error_message is None
        assert notification.retry_count == 2


# ============================================================================
# RETRY NOTIFICATION
# ============================================================================


def test_retry_notification_success(
    app,
    make_notification,
    clinic,
    user,
    db_session,
):
    with app.app_context():
        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            channel=NotificationChannel.EMAIL,
            status=NotificationStatus.FAILED,
            failed_at=datetime.now(timezone.utc),
            error_message="Provider timeout",
            retry_count=2,
        )
        notification_id = notification.id

        result = notification_service.retry_notification(
            notification_id
        )

        notification = db_session.get(
            Notification,
            notification_id,
        )

        assert notification is not None
        assert result.id == notification_id
        assert notification.status == NotificationStatus.PENDING
        assert notification.failed_at is None
        assert notification.error_message is None
        assert notification.retry_count == 2


def test_retry_notification_rejects_non_failed_status(
    app,
    notification,
):
    with app.app_context():
        notification_id = notification.id

        with pytest.raises(ConflictError):
            notification_service.retry_notification(
                notification_id
            )


def test_retry_in_app_notification_rejected(
    app,
    make_notification,
    clinic,
    user,
):
    with app.app_context():
        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            channel=NotificationChannel.IN_APP,
            status=NotificationStatus.FAILED,
        )
        notification_id = notification.id

        with pytest.raises(ConflictError):
            notification_service.retry_notification(
                notification_id
            )


# ============================================================================
# POSITIVE-ID VALIDATION
# ============================================================================


@pytest.mark.parametrize(
    "notification_id",
    [
        0,
        -1,
        True,
        False,
    ],
)
def test_get_notification_for_user_rejects_invalid_notification_id(
    app,
    notification_id,
):
    with app.app_context():
        with pytest.raises(ValidationError):
            notification_service.get_notification_for_user(
                notification_id=notification_id,
                user_id=1,
                clinic_id=1,
            )


@pytest.mark.parametrize(
    "user_id",
    [
        0,
        -1,
        True,
        False,
    ],
)
def test_get_user_notifications_rejects_invalid_user_id(
    app,
    clinic,
    user_id,
):
    with app.app_context():
        with pytest.raises(ValidationError):
            notification_service.get_user_notifications(
                user_id=user_id,
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
def test_get_user_notifications_rejects_invalid_clinic_id(
    app,
    user,
    clinic_id,
):
    with app.app_context():
        with pytest.raises(ValidationError):
            notification_service.get_user_notifications(
                user_id=user.id,
                clinic_id=clinic_id,
            )