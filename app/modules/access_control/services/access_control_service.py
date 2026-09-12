from __future__ import annotations

from typing import Any

from app.core.audit.services.audit_service import create_audit_log
from app.core.auth.user.models.user_model import User
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import transactional
from app.extensions import db
from app.modules.access_control.schemas.access_control_schema import (
    AccessControlRoleChangeResponseSchema,
    AccessControlStatusChangeResponseSchema,
    AccessControlUserListQuerySchema,
    AccessControlUserResponseSchema,
)


def _validate_positive_id(
    value: Any,
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


def _get_user(user_id: int) -> User:
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


def _validate_actor(actor_id: int) -> User:
    actor = _get_user(actor_id)

    if not actor.is_active:
        raise ValidationError(
            "Authenticated administrator is inactive"
        )

    if actor.role not in {
        Role.ADMIN,
        Role.SUPER_ADMIN,
    }:
        raise ValidationError(
            "Authenticated user is not authorized"
        )

    return actor


def _validate_same_clinic(
    actor: User,
    target: User,
) -> None:
    if actor.role is Role.SUPER_ADMIN:
        return

    if actor.clinic_id is None:
        raise ValidationError(
            "Administrator must belong to a clinic"
        )

    if target.clinic_id is None:
        raise ValidationError(
            "Target user must belong to a clinic"
        )

    if actor.clinic_id != target.clinic_id:
        raise ValidationError(
            "Administrator and target user must belong to the same clinic"
        )


def _serialize_user(
    user: User,
) -> AccessControlUserResponseSchema:
    return AccessControlUserResponseSchema.model_validate(
        user,
        from_attributes=True,
    )


def _validate_role_change_permissions(
    actor: User,
    target: User,
    new_role: Role,
) -> None:
    if actor.id == target.id:
        raise ConflictError(
            "Users cannot change their own role"
        )

    if actor.role is Role.ADMIN:
        if target.role in {
            Role.ADMIN,
            Role.SUPER_ADMIN,
        }:
            raise ConflictError(
                "Administrator cannot modify another administrator"
            )

        if new_role in {
            Role.ADMIN,
            Role.SUPER_ADMIN,
        }:
            raise ConflictError(
                "Administrator cannot assign administrator privileges"
            )

    elif actor.role is Role.SUPER_ADMIN:
        if target.role is Role.SUPER_ADMIN:
            raise ConflictError(
                "A super administrator cannot modify another super administrator"
            )

        if new_role is Role.SUPER_ADMIN:
            raise ConflictError(
                "A super administrator cannot assign super administrator privileges"
            )


def _validate_status_change_permissions(
    actor: User,
    target: User,
) -> None:
    if actor.id == target.id:
        raise ConflictError(
            "Users cannot change their own account status"
        )

    if actor.role is Role.ADMIN and target.role in {
        Role.ADMIN,
        Role.SUPER_ADMIN,
    }:
        raise ConflictError(
            "Administrator cannot modify another administrator"
        )

    if (
        actor.role is Role.SUPER_ADMIN
        and target.role is Role.SUPER_ADMIN
    ):
        raise ConflictError(
            "A super administrator cannot modify another super administrator"
        )


def get_access_control_user(
    *,
    actor_id: int,
    user_id: int,
) -> AccessControlUserResponseSchema:
    actor = _validate_actor(actor_id)
    target = _get_user(user_id)

    _validate_same_clinic(
        actor,
        target,
    )

    return _serialize_user(target)


def list_access_control_users(
    *,
    actor_id: int,
    query: AccessControlUserListQuerySchema,
) -> tuple[list[AccessControlUserResponseSchema], int]:
    actor = _validate_actor(actor_id)

    if actor.role is Role.SUPER_ADMIN:
        base_query = User.query
    else:
        if actor.clinic_id is None:
            raise ValidationError(
                "Administrator must belong to a clinic"
            )

        base_query = User.query.filter(
            User.clinic_id == actor.clinic_id
        )

    if query.role is not None:
        base_query = base_query.filter(
            User.role == query.role
        )

    if query.is_active is not None:
        base_query = base_query.filter(
            User.is_active == query.is_active
        )

    pagination = (
        base_query
        .order_by(User.id.asc())
        .paginate(
            page=query.page,
            per_page=query.per_page,
            error_out=False,
        )
    )

    users = [
        _serialize_user(user)
        for user in pagination.items
    ]

    return users, pagination.total


@transactional
def change_user_role(
    *,
    actor_id: int,
    user_id: int,
    new_role: Role,
    reason: str | None = None,
) -> AccessControlRoleChangeResponseSchema:
    actor = _validate_actor(actor_id)
    target = _get_user(user_id)

    if not isinstance(new_role, Role):
        raise ValidationError(
            "Invalid user role"
        )

    _validate_same_clinic(
        actor,
        target,
    )

    _validate_role_change_permissions(
        actor,
        target,
        new_role,
    )

    previous_role = target.role

    if previous_role is new_role:
        raise ConflictError(
            f"User already has role '{new_role.value}'"
        )

    normalized_reason = (
        reason.strip()
        if reason is not None
        else None
    )

    target.role = new_role
    target.token_version += 1

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="User",
        entity_id=target.id,
        description=(
            f"User role changed from "
            f"'{previous_role.value}' to "
            f"'{new_role.value}'"
            + (
                f": {normalized_reason}"
                if normalized_reason
                else ""
            )
        ),
        old_value={
            "role": previous_role.value,
            "token_version": target.token_version - 1,
        },
        new_value={
            "role": new_role.value,
            "token_version": target.token_version,
            "reason": normalized_reason,
        },
        user_id=actor.id,
    )

    return AccessControlRoleChangeResponseSchema(
        user=_serialize_user(target),
        previous_role=previous_role,
        new_role=new_role,
        reason=normalized_reason,
    )


@transactional
def change_user_status(
    *,
    actor_id: int,
    user_id: int,
    is_active: bool,
    reason: str | None = None,
) -> AccessControlStatusChangeResponseSchema:
    actor = _validate_actor(actor_id)
    target = _get_user(user_id)

    if not isinstance(is_active, bool):
        raise ValidationError(
            "is_active must be a boolean"
        )

    _validate_same_clinic(
        actor,
        target,
    )

    _validate_status_change_permissions(
        actor,
        target,
    )

    previous_status = target.is_active

    if previous_status is is_active:
        raise ConflictError(
            "User already has the requested account status"
        )

    normalized_reason = (
        reason.strip()
        if reason is not None
        else None
    )

    target.is_active = is_active
    target.token_version += 1

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="User",
        entity_id=target.id,
        description=(
            "User account activated"
            if is_active
            else "User account deactivated"
        )
        + (
            f": {normalized_reason}"
            if normalized_reason
            else ""
        ),
        old_value={
            "is_active": previous_status,
            "token_version": target.token_version - 1,
        },
        new_value={
            "is_active": is_active,
            "token_version": target.token_version,
            "reason": normalized_reason,
        },
        user_id=actor.id,
    )

    return AccessControlStatusChangeResponseSchema(
        user=_serialize_user(target),
        previous_status=previous_status,
        new_status=is_active,
        reason=normalized_reason,
    )