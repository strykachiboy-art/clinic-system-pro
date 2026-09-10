from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.core.audit.services.audit_service import (
    create_audit_log,
)
from app.core.auth.user.models.user_device_model import UserDevice
from app.core.auth.user.models.user_model import User
from app.core.enums.audit_enums import AuditAction
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.extensions import db
from app.core.utils.decorators import transactional


DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100

ALLOWED_DEVICE_PLATFORMS = {
    "android",
    "ios",
    "web",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _validate_positive_id(
    value,
    field_name: str,
) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ValidationError(
            f"{field_name} must be a positive integer"
        )


def _validate_pagination(
    page: int,
    per_page: int,
) -> tuple[int, int]:
    if (
        isinstance(page, bool)
        or not isinstance(page, int)
        or page <= 0
    ):
        raise ValidationError(
            "Page must be a positive integer"
        )

    if (
        isinstance(per_page, bool)
        or not isinstance(per_page, int)
        or per_page <= 0
    ):
        raise ValidationError(
            "Per-page must be a positive integer"
        )

    if per_page > MAX_PER_PAGE:
        raise ValidationError(
            f"Per-page cannot exceed {MAX_PER_PAGE}"
        )

    return page, per_page


def _normalize_platform(
    platform: str,
) -> str:
    if not isinstance(platform, str):
        raise ValidationError(
            "Platform must be a string"
        )

    platform = platform.strip().lower()

    if platform not in ALLOWED_DEVICE_PLATFORMS:
        raise ValidationError(
            "Unsupported device platform"
        )

    return platform


def _normalize_device_name(
    device_name: str | None,
) -> str | None:
    if device_name is None:
        return None

    if not isinstance(device_name, str):
        raise ValidationError(
            "Device name must be a string"
        )

    device_name = device_name.strip()

    return device_name or None


def _normalize_device_token(
    device_token: str,
) -> str:
    if not isinstance(device_token, str):
        raise ValidationError(
            "Device token must be a string"
        )

    device_token = device_token.strip()

    if not device_token:
        raise ValidationError(
            "Device token is required"
        )

    if len(device_token) > 500:
        raise ValidationError(
            "Device token cannot exceed 500 characters"
        )

    return device_token


def _get_user(
    user_id: int,
) -> User:
    _validate_positive_id(
        user_id,
        "User ID",
    )

    user = db.session.get(
        User,
        user_id,
    )

    if user is None:
        raise NotFoundError(
            f"User {user_id} not found"
        )

    return user


def _validate_user_for_device(
    user_id: int,
) -> User:
    user = _get_user(user_id)

    if not user.is_active:
        raise ValidationError(
            f"User {user.id} is inactive"
        )

    return user


def _get_device(
    device_id: int,
    *,
    user_id: int | None = None,
) -> UserDevice:
    _validate_positive_id(
        device_id,
        "Device ID",
    )

    query = UserDevice.query.filter(
        UserDevice.id == device_id,
    )

    if user_id is not None:
        _validate_positive_id(
            user_id,
            "User ID",
        )

        query = query.filter(
            UserDevice.user_id == user_id,
        )

    device = query.first()

    if device is None:
        raise NotFoundError(
            f"User device {device_id} not found"
        )

    return device


def _get_device_by_token(
    device_token: str,
) -> UserDevice | None:
    device_token = _normalize_device_token(
        device_token,
    )

    return UserDevice.query.filter(
        UserDevice.device_token == device_token,
    ).first()


# =============================================================================
# REGISTER DEVICE
# =============================================================================


@transactional
def register_device(
    user_id: int,
    *,
    device_token: str,
    platform: str,
    device_name: str | None = None,
) -> UserDevice:
    """
    Register or re-register a user's push device.

    A device token is globally unique. If an existing token is
    found, ownership is reconciled safely rather than creating
    a duplicate record.
    """

    user = _validate_user_for_device(
        user_id,
    )

    device_token = _normalize_device_token(
        device_token,
    )

    platform = _normalize_platform(
        platform,
    )

    device_name = _normalize_device_name(
        device_name,
    )

    existing = _get_device_by_token(
        device_token,
    )

    if existing is not None:
        changed = False

        if existing.user_id != user.id:
            existing.user_id = user.id
            changed = True

        if existing.platform != platform:
            existing.platform = platform
            changed = True

        if existing.device_name != device_name:
            existing.device_name = device_name
            changed = True

        if not existing.is_active:
            existing.is_active = True
            changed = True

        existing.last_seen_at = _utcnow()

        if changed:
            create_audit_log(
                action=AuditAction.UPDATE,
                entity_type="UserDevice",
                entity_id=existing.id,
                description=(
                    f"Device {existing.id} "
                    f"re-registered for user {user.id}"
                ),
                new_value={
                    "user_id": user.id,
                    "platform": platform,
                    "device_name": device_name,
                    "is_active": True,
                },
            )

        return existing

    device = UserDevice(
        user_id=user.id,
        device_token=device_token,
        device_name=device_name,
        platform=platform,
        is_active=True,
        last_seen_at=_utcnow(),
    )

    db.session.add(device)

    try:
        db.session.flush()
    except IntegrityError as exc:
        db.session.rollback()

        existing = _get_device_by_token(
            device_token,
        )

        if existing is None:
            raise ConflictError(
                "Unable to register device"
            ) from exc

        if existing.user_id != user.id:
            raise ConflictError(
                "Device token is already registered"
            ) from exc

        existing.platform = platform
        existing.device_name = device_name
        existing.is_active = True
        existing.last_seen_at = _utcnow()

        return existing

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="UserDevice",
        entity_id=device.id,
        description=(
            f"Device registered for user {user.id}"
        ),
        new_value={
            "user_id": user.id,
            "platform": platform,
            "device_name": device_name,
            "is_active": True,
        },
    )

    return device


