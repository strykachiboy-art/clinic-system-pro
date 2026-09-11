from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from app.core.enums.notification_enums import (
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)
from app.core.enums.role_enums import Role
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


# ============================================================================
# PROVIDER BOUNDARY
# ============================================================================


def test_deliver_with_provider_push_uses_factory(
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
            channel=NotificationChannel.PUSH,
        )

        provider = Mock()
        provider.send.return_value = True

        factory = Mock(
            return_value=provider,
        )

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            factory,
        )

        result = (
            notification_service
            ._deliver_with_provider(
                notification
            )
        )

        assert result is True

        factory.assert_called_once_with(
            NotificationChannel.PUSH,
            clinic_id=clinic.id,
        )

        provider.send.assert_called_once_with(
            notification=notification,
        )


def test_deliver_with_provider_patient_email_uses_patient_email(
    app,
    clinic,
    make_user,
    make_patient,
    make_notification,
    monkeypatch,
):
    with app.app_context():
        user = make_user(
            clinic=clinic,
            role=Role.PATIENT,
            email="patient-user@test.com",
        )

        patient = make_patient(
            clinic,
            user_id=user.id,
            email="patient@test.com",
            phone="+2348011111111",
        )

        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            channel=NotificationChannel.EMAIL,
        )

        provider = Mock()
        provider.send.return_value = True

        factory = Mock(
            return_value=provider,
        )

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            factory,
        )

        result = notification_service._deliver_with_provider(
            notification
        )

        assert result is True

        factory.assert_called_once_with(
            NotificationChannel.EMAIL,
            clinic_id=clinic.id,
        )

        provider.send.assert_called_once_with(
            notification=notification,
            email="patient@test.com",
        )

        assert patient.email == "patient@test.com"


def test_deliver_with_provider_patient_email_falls_back_to_user_email(
    app,
    clinic,
    make_user,
    make_patient,
    make_notification,
    monkeypatch,
):
    with app.app_context():
        user = make_user(
            clinic=clinic,
            role=Role.PATIENT,
            email="patient-user@test.com",
        )

        make_patient(
            clinic,
            user_id=user.id,
            email=None,
            phone="+2348011111111",
        )

        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            channel=NotificationChannel.EMAIL,
        )

        provider = Mock()
        provider.send.return_value = True

        factory = Mock(
            return_value=provider,
        )

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            factory,
        )

        result = notification_service._deliver_with_provider(
            notification
        )

        assert result is True

        factory.assert_called_once_with(
            NotificationChannel.EMAIL,
            clinic_id=clinic.id,
        )

        provider.send.assert_called_once_with(
            notification=notification,
            email="patient-user@test.com",
        )


def test_deliver_with_provider_patient_sms_uses_patient_phone(
    app,
    clinic,
    make_user,
    make_patient,
    make_notification,
    monkeypatch,
):
    with app.app_context():
        user = make_user(
            clinic=clinic,
            role=Role.PATIENT,
            email="patient-user@test.com",
        )

        patient = make_patient(
            clinic,
            user_id=user.id,
            email="patient@test.com",
            phone="+2348022222222",
        )

        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            channel=NotificationChannel.SMS,
        )

        provider = Mock()
        provider.send.return_value = True

        factory = Mock(
            return_value=provider,
        )

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            factory,
        )

        result = notification_service._deliver_with_provider(
            notification
        )

        assert result is True

        factory.assert_called_once_with(
            NotificationChannel.SMS,
            clinic_id=clinic.id,
        )

        provider.send.assert_called_once_with(
            notification=notification,
            phone="+2348022222222",
        )

        assert patient.phone == "+2348022222222"


def test_deliver_with_provider_staff_email_uses_staff_email(
    app,
    clinic,
    make_staff,
    make_notification,
    monkeypatch,
):
    with app.app_context():
        staff = make_staff(
            clinic,
            role=Role.DOCTOR,
            email="doctor@test.com",
            phone="+2348033333333",
        )

        notification = make_notification(
            clinic_id=clinic.id,
            user_id=staff.user_id,
            channel=NotificationChannel.EMAIL,
        )

        provider = Mock()
        provider.send.return_value = True

        factory = Mock(
            return_value=provider,
        )

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            factory,
        )

        result = notification_service._deliver_with_provider(
            notification
        )

        assert result is True

        factory.assert_called_once_with(
            NotificationChannel.EMAIL,
            clinic_id=clinic.id,
        )

        provider.send.assert_called_once_with(
            notification=notification,
            email="doctor@test.com",
        )


