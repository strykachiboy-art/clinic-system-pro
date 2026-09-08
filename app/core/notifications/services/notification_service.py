from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db, celery

from app.core.audit.services.audit_service import (
    create_audit_log,
)
from app.core.enums.audit_enums import AuditAction
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
from app.core.utils.decorators import transactional

from app.core.auth.user.models.user_model import User
from app.core.notifications.models.notification_models import (
    Notification,
)
from app.modules.clinic.services.clinic_service import (
    get_clinic,
)


# ============================================================================
# UTILITIES
# ============================================================================


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _validate_positive_id(
    value,
    field_name,
):
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ValidationError(
            f"{field_name} must be a positive integer"
        )


def _normalize_required_string(
    value,
    field_name,
    max_length=None,
):
    if not isinstance(value, str):
        raise ValidationError(
            f"{field_name} must be a string"
        )

    value = value.strip()

    if not value:
        raise ValidationError(
            f"{field_name} is required"
        )

    if (
        max_length is not None
        and len(value) > max_length
    ):
        raise ValidationError(
            f"{field_name} cannot exceed "
            f"{max_length} characters"
        )

    return value


def _normalize_optional_string(
    value,
    field_name,
    max_length=None,
):
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValidationError(
            f"{field_name} must be a string"
        )

    value = value.strip()

    if not value:
        return None

    if (
        max_length is not None
        and len(value) > max_length
    ):
        raise ValidationError(
            f"{field_name} cannot exceed "
            f"{max_length} characters"
        )

    return value


def _normalize_enum(
    value,
    enum_class,
    field_name,
):
    if isinstance(value, enum_class):
        return value

    try:
        return enum_class(value)
    except (ValueError, TypeError):
        raise ValidationError(
            f"Invalid {field_name}"
        )


# ============================================================================
# USER / CLINIC HELPERS
# ============================================================================


def _get_user(
    user_id,
    *,
    clinic_id=None,
):
    _validate_positive_id(
        user_id,
        "User ID",
    )

    query = User.query.filter(
        User.id == user_id,
    )

    if clinic_id is not None:
        query = query.filter(
            User.clinic_id == clinic_id,
        )

    user = query.first()

    if user is None:
        raise NotFoundError(
            f"User {user_id} not found"
        )

    return user


def _validate_notification_target(
    clinic_id,
    user_id,
):
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    clinic = get_clinic(
        clinic_id,
    )

    user = _get_user(
        user_id,
        clinic_id=clinic_id,
    )

    if not user.is_active:
        raise ValidationError(
            f"User {user.id} is inactive"
        )

    return clinic, user


# ============================================================================
# NOTIFICATION HELPERS
# ============================================================================


def _get_notification(
    notification_id,
    *,
    clinic_id=None,
    lock=False,
):
    _validate_positive_id(
        notification_id,
        "Notification ID",
    )

    query = Notification.query.filter(
        Notification.id == notification_id,
    )

    if clinic_id is not None:
        query = query.filter(
            Notification.clinic_id == clinic_id,
        )

    if lock:
        query = query.with_for_update()

    notification = query.first()

    if notification is None:
        raise NotFoundError(
            f"Notification {notification_id} not found"
        )

    return notification


def _normalize_channel(channel):
    return _normalize_enum(
        channel,
        NotificationChannel,
        "notification channel",
    )


def _normalize_priority(priority):
    return _normalize_enum(
        priority,
        NotificationPriority,
        "notification priority",
    )


def _normalize_type(notification_type):
    return _normalize_enum(
        notification_type,
        NotificationType,
        "notification type",
    )


# ============================================================================
# PROVIDER BOUNDARY
# ============================================================================


def _deliver_with_provider(notification):
    """
    Provider integration boundary.

    This function intentionally contains no concrete provider
    implementation yet.

    EMAIL -> email provider
    SMS   -> SMS provider
    PUSH  -> push provider

    A real provider implementation should return True only
    when the provider accepts the notification successfully.

    Provider-specific message IDs or metadata can be added
    here later without changing the notification service API.
    """

    if notification.channel == NotificationChannel.EMAIL:
        # Email provider integration goes here.
        #
        # Example future behavior:
        # return email_provider.send(...)
        #
        # Keep this boundary isolated from routes and Celery.
        return True

    if notification.channel == NotificationChannel.SMS:
        # SMS provider integration goes here.
        return True

    if notification.channel == NotificationChannel.PUSH:
        # Push provider integration goes here.
        return True

    raise ValidationError(
        "Unsupported notification channel for delivery"
    )


# ============================================================================
# CREATE NOTIFICATION
# ============================================================================