# =============================================================================
# GET DEVICE
# =============================================================================


def get_device(
    device_id: int,
    *,
    user_id: int,
) -> UserDevice:
    """
    Return a device owned by the specified user.
    """

    return _get_device(
        device_id,
        user_id=user_id,
    )


# =============================================================================
# LIST USER DEVICES
# =============================================================================


def list_user_devices(
    user_id: int,
    *,
    active_only: bool = False,
    platform: str | None = None,
    page: int = DEFAULT_PAGE,
    per_page: int = DEFAULT_PER_PAGE,
) -> dict:
    """
    Return a paginated list of devices owned by a user.

    Results are deterministic: newest activity first,
    then device ID descending.
    """

    _validate_user_for_device(
        user_id,
    )

    page, per_page = _validate_pagination(
        page,
        per_page,
    )

    if platform is not None:
        platform = _normalize_platform(
            platform,
        )

    query = UserDevice.query.filter(
        UserDevice.user_id == user_id,
    )

    if active_only:
        query = query.filter(
            UserDevice.is_active.is_(True),
        )

    if platform is not None:
        query = query.filter(
            UserDevice.platform == platform,
        )

    query = query.order_by(
        UserDevice.last_seen_at.desc(),
        UserDevice.id.desc(),
    )

    pagination = query.paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )

    return {
        "items": pagination.items,
        "page": pagination.page,
        "per_page": pagination.per_page,
        "total": pagination.total,
        "pages": pagination.pages,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev,
    }


# =============================================================================
# UPDATE DEVICE
# =============================================================================


@transactional
def update_device(
    device_id: int,
    user_id: int,
    *,
    device_name: str | None = None,
    platform: str | None = None,
) -> UserDevice:
    """
    Update mutable device metadata.

    Device tokens are intentionally not changed through this
    method. Token rotation should go through registration so
    uniqueness is handled consistently.
    """

    device = _get_device(
        device_id,
        user_id=user_id,
    )

    changed_fields = {}

    if device_name is not None:
        normalized_name = _normalize_device_name(
            device_name,
        )

        if device.device_name != normalized_name:
            device.device_name = normalized_name
            changed_fields["device_name"] = (
                normalized_name
            )

    if platform is not None:
        normalized_platform = _normalize_platform(
            platform,
        )

        if device.platform != normalized_platform:
            device.platform = normalized_platform
            changed_fields["platform"] = (
                normalized_platform
            )

    if changed_fields:
        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="UserDevice",
            entity_id=device.id,
            description=(
                f"Device {device.id} updated"
            ),
            new_value=changed_fields,
        )

    return device


# =============================================================================
# LAST SEEN
# =============================================================================


@transactional
def touch_device(
    device_id: int,
    user_id: int,
) -> UserDevice:
    """
    Update the last-seen timestamp for a user's device.
    """

    device = _get_device(
        device_id,
        user_id=user_id,
    )

    device.last_seen_at = _utcnow()

    return device


# =============================================================================
# ACTIVATE / DEACTIVATE
# =============================================================================


@transactional
def activate_device(
    device_id: int,
    user_id: int,
) -> UserDevice:
    """
    Activate a user's device.

    Activation is idempotent.
    """

    device = _get_device(
        device_id,
        user_id=user_id,
    )

    if device.is_active:
        return device

    device.is_active = True
    device.last_seen_at = _utcnow()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="UserDevice",
        entity_id=device.id,
        description=(
            f"Device {device.id} activated"
        ),
        old_value={
            "is_active": False,
        },
        new_value={
            "is_active": True,
        },
    )

    return device


@transactional
def deactivate_device(
    device_id: int,
    user_id: int,
) -> UserDevice:
    """
    Deactivate a user's device.

    Deactivation is idempotent.
    """

    device = _get_device(
        device_id,
        user_id=user_id,
    )

    if not device.is_active:
        return device

    device.is_active = False

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="UserDevice",
        entity_id=device.id,
        description=(
            f"Device {device.id} deactivated"
        ),
        old_value={
            "is_active": True,
        },
        new_value={
            "is_active": False,
        },
    )

    return device


# =============================================================================
# DELETE DEVICE
# =============================================================================


@transactional
def delete_device(
    device_id: int,
    user_id: int,
) -> None:
    """
    Permanently remove a user's device registration.
    """

    device = _get_device(
        device_id,
        user_id=user_id,
    )

    device_id = device.id
    owner_id = device.user_id

    db.session.delete(device)

    create_audit_log(
        action=AuditAction.DELETE,
        entity_type="UserDevice",
        entity_id=device_id,
        description=(
            f"Device {device_id} removed "
            f"from user {owner_id}"
        ),
    )