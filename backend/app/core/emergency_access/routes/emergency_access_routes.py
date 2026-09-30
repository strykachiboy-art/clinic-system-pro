from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.core.auth.user.models.user_model import User
from app.core.emergency_access.models.emergency_access_model import (
    EmergencyAccessGrant,
)
from app.core.emergency_access.schemas.emergency_access_schema import (
    EmergencyAccessDecisionSchema,
    EmergencyAccessRequestSchema,
    EmergencyAccessResponseSchema,
    EmergencyAccessRevokeSchema,
)
from app.core.emergency_access.services.emergency_access_service import (
    deny_emergency_access,
    grant_emergency_access,
    request_emergency_access,
    revoke_emergency_access,
)
from app.core.enums.emergency_access_enums import (
    EmergencyAccessStatus,
)
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import (
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import role_required
from app.extensions import db


emergency_access_bp = Blueprint(
    "emergency_access",
    __name__,
    url_prefix="/emergency-access",
)


EMERGENCY_REQUESTER_ROLES = (
    Role.DOCTOR,
    Role.NURSE,
    Role.PHARMACIST,
    Role.LAB_TECHNICIAN,
    Role.PARAMEDIC,
    Role.EMT,
)


EMERGENCY_REVIEWER_ROLES = (
    Role.DOCTOR,
    Role.NURSE,
    Role.PHARMACIST,
    Role.LAB_TECHNICIAN,
    Role.PARAMEDIC,
    Role.EMT,
    Role.ADMIN,
    Role.SUPER_ADMIN,
)


EMERGENCY_READ_ROLES = EMERGENCY_REVIEWER_ROLES


def _get_current_user() -> User:
    identity = get_jwt_identity()

    if (
        isinstance(identity, bool)
        or identity is None
    ):
        raise ValidationError(
            "Invalid authentication identity"
        )

    try:
        user_id = int(identity)
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValidationError(
            "Invalid authentication identity"
        ) from exc

    if user_id <= 0:
        raise ValidationError(
            "Invalid authentication identity"
        )

    user = db.session.get(
        User,
        user_id,
    )

    if user is None:
        raise ValidationError(
            "Authenticated user could not be resolved"
        )

    if not user.is_active:
        raise ValidationError(
            "User account is inactive"
        )

    role = user.role

    if role in EMERGENCY_REQUESTER_ROLES:
        staff = getattr(
            user,
            "staff",
            None,
        )

        if staff is None:
            raise ValidationError(
                "Authenticated user is not linked "
                "to a staff record"
            )

        if staff.status != StaffStatus.ACTIVE:
            raise ValidationError(
                "Staff record is not active"
            )

    return user


def _json_body() -> dict:
    payload = request.get_json(
        silent=True
    )

    if payload is None:
        return {}

    if not isinstance(payload, dict):
        raise ValidationError(
            "JSON body must be an object"
        )

    return payload


def _serialize(
    value: EmergencyAccessGrant,
) -> dict:
    return (
        EmergencyAccessResponseSchema
        .model_validate(
            value,
            from_attributes=True,
        )
        .model_dump(
            mode="json"
        )
    )


def _current_clinic_id(
    user: User,
) -> int | None:
    if user.role == Role.SUPER_ADMIN:
        return user.clinic_id

    staff = getattr(
        user,
        "staff",
        None,
    )

    if staff is not None:
        if (
            user.clinic_id is not None
            and user.clinic_id != staff.clinic_id
        ):
            raise ValidationError(
                "User clinic does not match staff clinic"
            )

        return staff.clinic_id

    return user.clinic_id


def _get_visible_grant(
    emergency_access_id: int,
    user: User,
) -> EmergencyAccessGrant:
    if (
        isinstance(emergency_access_id, bool)
        or not isinstance(
            emergency_access_id,
            int,
        )
        or emergency_access_id <= 0
    ):
        raise ValidationError(
            "Emergency access ID must be a positive integer"
        )

    grant = db.session.get(
        EmergencyAccessGrant,
        emergency_access_id,
    )

    if grant is None:
        raise NotFoundError(
            f"Emergency access request "
            f"{emergency_access_id} not found"
        )

    if user.role == Role.SUPER_ADMIN:
        return grant

    clinic_id = _current_clinic_id(
        user,
    )

    if clinic_id is None:
        raise NotFoundError(
            "Emergency access request not found"
        )

    if grant.clinic_id != clinic_id:
        raise NotFoundError(
            "Emergency access request not found"
        )

    return grant


@emergency_access_bp.post("/requests")
@role_required(
    *EMERGENCY_REQUESTER_ROLES,
)
def request_emergency_access_route():
    current_user = _get_current_user()

    payload = EmergencyAccessRequestSchema.model_validate(
        _json_body()
    )

    grant = request_emergency_access(
        actor_id=current_user.id,
        patient_id=payload.patient_id,
        reason=payload.reason,
        purpose=payload.purpose,
        scope=payload.scope,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(grant),
        }
    ), 201


@emergency_access_bp.get(
    "/requests/<int:emergency_access_id>"
)
@role_required(
    *EMERGENCY_READ_ROLES,
)
def get_emergency_access_route(
    emergency_access_id: int,
):
    current_user = _get_current_user()

    grant = _get_visible_grant(
        emergency_access_id,
        current_user,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(grant),
        }
    ), 200


@emergency_access_bp.post(
    "/requests/<int:emergency_access_id>/grant"
)
@role_required(
    *EMERGENCY_REVIEWER_ROLES,
)
def grant_emergency_access_route(
    emergency_access_id: int,
):
    current_user = _get_current_user()

    payload = EmergencyAccessDecisionSchema.model_validate(
        _json_body()
    )

    grant = grant_emergency_access(
        emergency_access_id=emergency_access_id,
        reviewer_id=current_user.id,
        duration_minutes=payload.duration_minutes,
        review_notes=payload.review_notes,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(grant),
        }
    ), 200


@emergency_access_bp.post(
    "/requests/<int:emergency_access_id>/deny"
)
@role_required(
    *EMERGENCY_REVIEWER_ROLES,
)
def deny_emergency_access_route(
    emergency_access_id: int,
):
    current_user = _get_current_user()

    payload = EmergencyAccessDecisionSchema.model_validate(
        _json_body()
    )

    grant = deny_emergency_access(
        emergency_access_id=emergency_access_id,
        reviewer_id=current_user.id,
        review_notes=payload.review_notes,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(grant),
        }
    ), 200


@emergency_access_bp.post(
    "/requests/<int:emergency_access_id>/revoke"
)
@role_required(
    *EMERGENCY_REVIEWER_ROLES,
)
def revoke_emergency_access_route(
    emergency_access_id: int,
):
    current_user = _get_current_user()

    payload = EmergencyAccessRevokeSchema.model_validate(
        _json_body()
    )

    grant = revoke_emergency_access(
        emergency_access_id=emergency_access_id,
        actor_id=current_user.id,
        reason=payload.reason,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(grant),
        }
    ), 200