def test_deliver_with_provider_staff_email_falls_back_to_user_email(
    app,
    clinic,
    make_staff,
    make_notification,
    monkeypatch,
):
    with app.app_context():
        staff = make_staff(
            clinic,
            role=Role.DOCTOR,
            email=None,
            phone="+2348044444444",
            user_overrides={
                "email": "doctor-user@test.com",
            },
        )

        notification = make_notification(
            clinic_id=clinic.id,
            user_id=staff.user_id,
            channel=NotificationChannel.EMAIL,
        )

        provider = Mock()
        provider.send.return_value = True

        factory = Mock(
            return_value=provider,
        )

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            factory,
        )

        result = notification_service._deliver_with_provider(
            notification
        )

        assert result is True

        factory.assert_called_once_with(
            NotificationChannel.EMAIL,
            clinic_id=clinic.id,
        )

        provider.send.assert_called_once_with(
            notification=notification,
            email="doctor-user@test.com",
        )


def test_deliver_with_provider_staff_sms_uses_staff_phone(
    app,
    clinic,
    make_staff,
    make_notification,
    monkeypatch,
):
    with app.app_context():
        staff = make_staff(
            clinic,
            role=Role.DOCTOR,
            email="doctor@test.com",
            phone="+2348055555555",
        )

        notification = make_notification(
            clinic_id=clinic.id,
            user_id=staff.user_id,
            channel=NotificationChannel.SMS,
        )

        provider = Mock()
        provider.send.return_value = True

        factory = Mock(
            return_value=provider,
        )

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            factory,
        )

        result = notification_service._deliver_with_provider(
            notification
        )

        assert result is True

        factory.assert_called_once_with(
            NotificationChannel.SMS,
            clinic_id=clinic.id,
        )

        provider.send.assert_called_once_with(
            notification=notification,
            phone="+2348055555555",
        )


def test_deliver_with_provider_rejects_missing_patient_profile(
    app,
    clinic,
    make_user,
    make_notification,
    monkeypatch,
):
    with app.app_context():
        user = make_user(
            clinic=clinic,
            role=Role.PATIENT,
        )

        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            channel=NotificationChannel.EMAIL,
        )

        provider = Mock()

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            Mock(return_value=provider),
        )

        with pytest.raises(
            NotFoundError,
            match="Patient profile",
        ):
            notification_service._deliver_with_provider(
                notification
            )

        provider.send.assert_not_called()


def test_deliver_with_provider_rejects_missing_staff_profile(
    app,
    clinic,
    make_user,
    make_notification,
    monkeypatch,
):
    with app.app_context():
        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            channel=NotificationChannel.EMAIL,
        )

        provider = Mock()

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            Mock(return_value=provider),
        )

        with pytest.raises(
            NotFoundError,
            match="Staff profile",
        ):
            notification_service._deliver_with_provider(
                notification
            )

        provider.send.assert_not_called()


def test_deliver_with_provider_rejects_missing_patient_email(
    app,
    clinic,
    make_user,
    make_patient,
    make_notification,
    monkeypatch,
):
    with app.app_context():
        user = make_user(
            clinic=clinic,
            role=Role.PATIENT,
            email="",
        )

        make_patient(
            clinic,
            user_id=user.id,
            email=None,
            phone="+2348066666666",
        )

        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            channel=NotificationChannel.EMAIL,
        )

        provider = Mock()

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            Mock(return_value=provider),
        )

        with pytest.raises(
            ValidationError,
            match="recipient email",
        ):
            notification_service._deliver_with_provider(
                notification
            )

        provider.send.assert_not_called()


def test_deliver_with_provider_rejects_missing_patient_phone(
    app,
    clinic,
    make_user,
    make_patient,
    make_notification,
    monkeypatch,
):
    with app.app_context():
        user = make_user(
            clinic=clinic,
            role=Role.PATIENT,
        )

        make_patient(
            clinic,
            user_id=user.id,
            email="patient@test.com",
            phone=None,
        )

        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            channel=NotificationChannel.SMS,
        )

        provider = Mock()

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            Mock(return_value=provider),
        )

        with pytest.raises(
            ValidationError,
            match="recipient phone number",
        ):
            notification_service._deliver_with_provider(
                notification
            )

        provider.send.assert_not_called()


def test_deliver_with_provider_rejects_cross_clinic_patient(
    app,
    make_clinic,
    make_user,
    make_patient,
    make_notification,
    clinic,
    monkeypatch,
):
    with app.app_context():
        other_clinic = make_clinic()

        user = make_user(
            clinic=clinic,
            role=Role.PATIENT,
        )

        make_patient(
            other_clinic,
            user_id=user.id,
            email="other@test.com",
            phone="+2348077777777",
        )

        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            channel=NotificationChannel.EMAIL,
        )

        provider = Mock()

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            Mock(return_value=provider),
        )

        with pytest.raises(
            NotFoundError,
            match="Patient profile",
        ):
            notification_service._deliver_with_provider(
                notification
            )

        provider.send.assert_not_called()


