from __future__ import annotations

from typing import Optional

from app.core.audit.models.audit_model import AuditLog
from app.core.audit.services.audit_writer import write_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.exceptions import ValidationError


MAX_IP_ADDRESS_LENGTH = 45


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


def create_audit_log(
    *,
    action: AuditAction,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    description: Optional[str] = None,
    old_value=None,
    new_value=None,
    user_id: Optional[int] = None,
    clinic_id: Optional[int] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    action = _normalize_action(action)

    resolved_entity_type = _normalize_optional_string(
        entity_type,
        "Audit entity type",
        max_length=80,
    )

    if resolved_entity_type is None:
        raise ValidationError(
            "Audit entity type is required"
        )

    _validate_positive_id(
        entity_id,
        "Audit entity ID",
    )

    user_id = _normalize_optional_id(
        user_id,
        "User ID",
    )

    clinic_id = _normalize_optional_id(
        clinic_id,
        "Clinic ID",
    )

    description = _normalize_optional_string(
        description,
        "Audit description",
        max_length=255,
    )

    ip_address = _normalize_ip_address(
        ip_address,
    )

    return write_audit_log(
        action=action,
        entity_type=resolved_entity_type,
        entity_id=entity_id,
        description=description,
        old_value=old_value,
        new_value=new_value,
        user_id=user_id,
        clinic_id=clinic_id,
        ip_address=ip_address,
    )