@transactional
def create_notification(
    clinic_id,
    user_id,
    title,
    message,
    notification_type,
    priority=NotificationPriority.NORMAL,
    channel=NotificationChannel.IN_APP,
    reference_type=None,
    reference_id=None,
):
    """
    Create a notification for a clinic-owned user.

    Notification status is controlled by the service and
    delivery layer. Clients cannot manually create a
    SENT/DELIVERED/READ notification.
    """

    clinic, user = _validate_notification_target(
        clinic_id,
        user_id,
    )

    title = _normalize_required_string(
        title,
        "Notification title",
        max_length=255,
    )

    message = _normalize_required_string(
        message,
        "Notification message",
    )

    notification_type = _normalize_type(
        notification_type,
    )

    priority = _normalize_priority(
        priority,
    )

    channel = _normalize_channel(
        channel,
    )

    reference_type = _normalize_optional_string(
        reference_type,
        "Reference type",
        max_length=50,
    )

    if reference_id is not None:
        _validate_positive_id(
            reference_id,
            "Reference ID",
        )

    notification = Notification(
        clinic_id=clinic.id,
        user_id=user.id,
        title=title,
        message=message,
        notification_type=notification_type,
        priority=priority,
        channel=channel,
        status=NotificationStatus.PENDING,
        reference_type=reference_type,
        reference_id=reference_id,
        is_read=False,
        retry_count=0,
    )

    db.session.add(notification)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Notification",
        entity_id=notification.id,
        description=(
            f"Notification created for user "
            f"{user.id}"
        ),
        new_value={
            "clinic_id": clinic.id,
            "user_id": user.id,
            "notification_type": (
                notification_type.value
            ),
            "priority": priority.value,
            "channel": channel.value,
            "status": (
                notification.status.value
            ),
            "reference_type": reference_type,
            "reference_id": reference_id,
        },
    )

    return notification


# ============================================================================
# QUEUE NOTIFICATION DELIVERY
# ============================================================================


def queue_notification_delivery(
    notification_id,
):
    """
    Queue an external notification for asynchronous
    delivery.

    IN_APP notifications do not require Celery delivery.
    """

    notification = _get_notification(
        notification_id,
    )

    if notification.channel == NotificationChannel.IN_APP:
        return notification

    if notification.status not in (
        NotificationStatus.PENDING,
        NotificationStatus.FAILED,
    ):
        raise ConflictError(
            f"Notification {notification.id} "
            f"cannot be queued from status "
            f"'{notification.status.value}'"
        )

    deliver_notification.delay(
        notification.id,
    )

    return notification


# ============================================================================
# CELERY DELIVERY ENTRYPOINT
# ============================================================================


@celery.task(
    name="deliver_notification",
)
def deliver_notification(
    notification_id,
):
    """
    Background notification delivery entrypoint.

    Celery is responsible for asynchronous execution.

    Provider-specific delivery is isolated behind
    _deliver_with_provider().

    The task is intentionally not exposed directly through
    ordinary HTTP routes.
    """

    try:
        _validate_positive_id(
            notification_id,
            "Notification ID",
        )
    except ValidationError:
        return False

    notification = db.session.get(
        Notification,
        notification_id,
    )

    if notification is None:
        return False

    # Terminal states are idempotent.
    if notification.status in (
        NotificationStatus.DELIVERED,
        NotificationStatus.READ,
    ):
        return True

    # In-app notifications are persisted directly and do not
    # require an external provider.
    if notification.channel == NotificationChannel.IN_APP:
        return False

    try:
        # --------------------------------------------------------------------
        # Mark the delivery attempt as SENT.
        #
        # SENT means the application has begun an external
        # provider delivery attempt.
        # --------------------------------------------------------------------

        notification.status = NotificationStatus.SENT
        notification.sent_at = _utcnow()

        db.session.flush()

        # --------------------------------------------------------------------
        # Provider boundary.
        #
        # The provider implementation is responsible for
        # communicating with EMAIL/SMS/PUSH infrastructure.
        # --------------------------------------------------------------------

        provider_success = _deliver_with_provider(
            notification,
        )

        if not provider_success:
            raise RuntimeError(
                "Notification provider rejected delivery"
            )

        # --------------------------------------------------------------------
        # Provider accepted the notification.
        # --------------------------------------------------------------------

        notification.status = (
            NotificationStatus.DELIVERED
        )
        notification.delivered_at = _utcnow()
        notification.error_message = None

        db.session.commit()

        return True

    except Exception as exc:
        db.session.rollback()

        try:
            notification = db.session.get(
                Notification,
                notification_id,
            )

            if notification is not None:
                notification.status = (
                    NotificationStatus.FAILED
                )
                notification.failed_at = _utcnow()
                notification.retry_count = (
                    notification.retry_count + 1
                )
                notification.error_message = str(
                    exc
                )[:2000]

                db.session.commit()

        except Exception:
            db.session.rollback()

        raise


# ============================================================================
# USER NOTIFICATIONS
# ============================================================================


def get_user_notifications(
    user_id,
    clinic_id,
    *,
    unread_only=False,
):
    """
    Return notifications belonging to a clinic-owned user.
    """

    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    _get_user(
        user_id,
        clinic_id=clinic_id,
    )

    query = Notification.query.filter(
        Notification.clinic_id == clinic_id,
        Notification.user_id == user_id,
    )

    if unread_only:
        query = query.filter(
            Notification.is_read.is_(False),
        )

    return (
        query
        .order_by(
            Notification.created_at.desc(),
            Notification.id.desc(),
        )
        .all()
    )