def test_deliver_with_provider_rejects_cross_clinic_staff(
    app,
    make_clinic,
    make_staff,
    make_notification,
    clinic,
    monkeypatch,
):
    with app.app_context():
        other_clinic = make_clinic()

        staff = make_staff(
            other_clinic,
            role=Role.DOCTOR,
            email="other-doctor@test.com",
            phone="+2348088888888",
        )

        user_id = staff.user_id

        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user_id,
            channel=NotificationChannel.EMAIL,
        )

        provider = Mock()

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            Mock(return_value=provider),
        )

        with pytest.raises(
            NotFoundError,
            match="Notification recipient",
        ):
            notification_service._deliver_with_provider(
                notification
            )

        provider.send.assert_not_called()


def test_deliver_with_provider_rejects_inactive_user(
    app,
    clinic,
    make_user,
    make_patient,
    make_notification,
    monkeypatch,
):
    with app.app_context():
        user = make_user(
            clinic=clinic,
            role=Role.PATIENT,
            is_active=False,
        )

        make_patient(
            clinic,
            user_id=user.id,
            email="inactive@test.com",
            phone="+2348099999999",
        )

        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            channel=NotificationChannel.EMAIL,
        )

        provider = Mock()

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            Mock(return_value=provider),
        )

        with pytest.raises(
            ValidationError,
            match="inactive",
        ):
            notification_service._deliver_with_provider(
                notification
            )

        provider.send.assert_not_called()


def test_deliver_with_provider_rejects_unsupported_channel(
    app,
    notification,
):
    with app.app_context():
        notification.channel = "unsupported"

        with pytest.raises(
            ValidationError,
            match="Unsupported notification channel",
        ):
            notification_service._deliver_with_provider(
                notification
            )


def test_deliver_notification_push_uses_provider(
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
        )
        notification_id = notification.id

        provider = Mock()
        provider.send.return_value = True

        factory = Mock(
            return_value=provider,
        )

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            factory,
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

        factory.assert_called_once_with(
            NotificationChannel.PUSH,
            clinic_id=clinic.id,
        )

        provider.send.assert_called_once_with(
            notification=notification,
        )


def test_deliver_notification_push_provider_rejection_marks_failed(
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
        )
        notification_id = notification.id

        db_session.commit()

        provider = Mock()
        provider.send.return_value = False

        factory = Mock(
            return_value=provider,
        )

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            factory,
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

        factory.assert_called_once_with(
            NotificationChannel.PUSH,
            clinic_id=clinic.id,
        )

        provider.send.assert_called_once_with(
            notification=notification,
        )


