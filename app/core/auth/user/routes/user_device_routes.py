from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.extensions import db

from app.core.auth.user.models.user_model import User
from app.core.auth.user.schema.user_device_schema import (
    UserDeviceCreateSchema,
    UserDeviceResponseSchema,
    UserDeviceUpdateSchema,
)
from app.core.auth.user.services.user_device_service import (
    activate_device,
    deactivate_device,
    delete_device,
    get_device,
    list_user_devices,
    register_device,
    touch_device,
    update_device,
)
from app.core.enums.role_enums import Role
from app.core.exceptions import (
    DomainError,
    ValidationError,
)
from app.core.utils.decorators import role_required


user_device_bp = Blueprint(
    "user_device",
    __name__,
    url_prefix="/api/users/devices",
)


# ============================================================================
# ROLE AUTHORIZATION
# ============================================================================


DEVICE_MANAGEMENT_ROLES = (
    Role.DOCTOR,
    Role.NURSE,
    Role.PATIENT,
    Role.PHARMACIST,
    Role.LAB_TECHNICIAN,
    Role.RECEPTIONIST,
    Role.ADMIN,
    Role.ACCOUNTANT,
    Role.PARAMEDIC,
    Role.EMT,
    Role.DRIVER,
    Role.AMBULANCE_DISPATCHER,
    Role.AMBULANCE_COORDINATOR,
    Role.OTHER,
)


# ============================================================================
# HELPERS
# ============================================================================


def _json_body() -> dict:
    """
    Return a JSON object from the request body.
    """
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


def _payload(schema):
    """
    Validate a JSON request payload.

    Pydantic validation errors intentionally propagate to
    the application's global validation error handler.
    """
    return schema.model_validate(
        _json_body()
    )


def _get_current_user() -> User:
    """
    Return the authenticated active user.

    The user ID is always derived from the JWT.
    """
    identity = get_jwt_identity()

    try:
        user_id = int(identity)
    except (
        TypeError,
        ValueError,
    ):
        raise ValidationError(
            "Invalid authentication identity"
        )

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


def _serialize_device(device) -> dict:
    """
    Serialize a UserDevice through the response schema.
    """
    return (
        UserDeviceResponseSchema
        .model_validate(device)
        .model_dump(
            mode="json"
        )
    )


def _serialize_page(result: dict) -> dict:
    """
    Serialize a paginated UserDevice service result.
    """
    return {
        "items": [
            _serialize_device(device)
            for device in result["items"]
        ],
        "page": result["page"],
        "per_page": result["per_page"],
        "total": result["total"],
        "pages": result["pages"],
        "has_next": result["has_next"],
        "has_prev": result["has_prev"],
    }


def _parse_bool_query(
    name: str,
    default: bool = False,
) -> bool:
    """
    Parse a boolean query-string parameter.
    """
    value = request.args.get(
        name
    )

    if value is None:
        return default

    normalized = value.strip().lower()

    if normalized in {
        "true",
        "1",
        "yes",
    }:
        return True

    if normalized in {
        "false",
        "0",
        "no",
    }:
        return False

    raise ValidationError(
        f"{name} must be a boolean"
    )


def _parse_int_query(
    name: str,
    default: int,
) -> int:
    """
    Parse a positive integer query-string parameter.
    """
    value = request.args.get(
        name
    )

    if value is None:
        return default

    try:
        parsed = int(value)
    except (
        TypeError,
        ValueError,
    ):
        raise ValidationError(
            f"{name} must be an integer"
        )

    if parsed <= 0:
        raise ValidationError(
            f"{name} must be a positive integer"
        )

    return parsed


def _handle_domain_error(
    exc: DomainError,
):
    return jsonify(
        {
            "success": False,
            "error": str(exc),
        }
    ), exc.status_code


# ============================================================================
# REGISTER DEVICE
# ============================================================================


@user_device_bp.post("/")
@role_required(*DEVICE_MANAGEMENT_ROLES)
def register_device_route():
    """
    Register or re-register the authenticated user's device.
    """
    payload = _payload(
        UserDeviceCreateSchema
    )

    try:
        user = _get_current_user()

        device = register_device(
            user_id=user.id,
            **payload.model_dump(),
        )

        return jsonify(
            {
                "success": True,
                "data": _serialize_device(
                    device
                ),
            }
        ), 201

    except DomainError as exc:
        return _handle_domain_error(
            exc
        )


# ============================================================================
# LIST DEVICES
# ============================================================================