# ============================================================================
# GET SINGLE NOTIFICATION
# ============================================================================


def get_notification_for_user(
    notification_id,
    user_id,
    clinic_id,
):
    _validate_positive_id(
        user_id,
        "User ID",
    )

    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    notification = _get_notification(
        notification_id,
        clinic_id=clinic_id,
    )

    if notification.user_id != user_id:
        raise NotFoundError(
            f"Notification {notification_id} not found"
        )

    return notification


# ============================================================================
# MARK NOTIFICATION READ
# ============================================================================


@transactional
def mark_notification_read(
    notification_id,
    user_id,
    clinic_id,
):
    """
    Mark one notification as read.
    """

    _validate_positive_id(
        user_id,
        "User ID",
    )

    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    notification = _get_notification(
        notification_id,
        clinic_id=clinic_id,
        lock=True,
    )

    if notification.user_id != user_id:
        raise NotFoundError(
            f"Notification {notification_id} not found"
        )

    if notification.is_read:
        return notification

    old_status = notification.status
    old_is_read = notification.is_read

    notification.is_read = True
    notification.read_at = _utcnow()
    notification.status = NotificationStatus.READ

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Notification",
        entity_id=notification.id,
        description="Notification marked as read",
        old_value={
            "status": old_status.value,
            "is_read": old_is_read,
        },
        new_value={
            "status": NotificationStatus.READ.value,
            "is_read": True,
            "read_at": notification.read_at.isoformat(),
        },
    )

    return notification


# ============================================================================
# MARK ALL NOTIFICATIONS READ
# ============================================================================


@transactional
def mark_all_notifications_read(
    user_id,
    clinic_id,
):
    """
    Mark every unread notification for a user as read.
    """

    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    _get_user(
        user_id,
        clinic_id=clinic_id,
    )

    notifications = (
        Notification.query
        .filter(
            Notification.clinic_id == clinic_id,
            Notification.user_id == user_id,
            Notification.is_read.is_(False),
        )
        .with_for_update()
        .all()
    )

    if not notifications:
        return 0

    read_at = _utcnow()

    for notification in notifications:
        notification.is_read = True
        notification.read_at = read_at
        notification.status = NotificationStatus.READ

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Notification",
        entity_id=user_id,
        description=(
            f"{len(notifications)} notifications "
            f"marked as read for user {user_id}"
        ),
        new_value={
            "user_id": user_id,
            "count": len(notifications),
        },
    )

    return len(notifications)


# ============================================================================
# DELIVERY STATUS
# ============================================================================


@transactional
def update_notification_delivery_status(
    notification_id,
    status,
    *,
    error_message=None,
):
    """
    Internal operation used by delivery workers.

    This should not be exposed directly to ordinary
    authenticated HTTP clients.
    """

    notification = _get_notification(
        notification_id,
        lock=True,
    )

    status = _normalize_enum(
        status,
        NotificationStatus,
        "notification status",
    )

    error_message = _normalize_optional_string(
        error_message,
        "Error message",
        max_length=2000,
    )

    old_status = notification.status

    notification.status = status

    now = _utcnow()

    if status == NotificationStatus.SENT:
        notification.sent_at = (
            notification.sent_at or now
        )

    elif status == NotificationStatus.DELIVERED:
        notification.sent_at = (
            notification.sent_at or now
        )
        notification.delivered_at = now
        notification.error_message = None

    elif status == NotificationStatus.READ:
        notification.is_read = True
        notification.read_at = (
            notification.read_at or now
        )
        notification.delivered_at = (
            notification.delivered_at or now
        )
        notification.error_message = None

    elif status == NotificationStatus.FAILED:
        notification.failed_at = now
        notification.retry_count += 1
        notification.error_message = error_message

    elif status == NotificationStatus.PENDING:
        notification.error_message = None

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Notification",
        entity_id=notification.id,
        description=(
            "Notification delivery status changed"
        ),
        old_value={
            "status": old_status.value,
        },
        new_value={
            "status": notification.status.value,
            "error_message": notification.error_message,
            "retry_count": notification.retry_count,
        },
    )

    return notification


# ============================================================================
# RETRY FAILED NOTIFICATION
# ============================================================================


@transactional
def retry_notification(
    notification_id,
):
    """
    Reset a failed notification to pending.

    The caller may queue delivery after the transaction
    has successfully committed.
    """

    notification = _get_notification(
        notification_id,
        lock=True,
    )

    if notification.status != NotificationStatus.FAILED:
        raise ConflictError(
            "Only failed notifications can be retried"
        )

    if notification.channel == NotificationChannel.IN_APP:
        raise ConflictError(
            "In-app notifications do not require delivery retry"
        )

    old_status = notification.status

    notification.status = NotificationStatus.PENDING
    notification.failed_at = None
    notification.error_message = None

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Notification",
        entity_id=notification.id,
        description=(
            "Failed notification reset for retry"
        ),
        old_value={
            "status": old_status.value,
        },
        new_value={
            "status": notification.status.value,
            "retry_count": notification.retry_count,
        },
    )

    db.session.flush()

    return notification