from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from app.core.audit.services.audit_service import create_audit_log
from app.core.auth.user.models.user_model import User
from app.core.enums.audit_enums import AuditAction
from app.core.enums.clinic_enums import ClinicStatus
from app.core.enums.role_enums import Role
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import transactional
from app.extensions import db
from app.modules.access_control.schemas.access_control_schema import (
    AccessControlClinicTransferResponseSchema,
    AccessControlRoleChangeResponseSchema,
    AccessControlStatusChangeResponseSchema,
    AccessControlUserListQuerySchema,
    AccessControlUserResponseSchema,
)
from app.modules.clinic.models.clinic_model import Clinic


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


def _normalize_reason(
    reason: str | None,
) -> str | None:
    if reason is None:
        return None

    if not isinstance(reason, str):
        raise ValidationError(
            "Reason must be a string"
        )

    normalized = reason.strip()

    return normalized or None


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


def _validate_actor(
    actor_id: int,
) -> User:
    actor = _get_user(actor_id)

    if not actor.is_active:
        raise ValidationError(
            "Authenticated administrator is inactive"
        )

    if actor.role is not Role.SUPER_ADMIN:
        raise ValidationError(
            "Only a super administrator can access access-control administration"
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
    if actor.role is not Role.SUPER_ADMIN:
        raise ConflictError(
            "Only a super administrator can change user roles"
        )

    if actor.id == target.id:
        raise ConflictError(
            "Super administrators cannot change their own role"
        )

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
    if actor.role is not Role.SUPER_ADMIN:
        raise ConflictError(
            "Only a super administrator can change user status"
        )

    if actor.id == target.id:
        raise ConflictError(
            "Super administrators cannot change their own account status"
        )

    if target.role is Role.SUPER_ADMIN:
        raise ConflictError(
            "A super administrator cannot modify another super administrator"
        )


def _validate_clinic_transfer_permissions(
    actor: User,
    target: User,
) -> None:
    if actor.role is not Role.SUPER_ADMIN:
        raise ConflictError(
            "Only a super administrator can transfer users between clinics"
        )

    if actor.id == target.id:
        raise ConflictError(
            "Super administrators cannot transfer their own account"
        )

    if target.role is Role.SUPER_ADMIN:
        raise ConflictError(
            "A super administrator cannot transfer another super administrator"
        )

    if target.patient is not None:
        raise ConflictError(
            "Patient accounts cannot be transferred through access control"
        )


def _get_active_clinic(
    clinic_id: int,
) -> Clinic:
    _validate_positive_id(
        clinic_id,
        "Destination clinic ID",
    )

    clinic = db.session.get(
        Clinic,
        clinic_id,
    )

    if clinic is None:
        raise NotFoundError(
            f"Clinic {clinic_id} not found"
        )

    if clinic.status is not ClinicStatus.ACTIVE:
        raise ValidationError(
            "Destination clinic is not active"
        )

    return clinic


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

    if actor.role is not Role.SUPER_ADMIN:
        raise ValidationError(
            "Only a super administrator can list access-control users"
        )

    filters = []

    if query.role is not None:
        filters.append(
            User.role == query.role
        )

    if query.is_active is not None:
        filters.append(
            User.is_active == query.is_active
        )

    count_statement = select(
        func.count(User.id)
    )

    user_statement = select(User)

    if filters:
        count_statement = count_statement.where(
            *filters
        )
        user_statement = user_statement.where(
            *filters
        )

    total = db.session.execute(
        count_statement
    ).scalar_one()

    offset = (
        (query.page - 1)
        * query.per_page
    )

    users = list(
        db.session.execute(
            user_statement
            .order_by(
                User.id.asc()
            )
            .offset(offset)
            .limit(query.per_page)
        ).scalars()
    )

    serialized_users = [
        _serialize_user(user)
        for user in users
    ]

    return serialized_users, total


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

    normalized_reason = _normalize_reason(
        reason
    )

    previous_token_version = target.token_version

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
            "token_version": previous_token_version,
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

    normalized_reason = _normalize_reason(
        reason
    )

    previous_token_version = target.token_version

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
            "token_version": previous_token_version,
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


@transactional
def transfer_user_clinic(
    *,
    actor_id: int,
    user_id: int,
    destination_clinic_id: int,
    reason: str | None = None,
) -> AccessControlClinicTransferResponseSchema:
    actor = _validate_actor(actor_id)
    target = _get_user(user_id)

    _validate_clinic_transfer_permissions(
        actor,
        target,
    )

    destination_clinic = _get_active_clinic(
        destination_clinic_id,
    )

    previous_clinic_id = target.clinic_id

    if previous_clinic_id == destination_clinic.id:
        raise ConflictError(
            "User already belongs to the destination clinic"
        )

    normalized_reason = _normalize_reason(
        reason
    )

    previous_token_version = target.token_version
    previous_staff_clinic_id = (
        target.staff.clinic_id
        if target.staff is not None
        else None
    )

    target.clinic_id = destination_clinic.id

    if target.staff is not None:
        target.staff.clinic_id = destination_clinic.id

    target.token_version += 1

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="User",
        entity_id=target.id,
        description=(
            f"User clinic transferred from "
            f"'{previous_clinic_id}' to "
            f"'{destination_clinic.id}'"
            + (
                f": {normalized_reason}"
                if normalized_reason
                else ""
            )
        ),
        old_value={
            "clinic_id": previous_clinic_id,
            "staff_clinic_id": previous_staff_clinic_id,
            "token_version": previous_token_version,
        },
        new_value={
            "clinic_id": target.clinic_id,
            "staff_clinic_id": (
                target.staff.clinic_id
                if target.staff is not None
                else None
            ),
            "token_version": target.token_version,
            "reason": normalized_reason,
        },
        user_id=actor.id,
    )

    return AccessControlClinicTransferResponseSchema(
        user=_serialize_user(target),
        previous_clinic_id=previous_clinic_id,
        new_clinic_id=destination_clinic.id,
        reason=normalized_reason,
    )