def test_deliver_notification_push_provider_exception_marks_failed(
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
        )
        notification_id = notification.id

        db_session.commit()

        provider = Mock()
        provider.send.side_effect = RuntimeError(
            "Push provider timeout"
        )

        factory = Mock(
            return_value=provider,
        )

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            factory,
        )

        with pytest.raises(
            RuntimeError,
            match="Push provider timeout",
        ):
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
            == "Push provider timeout"
        )

        factory.assert_called_once_with(
            NotificationChannel.PUSH,
            clinic_id=clinic.id,
        )

        provider.send.assert_called_once_with(
            notification=notification,
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

        db_session.commit()

        def failing_provider(_notification):
            raise RuntimeError("Provider timeout")

        monkeypatch.setattr(
            notification_service,
            "_deliver_with_provider",
            failing_provider,
        )

        with pytest.raises(
            RuntimeError,
            match="Provider timeout",
        ):
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

        ids = [item.id for item in result["items"]]

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

        assert [item.id for item in result["items"]] == [unread.id]


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
            for item in result["items"]
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

        assert result["items"][0].id == second.id
        assert result["items"][1].id == first.id


def test_get_user_notifications_returns_default_pagination(
    app,
    make_notification,
    clinic,
    user,
):
    with app.app_context():
        for index in range(3):
            make_notification(
                clinic_id=clinic.id,
                user_id=user.id,
                title=f"Notification {index}",
            )

        result = notification_service.get_user_notifications(
            user_id=user.id,
            clinic_id=clinic.id,
        )

        assert result["page"] == 1
        assert result["per_page"] == 50
        assert result["total"] == 3
        assert result["pages"] == 1
        assert result["has_next"] is False
        assert result["has_prev"] is False
        assert len(result["items"]) == 3


def test_get_user_notifications_custom_pagination(
    app,
    make_notification,
    clinic,
    user,
):
    with app.app_context():
        for index in range(5):
            make_notification(
                clinic_id=clinic.id,
                user_id=user.id,
                title=f"Notification {index}",
            )

        result = notification_service.get_user_notifications(
            user_id=user.id,
            clinic_id=clinic.id,
            page=2,
            per_page=2,
        )

        assert result["page"] == 2
        assert result["per_page"] == 2
        assert result["total"] == 5
        assert result["pages"] == 3
        assert result["has_next"] is True
        assert result["has_prev"] is True
        assert len(result["items"]) == 2


def test_get_user_notifications_first_page(
    app,
    make_notification,
    clinic,
    user,
):
    with app.app_context():
        notifications = [
            make_notification(
                clinic_id=clinic.id,
                user_id=user.id,
            )
            for _ in range(5)
        ]

        result = notification_service.get_user_notifications(
            user_id=user.id,
            clinic_id=clinic.id,
            page=1,
            per_page=2,
        )

        assert [item.id for item in result["items"]] == [
            notifications[-1].id,
            notifications[-2].id,
        ]
        assert result["has_prev"] is False
        assert result["has_next"] is True


def test_get_user_notifications_middle_page(
    app,
    make_notification,
    clinic,
    user,
):
    with app.app_context():
        notifications = [
            make_notification(
                clinic_id=clinic.id,
                user_id=user.id,
            )
            for _ in range(5)
        ]

        result = notification_service.get_user_notifications(
            user_id=user.id,
            clinic_id=clinic.id,
            page=2,
            per_page=2,
        )

        assert [item.id for item in result["items"]] == [
            notifications[-3].id,
            notifications[-4].id,
        ]
        assert result["has_prev"] is True
        assert result["has_next"] is True


def test_get_user_notifications_last_page(
    app,
    make_notification,
    clinic,
    user,
):
    with app.app_context():
        notifications = [
            make_notification(
                clinic_id=clinic.id,
                user_id=user.id,
            )
            for _ in range(5)
        ]

        result = notification_service.get_user_notifications(
            user_id=user.id,
            clinic_id=clinic.id,
            page=3,
            per_page=2,
        )

        assert [item.id for item in result["items"]] == [
            notifications[0].id,
        ]
        assert result["has_prev"] is True
        assert result["has_next"] is False


def test_get_user_notifications_empty_page(
    app,
    make_notification,
    clinic,
    user,
):
    with app.app_context():
        for _ in range(2):
            make_notification(
                clinic_id=clinic.id,
                user_id=user.id,
            )

        result = notification_service.get_user_notifications(
            user_id=user.id,
            clinic_id=clinic.id,
            page=2,
            per_page=2,
        )

        assert result["items"] == []
        assert result["page"] == 2
        assert result["per_page"] == 2
        assert result["total"] == 2
        assert result["pages"] == 1
        assert result["has_prev"] is True
        assert result["has_next"] is False


def test_get_user_notifications_empty_collection(
    app,
    clinic,
    user,
):
    with app.app_context():
        result = notification_service.get_user_notifications(
            user_id=user.id,
            clinic_id=clinic.id,
        )

        assert result["items"] == []
        assert result["page"] == 1
        assert result["per_page"] == 50
        assert result["total"] == 0
        assert result["pages"] == 0
        assert result["has_next"] is False
        assert result["has_prev"] is False


def test_get_user_notifications_unread_only_is_paginated(
    app,
    make_notification,
    clinic,
    user,
):
    with app.app_context():
        unread_notifications = [
            make_notification(
                clinic_id=clinic.id,
                user_id=user.id,
                is_read=False,
            )
            for _ in range(5)
        ]

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
            page=2,
            per_page=2,
        )

        assert result["total"] == 5
        assert result["pages"] == 3
        assert len(result["items"]) == 2
        assert result["has_prev"] is True
        assert result["has_next"] is True

        assert [item.id for item in result["items"]] == [
            unread_notifications[-3].id,
            unread_notifications[-4].id,
        ]


@pytest.mark.parametrize(
    "page",
    [
        0,
        -1,
        True,
        False,
    ],
)
def test_get_user_notifications_rejects_invalid_page(
    app,
    clinic,
    user,
    page,
):
    with app.app_context():
        with pytest.raises(ValidationError):
            notification_service.get_user_notifications(
                user_id=user.id,
                clinic_id=clinic.id,
                page=page,
            )


@pytest.mark.parametrize(
    "per_page",
    [
        0,
        -1,
        True,
        False,
        501,
    ],
)
def test_get_user_notifications_rejects_invalid_per_page(
    app,
    clinic,
    user,
    per_page,
):
    with app.app_context():
        with pytest.raises(ValidationError):
            notification_service.get_user_notifications(
                user_id=user.id,
                clinic_id=clinic.id,
                per_page=per_page,
            )


def test_get_user_notifications_allows_max_per_page(
    app,
    clinic,
    user,
):
    with app.app_context():
        result = notification_service.get_user_notifications(
            user_id=user.id,
            clinic_id=clinic.id,
            per_page=500,
        )

        assert result["per_page"] == 500


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