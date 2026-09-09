from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.extensions import db

from app.core.audit.models.audit_model import AuditLog
from app.core.enums.audit_enums import AuditAction
from app.core.exceptions import (
    NotFoundError,
    ValidationError,
)


DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100
MAX_IP_ADDRESS_LENGTH = 45


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


def _normalize_action(action) -> AuditAction:
    if isinstance(action, AuditAction):
        return action

    try:
        return AuditAction(action)
    except (TypeError, ValueError):
        raise ValidationError(
            "Invalid audit action"
        )


def _normalize_optional_string(
    value,
    field_name: str,
    max_length: int,
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

    if len(value) > max_length:
        raise ValidationError(
            f"{field_name} cannot exceed "
            f"{max_length} characters"
        )

    return value


def _normalize_optional_id(
    value,
    field_name: str,
):
    if value is None:
        return None

    _validate_positive_id(
        value,
        field_name,
    )

    return value


def _normalize_ip_address(
    value,
):
    """
    Normalize an optional client IP address.

    IP addresses may be absent for background jobs,
    scheduled tasks, system operations, or internal
    service calls.
    """
    return _normalize_optional_string(
        value,
        "IP address",
        MAX_IP_ADDRESS_LENGTH,
    )


def _validate_pagination(
    page: int,
    per_page: int,
):
    """
    Validate and normalize pagination parameters.
    """
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
            "Per page must be a positive integer"
        )

    if per_page > MAX_PER_PAGE:
        raise ValidationError(
            f"Per page cannot exceed {MAX_PER_PAGE}"
        )

    return page, per_page


def create_audit_log(
    *,
    action: AuditAction,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    description: Optional[str] = None,
    old_value=None,
    new_value=None,
    user_id: Optional[int] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    details=None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    """
    Create an audit record.

    Supports both the current entity_* API and the
    legacy resource_* aliases used by older services.

    The caller is responsible for committing the
    surrounding transaction.

    IP address is optional because audit records may
    originate from API requests, background jobs,
    scheduled tasks, or internal system operations.
    """

    action = _normalize_action(action)

    resolved_entity_type = (
        entity_type
        if entity_type is not None
        else resource_type
    )

    resolved_entity_id = (
        entity_id
        if entity_id is not None
        else resource_id
    )

    resolved_entity_type = _normalize_optional_string(
        resolved_entity_type,
        "Audit entity type",
        max_length=80,
    )

    if resolved_entity_type is None:
        raise ValidationError(
            "Audit entity type is required"
        )

    _validate_positive_id(
        resolved_entity_id,
        "Audit entity ID",
    )

    user_id = _normalize_optional_id(
        user_id,
        "User ID",
    )

    description = _normalize_optional_string(
        description,
        "Audit description",
        max_length=255,
    )

    ip_address = _normalize_ip_address(
        ip_address
    )

    log = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=resolved_entity_type,
        entity_id=resolved_entity_id,
        description=description,
        old_value=old_value,
        new_value=(
            new_value
            if new_value is not None
            else details
        ),
        ip_address=ip_address,
    )

    db.session.add(log)

    return log


def list_audit_logs(
    *,
    user_id: Optional[int] = None,
    action: Optional[AuditAction] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    page: int = DEFAULT_PAGE,
    per_page: int = DEFAULT_PER_PAGE,
):
    """
    Return paginated audit logs.

    All filters are optional.

    Results are ordered newest-first using both
    created_at and id for deterministic pagination.
    """

    if user_id is not None:
        _validate_positive_id(
            user_id,
            "User ID",
        )

    if entity_id is not None:
        _validate_positive_id(
            entity_id,
            "Entity ID",
        )

    page, per_page = _validate_pagination(
        page,
        per_page,
    )

    if action is not None:
        action = _normalize_action(action)

    entity_type = _normalize_optional_string(
        entity_type,
        "Entity type",
        max_length=80,
    )

    query = AuditLog.query

    if user_id is not None:
        query = query.filter(
            AuditLog.user_id == user_id
        )

    if action is not None:
        query = query.filter(
            AuditLog.action == action
        )

    if entity_type is not None:
        query = query.filter(
            AuditLog.entity_type == entity_type
        )

    if entity_id is not None:
        query = query.filter(
            AuditLog.entity_id == entity_id
        )

    return (
        query
        .order_by(
            AuditLog.created_at.desc(),
            AuditLog.id.desc(),
        )
        .paginate(
            page=page,
            per_page=per_page,
            error_out=False,
        )
    )


def get_audit_log_by_id(
    log_id: int,
) -> AuditLog:
    """
    Return one audit log by primary key.
    """
    _validate_positive_id(
        log_id,
        "Audit log ID",
    )

    log = db.session.get(
        AuditLog,
        log_id,
    )

    if log is None:
        raise NotFoundError(
            f"Audit log {log_id} not found"
        )

    return log