@user_device_bp.get("/")
@role_required(*DEVICE_MANAGEMENT_ROLES)
def list_devices_route():
    """
    List devices belonging only to the authenticated user.
    """
    try:
        user = _get_current_user()

        page = _parse_int_query(
            "page",
            1,
        )

        per_page = _parse_int_query(
            "per_page",
            20,
        )

        active_only = _parse_bool_query(
            "active_only",
            False,
        )

        platform = request.args.get(
            "platform"
        )

        result = list_user_devices(
            user_id=user.id,
            active_only=active_only,
            platform=platform,
            page=page,
            per_page=per_page,
        )

        return jsonify(
            {
                "success": True,
                "data": _serialize_page(
                    result
                ),
            }
        ), 200

    except DomainError as exc:
        return _handle_domain_error(
            exc
        )


# ============================================================================
# GET DEVICE
# ============================================================================


@user_device_bp.get(
    "/<int:device_id>"
)
@role_required(*DEVICE_MANAGEMENT_ROLES)
def get_device_route(
    device_id: int,
):
    """
    Get a single device belonging to the authenticated user.
    """
    try:
        user = _get_current_user()

        device = get_device(
            device_id=device_id,
            user_id=user.id,
        )

        return jsonify(
            {
                "success": True,
                "data": _serialize_device(
                    device
                ),
            }
        ), 200

    except DomainError as exc:
        return _handle_domain_error(
            exc
        )


# ============================================================================
# UPDATE DEVICE
# ============================================================================


@user_device_bp.patch(
    "/<int:device_id>"
)
@role_required(*DEVICE_MANAGEMENT_ROLES)
def update_device_route(
    device_id: int,
):
    """
    Update device metadata or active state.

    Device tokens are intentionally not accepted here.
    Token registration/rotation belongs to registration.
    """
    payload = _payload(
        UserDeviceUpdateSchema
    )

    try:
        user = _get_current_user()

        data = payload.model_dump(
            exclude_unset=True
        )

        is_active = data.pop(
            "is_active",
            None,
        )

        device = update_device(
            device_id=device_id,
            user_id=user.id,
            **data,
        )

        if is_active is True:
            device = activate_device(
                device_id=device_id,
                user_id=user.id,
            )

        elif is_active is False:
            device = deactivate_device(
                device_id=device_id,
                user_id=user.id,
            )

        return jsonify(
            {
                "success": True,
                "data": _serialize_device(
                    device
                ),
            }
        ), 200

    except DomainError as exc:
        return _handle_domain_error(
            exc
        )


# ============================================================================
# TOUCH / LAST SEEN
# ============================================================================


@user_device_bp.post(
    "/<int:device_id>/touch"
)
@role_required(*DEVICE_MANAGEMENT_ROLES)
def touch_device_route(
    device_id: int,
):
    """
    Update the authenticated user's device last-seen timestamp.
    """
    try:
        user = _get_current_user()

        device = touch_device(
            device_id=device_id,
            user_id=user.id,
        )

        return jsonify(
            {
                "success": True,
                "data": _serialize_device(
                    device
                ),
            }
        ), 200

    except DomainError as exc:
        return _handle_domain_error(
            exc
        )


# ============================================================================
# ACTIVATE
# ============================================================================


@user_device_bp.post(
    "/<int:device_id>/activate"
)
@role_required(*DEVICE_MANAGEMENT_ROLES)
def activate_device_route(
    device_id: int,
):
    """
    Activate the authenticated user's device.
    """
    try:
        user = _get_current_user()

        device = activate_device(
            device_id=device_id,
            user_id=user.id,
        )

        return jsonify(
            {
                "success": True,
                "data": _serialize_device(
                    device
                ),
            }
        ), 200

    except DomainError as exc:
        return _handle_domain_error(
            exc
        )


# ============================================================================
# DEACTIVATE
# ============================================================================


@user_device_bp.post(
    "/<int:device_id>/deactivate"
)
@role_required(*DEVICE_MANAGEMENT_ROLES)
def deactivate_device_route(
    device_id: int,
):
    """
    Deactivate the authenticated user's device.
    """
    try:
        user = _get_current_user()

        device = deactivate_device(
            device_id=device_id,
            user_id=user.id,
        )

        return jsonify(
            {
                "success": True,
                "data": _serialize_device(
                    device
                ),
            }
        ), 200

    except DomainError as exc:
        return _handle_domain_error(
            exc
        )


# ============================================================================
# DELETE
# ============================================================================


@user_device_bp.delete(
    "/<int:device_id>"
)
@role_required(*DEVICE_MANAGEMENT_ROLES)
def delete_device_route(
    device_id: int,
):
    """
    Permanently remove the authenticated user's device.
    """
    try:
        user = _get_current_user()

        delete_device(
            device_id=device_id,
            user_id=user.id,
        )

        return jsonify(
            {
                "success": True,
                "message": "Device deleted successfully",
            }
        ), 200

    except DomainError as exc:
        return _handle_domain_error(
            exc
        )