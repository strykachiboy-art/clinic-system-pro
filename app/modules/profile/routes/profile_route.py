from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity
from pydantic import ValidationError as PydanticValidationError

from app.core.enums.role_enums import Role
from app.core.exceptions import ValidationError
from app.core.utils.decorators import role_required

from app.modules.profile.schemas.profile_schema import (
    ProfileUpdateSchema,
)
from app.modules.profile.services.profile_service import (
    get_profile,
    update_profile,
)


# ============================================================================
# BLUEPRINT
# ============================================================================


profile_bp = Blueprint(
    "profile",
    __name__,
    url_prefix="/api/profile",
)


# ============================================================================
# ROLE CONFIGURATION
# ============================================================================


PROFILE_ROLES = (
    Role.DOCTOR,
    Role.NURSE,
    Role.PATIENT,
    Role.PHARMACIST,
    Role.LAB_TECHNICIAN,
    Role.RECEPTIONIST,
    Role.ADMIN,
    Role.ACCOUNTANT,
    Role.PARAMEDIC,
    Role.OTHER,
    Role.DRIVER,
    Role.EMT,
    Role.AMBULANCE_DISPATCHER,
    Role.AMBULANCE_COORDINATOR,
)


# ============================================================================
# HELPERS
# ============================================================================


def _current_user_id() -> int:
    """
    Resolve the authenticated user's ID from the JWT identity.
    """

    identity = get_jwt_identity()

    if isinstance(identity, bool):
        raise ValidationError(
            "Invalid authentication identity"
        )

    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        raise ValidationError(
            "Invalid authentication identity"
        )

    if user_id <= 0:
        raise ValidationError(
            "Invalid authentication identity"
        )

    return user_id


def _payload() -> dict:
    """
    Return and validate the incoming JSON payload.
    """
    payload = request.get_json(silent=True)

    if payload is None:
        raise ValidationError(
            "Request body must contain valid JSON"
        )

    if not isinstance(payload, dict):
        raise ValidationError(
            "Request body must be a JSON object"
        )

    return payload


# ============================================================================
# GET MY PROFILE
# ============================================================================


@profile_bp.get("/me")
@role_required(*PROFILE_ROLES)
def get_my_profile():
    """
    Return the authenticated user's aggregated profile.
    """
    user_id = _current_user_id()

    profile = get_profile(
        user_id=user_id,
    )

    return jsonify(
        {
            "success": True,
            "data": profile.model_dump(
                mode="json"
            ),
        }
    ), 200


# ============================================================================
# UPDATE MY PROFILE
# ============================================================================


@profile_bp.patch("/me")
@role_required(*PROFILE_ROLES)
def update_my_profile():
    """
    Update the authenticated user's own profile.
    """
    user_id = _current_user_id()

    payload = _payload()

    try:
        data = ProfileUpdateSchema.model_validate(
            payload
        )
    except PydanticValidationError as exc:
        raise exc

    profile = update_profile(
        user_id=user_id,
        **data.model_dump(
            exclude_unset=True
        ),
    )

    return jsonify(
        {
            "success": True,
            "message": "Profile updated successfully",
            "data": profile.model_dump(
                mode="json"
            ),
        }
    ), 200