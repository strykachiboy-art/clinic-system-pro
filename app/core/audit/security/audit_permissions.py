from __future__ import annotations

from typing import Optional

from app.core.enums.role_enums import Role


AUDIT_READ_ROLES = frozenset(
    {
        Role.ADMIN,
        Role.SUPER_ADMIN,
    }
)


def _normalize_role(
    role,
) -> Optional[Role]:
    if role is None:
        return None

    if isinstance(role, Role):
        return role

    try:
        return Role(role)
    except (TypeError, ValueError):
        return None


def can_read_audit_logs(
    *,
    actor_role,
    actor_clinic_id: Optional[int],
    target_clinic_id: Optional[int],
) -> bool:

    role = _normalize_role(actor_role)

    if role not in AUDIT_READ_ROLES:
        return False

    if role is Role.SUPER_ADMIN:
        return True

    if role is Role.ADMIN:
        if (
            actor_clinic_id is None
            or target_clinic_id is None
        ):
            return False

        return actor_clinic_id == target_clinic_id

    return False


def can_access_audit_scope(
    *,
    actor_role,
    actor_clinic_id: Optional[int],
    requested_clinic_id: Optional[int],
) -> bool:

    role = _normalize_role(actor_role)

    if role is Role.SUPER_ADMIN:
        return True

    if role is not Role.ADMIN:
        return False

    if actor_clinic_id is None:
        return False

    if requested_clinic_id is None:
        return True

    return requested_clinic_id == actor_clinic_id