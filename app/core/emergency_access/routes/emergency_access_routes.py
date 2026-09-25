from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity

from app.core.auth.user.models.user_model import User
from app.core.emergency_access.schemas.emergency_access_schema import (
    EmergencyAccessDecisionSchema,
    EmergencyAccessRequestSchema,
    EmergencyAccessRevokeSchema,
)
from app.core.exceptions import ValidationError
from app.extensions import db


emergency_access_bp = Blueprint(
    "emergency_access",
    __name__,
    url_prefix="/emergency-access",
)


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


@emergency_access_bp.post("/requests")
def request_emergency_access_route():
    raise NotImplementedError


@emergency_access_bp.get("/requests/<int:emergency_access_id>")
def get_emergency_access_route(
    emergency_access_id: int,
):
    raise NotImplementedError


@emergency_access_bp.post(
    "/requests/<int:emergency_access_id>/grant"
)
def grant_emergency_access_route(
    emergency_access_id: int,
):
    raise NotImplementedError


@emergency_access_bp.post(
    "/requests/<int:emergency_access_id>/deny"
)
def deny_emergency_access_route(
    emergency_access_id: int,
):
    raise NotImplementedError


@emergency_access_bp.post(
    "/requests/<int:emergency_access_id>/revoke"
)
def revoke_emergency_access_route(
    emergency_access_id: int,
):
    raise NotImplementedError