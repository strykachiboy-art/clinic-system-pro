from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.audit.models.audit_model import AuditLog
from app.core.enums.audit_enums import AuditAction
from app.core.enums.notification_enums import (
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)
from app.core.enums.role_enums import Role
from app.core.notifications.models.notification_models import (
    Notification,
)
from app.core.notifications.services import notification_service
from app.extensions import celery
from app.modules.appointment.models.appointment_model import (
    Appointment,
)
from app.modules.appointment.services import appointment_service


def _headers(login: dict) -> dict[str, str]:
    return {
        "Authorization": (
            f"Bearer {login['access_token']}"
        ),
    }


def _audit_rows(
    db,
    entity_type: str,
    entity_id: int,
):
    return (
        db.session.execute(
            db.select(AuditLog)
            .where(
                AuditLog.entity_type == entity_type,
                AuditLog.entity_id == entity_id,
            )
            .order_by(
                AuditLog.id.asc(),
            )
        )
        .scalars()
        .all()
    )


def _assert_audit_owner(
    rows,
    *,
    clinic_id: int,
    user_id: int,
    action: AuditAction,
):
    assert rows
    assert any(
        row.clinic_id == clinic_id
        and row.user_id == user_id
        and row.action is action
        for row in rows
    )
    assert all(
        row.clinic_id == clinic_id
        for row in rows
    )


class DeterministicNotificationProvider:
    def __init__(
        self,
        calls,
        *,
        result=True,
        error=None,
    ):
        self.calls = calls
        self.result = result
        self.error = error

    def send(self, **kwargs):
        self.calls.append(kwargs)

        if self.error is not None:
            raise self.error

        return self.result


def test_background_notifications_e2e(
    client,
    db,
    clinic,
    make_clinic,
    make_staff,
    make_patient,
    make_appointment,
    e2e_login,
    monkeypatch,
):
    # ================================================================
    # PRIMARY CLINIC ACTORS
    # ================================================================

    admin_staff = make_staff(
        clinic=clinic,
        role=Role.ADMIN,
        user_overrides={
            "email": "e2e-g14-admin@test.com",
        },
    )

    recipient_staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
        user_overrides={
            "email": "e2e-g14-doctor@test.com",
        },
    )

    admin = admin_staff.user
    recipient = recipient_staff.user

    admin_login = e2e_login(
        "e2e-g14-admin@test.com",
    )

    recipient_login = e2e_login(
        "e2e-g14-doctor@test.com",
    )

    assert admin_login["user_id"] == admin.id
    assert admin_login["role"] == Role.ADMIN.value
    assert recipient_login["user_id"] == recipient.id
    assert recipient_login["role"] == Role.DOCTOR.value

    admin_headers = _headers(admin_login)
    recipient_headers = _headers(recipient_login)

    # ================================================================
    # CELERY EAGER EXECUTION
    #
    # This uses the real registered Celery task body while keeping
    # the E2E deterministic and isolated from an external worker.
    # Phase 7 separately verifies the real worker/broker runtime.
    # ================================================================

    old_eager = celery.conf.get(
        "task_always_eager",
        False,
    )
    old_propagates = celery.conf.get(
        "task_eager_propagates",
        False,
    )

    celery.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
    )

    try:
        # ============================================================
        # CREATE EXTERNAL NOTIFICATION THROUGH REAL HTTP ROUTE
        # ============================================================

        create_response = client.post(
            "/api/v1/notifications/",
            json={
                "user_id": recipient.id,
                "title": "Gate 14 appointment reminder",
                "message": (
                    "Your Gate 14 appointment reminder "
                    "was queued for delivery."
                ),
                "notification_type": (
                    NotificationType.APPOINTMENT.value
                ),
                "priority": (
                    NotificationPriority.HIGH.value
                ),
                "channel": (
                    NotificationChannel.EMAIL.value
                ),
                "reference_type": "Appointment",
                "reference_id": 1,
            },
            headers=admin_headers,
        )

        assert create_response.status_code == 201, (
            create_response.get_json()
        )

        create_body = create_response.get_json()

        assert create_body["success"] is True
        assert create_body["data"]["clinic_id"] == clinic.id
        assert create_body["data"]["user_id"] == recipient.id
        assert create_body["data"]["channel"] == (
            NotificationChannel.EMAIL.value
        )
        assert create_body["data"]["status"] == (
            NotificationStatus.PENDING.value
        )

        notification_id = create_body["data"]["id"]

        persisted_notification = db.session.get(
            Notification,
            notification_id,
        )

        assert persisted_notification is not None
        assert persisted_notification.clinic_id == clinic.id
        assert persisted_notification.user_id == recipient.id
        assert (
            persisted_notification.status
            is NotificationStatus.PENDING
        )

        # ============================================================
        # CREATE AUDIT MUST BE TENANT + ACTOR CORRECT
        # ============================================================

        notification_audits = _audit_rows(
            db,
            "Notification",
            notification_id,
        )

        _assert_audit_owner(
            notification_audits,
            clinic_id=clinic.id,
            user_id=admin.id,
            action=AuditAction.CREATE,
        )

        # ============================================================
        # FOREIGN CLINIC BACKGROUND TASK MUST NOT TOUCH RESOURCE
        # ============================================================

        second_clinic = make_clinic(
            name="Gate 14 Foreign Clinic",
        )

        foreign_admin_staff = make_staff(
            clinic=second_clinic,
            role=Role.ADMIN,
            user_overrides={
                "email": "e2e-g14-foreign-admin@test.com",
            },
        )

        foreign_admin_login = e2e_login(
            "e2e-g14-foreign-admin@test.com",
        )

        assert (
            foreign_admin_login["user_id"]
            == foreign_admin_staff.user.id
        )

        wrong_tenant_result = (
            notification_service
            .deliver_notification.delay(
                second_clinic.id,
                notification_id,
            )
            .get()
        )

        assert wrong_tenant_result is False

        persisted_notification = db.session.get(
            Notification,
            notification_id,
        )

        assert persisted_notification.status is (
            NotificationStatus.PENDING
        )
        assert persisted_notification.retry_count == 0

        # ============================================================
        # DETERMINISTIC PROVIDER
        # ============================================================

        successful_calls = []

        successful_provider = (
            DeterministicNotificationProvider(
                successful_calls,
            )
        )

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            lambda channel, *, clinic_id: (
                successful_provider
            ),
        )

        # ============================================================
        # QUEUE -> CELERY TASK -> PROVIDER -> DELIVERED
        # ============================================================

        queued = (
            notification_service
            .queue_notification_delivery(
                notification_id,
                clinic_id=clinic.id,
                user_id=recipient.id,
            )
        )

        assert queued.id == notification_id

        persisted_notification = db.session.get(
            Notification,
            notification_id,
        )

        assert persisted_notification is not None
        assert persisted_notification.status is (
            NotificationStatus.DELIVERED
        )
        assert persisted_notification.sent_at is not None
        assert persisted_notification.delivered_at is not None
        assert persisted_notification.failed_at is None
        assert persisted_notification.error_message is None
        assert persisted_notification.retry_count == 0

        assert len(successful_calls) == 1
        assert successful_calls[0]["notification"] is (
            persisted_notification
        )
        assert successful_calls[0]["idempotency_key"] == (
            f"clinic-notification-"
            f"{clinic.id}-{notification_id}"
        )
        assert successful_calls[0]["email"] == recipient.email

        # ============================================================
        # TERMINAL DELIVERY MUST NOT QUEUE AGAIN
        # ============================================================

        with pytest.raises(Exception):
            notification_service.queue_notification_delivery(
                notification_id,
                clinic_id=clinic.id,
                user_id=recipient.id,
            )

        # ============================================================
        # RECIPIENT CAN READ OWN NOTIFICATION
        # ============================================================

        get_response = client.get(
            f"/api/v1/notifications/{notification_id}",
            headers=recipient_headers,
        )

        assert get_response.status_code == 200

        get_body = get_response.get_json()

        assert get_body["success"] is True
        assert get_body["data"]["id"] == notification_id
        assert get_body["data"]["clinic_id"] == clinic.id
        assert get_body["data"]["user_id"] == recipient.id
        assert get_body["data"]["status"] == (
            NotificationStatus.DELIVERED.value
        )

        # ============================================================
        # RECIPIENT READ STATE
        # ============================================================

        read_response = client.post(
            f"/api/v1/notifications/{notification_id}/read",
            json={},
            headers=recipient_headers,
        )

        assert read_response.status_code == 200, (
            read_response.get_json()
        )

        read_body = read_response.get_json()

        assert read_body["success"] is True
        assert read_body["data"]["id"] == notification_id
        assert read_body["data"]["is_read"] is True
        assert read_body["data"]["status"] == (
            NotificationStatus.READ.value
        )
        assert read_body["data"]["read_at"] is not None

        persisted_notification = db.session.get(
            Notification,
            notification_id,
        )

        assert persisted_notification.status is (
            NotificationStatus.READ
        )
        assert persisted_notification.is_read is True

        # ============================================================
        # FAILURE -> FAILED -> RETRY -> DELIVERED
        # ============================================================

        failed_create_response = client.post(
            "/api/v1/notifications/",
            json={
                "user_id": recipient.id,
                "title": "Gate 14 retry notification",
                "message": (
                    "This delivery intentionally fails "
                    "once before retry."
                ),
                "notification_type": (
                    NotificationType.SYSTEM.value
                ),
                "priority": (
                    NotificationPriority.NORMAL.value
                ),
                "channel": (
                    NotificationChannel.EMAIL.value
                ),
            },
            headers=admin_headers,
        )

        assert failed_create_response.status_code == 201

        failed_notification_id = (
            failed_create_response.get_json()
            ["data"]["id"]
        )

        failed_calls = []

        failing_provider = (
            DeterministicNotificationProvider(
                failed_calls,
                error=RuntimeError(
                    "deterministic provider failure"
                ),
            )
        )

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            lambda channel, *, clinic_id: (
                failing_provider
            ),
        )

        with pytest.raises(RuntimeError):
            notification_service.queue_notification_delivery(
                failed_notification_id,
                clinic_id=clinic.id,
                user_id=recipient.id,
            )

        failed_notification = db.session.get(
            Notification,
            failed_notification_id,
        )

        assert failed_notification is not None
        assert failed_notification.status is (
            NotificationStatus.FAILED
        )
        assert failed_notification.retry_count == 1
        assert failed_notification.failed_at is not None
        assert failed_notification.error_message == (
            "deterministic provider failure"
        )

        retry_calls = []

        retry_provider = (
            DeterministicNotificationProvider(
                retry_calls,
            )
        )

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            lambda channel, *, clinic_id: (
                retry_provider
            ),
        )

        notification_service.queue_notification_delivery(
            failed_notification_id,
            clinic_id=clinic.id,
            user_id=recipient.id,
        )

        retried_notification = db.session.get(
            Notification,
            failed_notification_id,
        )

        assert retried_notification is not None
        assert retried_notification.status is (
            NotificationStatus.DELIVERED
        )
        assert retried_notification.retry_count == 1
        assert retried_notification.delivered_at is not None

        assert len(failed_calls) == 1
        assert len(retry_calls) == 1
        assert retry_calls[0]["idempotency_key"] == (
            f"clinic-notification-"
            f"{clinic.id}-{failed_notification_id}"
        )

        # ============================================================
        # CROSS-CLINIC HTTP READ + CREATE MUST FAIL
        # ============================================================

        foreign_headers = _headers(
            foreign_admin_login
        )

        foreign_get_response = client.get(
            f"/api/v1/notifications/{notification_id}",
            headers=foreign_headers,
        )

        assert foreign_get_response.status_code == 404

        notification_count_before = (
            db.session.execute(
                db.select(Notification)
                .where(
                    Notification.clinic_id == clinic.id,
                    Notification.id == notification_id,
                )
            )
            .scalars()
            .all()
        )

        denied_create_response = client.post(
            "/api/v1/notifications/",
            json={
                "user_id": recipient.id,
                "title": "Denied cross-clinic notification",
                "message": "Must not be created.",
                "notification_type": (
                    NotificationType.SYSTEM.value
                ),
                "priority": (
                    NotificationPriority.NORMAL.value
                ),
                "channel": (
                    NotificationChannel.IN_APP.value
                ),
            },
            headers=foreign_headers,
        )

        assert denied_create_response.status_code == 404

        notification_count_after = (
            db.session.execute(
                db.select(Notification)
                .where(
                    Notification.clinic_id == clinic.id,
                    Notification.id == notification_id,
                )
            )
            .scalars()
            .all()
        )

        assert len(notification_count_after) == (
            len(notification_count_before)
        )

        # ============================================================
        # APPOINTMENT BACKGROUND REMINDER
        # ============================================================

        patient = make_patient(
            clinic,
            first_name="Gate",
            last_name="Fourteen",
        )

        scheduled_start = (
            datetime.now(timezone.utc)
            + timedelta(
                days=1,
                minutes=30,
            )
        )

        scheduled_end = (
            scheduled_start
            + timedelta(minutes=30)
        )

        appointment = make_appointment(
            clinic=clinic,
            patient=patient,
            staff=recipient_staff,
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
        )

        assert appointment.reminder_sent is False

        appointment_service.check_upcoming_appointments.delay().get()

        persisted_appointment = db.session.get(
            Appointment,
            appointment.id,
        )

        assert persisted_appointment is not None
        assert persisted_appointment.clinic_id == clinic.id
        assert persisted_appointment.reminder_sent is True

        # ============================================================
        # WRONG-CLINIC APPOINTMENT TASK MUST NOT MUTATE STATE
        # ============================================================

        protected_appointment = make_appointment(
            clinic=clinic,
            patient=patient,
            staff=recipient_staff,
            scheduled_start=(
                datetime.now(timezone.utc)
                + timedelta(days=2)
            ),
            scheduled_end=(
                datetime.now(timezone.utc)
                + timedelta(days=2, minutes=30)
            ),
        )

        assert protected_appointment.reminder_sent is False

        result = appointment_service.send_appointment_reminder(
            second_clinic.id,
            protected_appointment.id,
        )

        assert result is None

        protected_appointment = db.session.get(
            Appointment,
            protected_appointment.id,
        )

        assert protected_appointment is not None
        assert protected_appointment.reminder_sent is False

        # ============================================================
        # CELERY / BEAT REGISTRATION
        # ============================================================

        assert (
            notification_service.deliver_notification.name
            == "deliver_notification"
        )

        beat_schedule = celery.conf.beat_schedule

        assert (
            beat_schedule[
                "check-upcoming-appointments-hourly"
            ]["task"]
            == "check_upcoming_appointments"
        )

        assert (
            beat_schedule[
                "mark-overdue-invoices-hourly"
            ]["task"]
            == "mark_overdue_invoices"
        )

        print(
            "PHASE8_E2E_GATE14_BACKGROUND_NOTIFICATIONS=PASS"
        )

    finally:
        celery.conf.update(
            task_always_eager=old_eager,
            task_eager_propagates=old_propagates,
        )
