from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity
from pydantic import ValidationError as PydanticValidationError

from app.core.auth.user.models.user_model import User
from app.core.enums.role_enums import Role
from app.core.exceptions import DomainError, ValidationError
from app.core.utils.decorators import role_required
from app.extensions import db

from app.modules.settings.schemas.clinic_settings import (
    ClinicSettingsCreateSchema,
    ClinicSettingsResponseSchema,
    ClinicSettingsUpdateSchema,
)
from app.modules.settings.schemas.integration_config import (
    IntegrationConfigCreateSchema,
    IntegrationConfigListQuerySchema,
    IntegrationConfigResponseSchema,
    IntegrationConfigUpdateSchema,
)
from app.modules.settings.services.clinic_settings_service import (
    create_clinic_settings,
    disable_clinic_settings,
    enable_clinic_settings,
    ensure_clinic_settings,
    get_clinic_settings,
    update_clinic_settings,
)
from app.modules.settings.services.integration_config_service import (
    create_integration_config,
    delete_integration_config,
    disable_integration_config,
    enable_integration_config,
    get_integration_config,
    get_integration_config_by_id,
    list_integration_configs,
    rotate_integration_credentials,
    update_integration_config,
)


settings_bp = Blueprint(
    "settings",
    __name__,
    url_prefix="/api/settings",
)


SETTINGS_VIEW_ROLES = (
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
    Role.RECEPTIONIST,
    Role.ACCOUNTANT,
    Role.PHARMACIST,
    Role.LAB_TECHNICIAN,
)

SETTINGS_WRITE_ROLES = (
    Role.ADMIN,
)


def _get_current_user() -> User:
    identity = get_jwt_identity()

    try:
        user_id = int(identity)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Invalid authentication identity"
        ) from exc

    if user_id <= 0:
        raise ValidationError(
            "Invalid authentication identity"
        )

    user = db.session.get(User, user_id)

    if user is None:
        raise ValidationError(
            "Authenticated user could not be resolved"
        )

    if not user.is_active:
        raise ValidationError(
            "User account is inactive"
        )

    return user


def _get_current_clinic_id(
    user: User | None = None,
) -> int:
    user = user or _get_current_user()

    clinic_id = getattr(
        user,
        "clinic_id",
        None,
    )

    if clinic_id is None:
        raise DomainError(
            "Authenticated user is not assigned to a clinic"
        )

    if isinstance(clinic_id, bool):
        raise DomainError(
            "Authenticated user has an invalid clinic assignment"
        )

    try:
        clinic_id = int(clinic_id)
    except (TypeError, ValueError) as exc:
        raise DomainError(
            "Authenticated user has an invalid clinic assignment"
        ) from exc

    if clinic_id <= 0:
        raise DomainError(
            "Authenticated user has an invalid clinic assignment"
        )

    return clinic_id


def _handle_route_error(exc: Exception):
    if isinstance(exc, DomainError):
        return (
            jsonify(
                {
                    "success": False,
                    "error": str(exc),
                }
            ),
            exc.status_code,
        )

    return (
        jsonify(
            {
                "success": False,
                "error": "An unexpected error occurred",
            }
        ),
        400,
    )


def _validation_error_response(
    exc: PydanticValidationError,
):
    details = []

    for error in exc.errors():
        item = dict(error)
        ctx = item.get("ctx")

        if isinstance(ctx, dict) and "error" in ctx:
            ctx = dict(ctx)
            ctx["error"] = str(ctx["error"])
            item["ctx"] = ctx

        details.append(item)

    return (
        jsonify(
            {
                "success": False,
                "error": "Validation failed",
                "details": details,
            }
        ),
        422,
    )


def _serialize_settings(
    settings,
) -> dict:
    return ClinicSettingsResponseSchema.model_validate(
        settings
    ).model_dump(
        mode="json",
    )


def _serialize_integration(
    integration,
) -> dict:
    return IntegrationConfigResponseSchema.model_validate(
        integration
    ).model_dump(
        mode="json",
    )


@settings_bp.get("/clinic")
@role_required(*SETTINGS_VIEW_ROLES)
def get_settings():
    try:
        user = _get_current_user()
        clinic_id = _get_current_clinic_id(user)

        settings = get_clinic_settings(
            clinic_id=clinic_id,
        )

        return (
            jsonify(
                {
                    "success": True,
                    "data": _serialize_settings(settings),
                }
            ),
            200,
        )

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except Exception as exc:
        return _handle_route_error(exc)


@settings_bp.post("/clinic")
@role_required(*SETTINGS_WRITE_ROLES)
def create_settings():
    try:
        user = _get_current_user()
        clinic_id = _get_current_clinic_id(user)

        payload = ClinicSettingsCreateSchema.model_validate(
            request.get_json(silent=True) or {}
        )

        settings = create_clinic_settings(
            clinic_id=clinic_id,
            payload=payload,
        )

        return (
            jsonify(
                {
                    "success": True,
                    "message": "Clinic settings created successfully",
                    "data": _serialize_settings(settings),
                }
            ),
            201,
        )

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except Exception as exc:
        return _handle_route_error(exc)


@settings_bp.patch("/clinic")
@role_required(*SETTINGS_WRITE_ROLES)
def update_settings():
    try:
        user = _get_current_user()
        clinic_id = _get_current_clinic_id(user)

        payload = ClinicSettingsUpdateSchema.model_validate(
            request.get_json(silent=True) or {}
        )

        expected_version = request.args.get(
            "expected_version",
            type=int,
        )

        settings = update_clinic_settings(
            clinic_id=clinic_id,
            payload=payload,
            expected_version=expected_version,
        )

        return (
            jsonify(
                {
                    "success": True,
                    "message": "Clinic settings updated successfully",
                    "data": _serialize_settings(settings),
                }
            ),
            200,
        )

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except Exception as exc:
        return _handle_route_error(exc)


@settings_bp.post("/clinic/enable")
@role_required(*SETTINGS_WRITE_ROLES)
def enable_settings():
    try:
        user = _get_current_user()
        clinic_id = _get_current_clinic_id(user)

        settings = enable_clinic_settings(
            clinic_id=clinic_id,
        )

        return (
            jsonify(
                {
                    "success": True,
                    "message": "Clinic settings enabled successfully",
                    "data": _serialize_settings(settings),
                }
            ),
            200,
        )

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except Exception as exc:
        return _handle_route_error(exc)


@settings_bp.post("/clinic/disable")
@role_required(*SETTINGS_WRITE_ROLES)
def disable_settings():
    try:
        user = _get_current_user()
        clinic_id = _get_current_clinic_id(user)

        settings = disable_clinic_settings(
            clinic_id=clinic_id,
        )

        return (
            jsonify(
                {
                    "success": True,
                    "message": "Clinic settings disabled successfully",
                    "data": _serialize_settings(settings),
                }
            ),
            200,
        )

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except Exception as exc:
        return _handle_route_error(exc)


@settings_bp.post("/clinic/initialize")
@role_required(*SETTINGS_WRITE_ROLES)
def initialize_settings():
    try:
        user = _get_current_user()
        clinic_id = _get_current_clinic_id(user)

        settings = ensure_clinic_settings(
            clinic_id=clinic_id,
        )

        return (
            jsonify(
                {
                    "success": True,
                    "message": "Clinic settings initialized successfully",
                    "data": _serialize_settings(settings),
                }
            ),
            200,
        )

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except Exception as exc:
        return _handle_route_error(exc)


@settings_bp.get("/integrations")
@role_required(*SETTINGS_VIEW_ROLES)
def list_integrations():
    try:
        user = _get_current_user()
        clinic_id = _get_current_clinic_id(user)

        query_payload = IntegrationConfigListQuerySchema.model_validate(
            {
                "include_disabled": request.args.get(
                    "include_disabled",
                    "false",
                ),
                "provider": request.args.get(
                    "provider",
                    default=None,
                    type=str,
                ),
                "page": request.args.get(
                    "page",
                    default=1,
                    type=int,
                ),
                "per_page": request.args.get(
                    "per_page",
                    default=20,
                    type=int,
                ),
            }
        )

        integrations, total = list_integration_configs(
            clinic_id=clinic_id,
            include_disabled=query_payload.include_disabled,
            provider=query_payload.provider,
            page=query_payload.page,
            per_page=query_payload.per_page,
        )

        pages = (
            (total + query_payload.per_page - 1)
            // query_payload.per_page
            if total
            else 0
        )

        return (
            jsonify(
                {
                    "success": True,
                    "data": [
                        _serialize_integration(
                            integration
                        )
                        for integration in integrations
                    ],
                    "pagination": {
                        "page": query_payload.page,
                        "per_page": query_payload.per_page,
                        "total": total,
                        "pages": pages,
                        "has_next": (
                            query_payload.page < pages
                        ),
                        "has_previous": (
                            query_payload.page > 1
                            and pages > 0
                        ),
                    },
                }
            ),
            200,
        )

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except Exception as exc:
        return _handle_route_error(exc)


@settings_bp.post("/integrations")
@role_required(*SETTINGS_WRITE_ROLES)
def create_integration():
    try:
        user = _get_current_user()
        clinic_id = _get_current_clinic_id(user)

        payload = IntegrationConfigCreateSchema.model_validate(
            request.get_json(silent=True) or {}
        )

        integration = create_integration_config(
            clinic_id=clinic_id,
            payload=payload,
        )

        return (
            jsonify(
                {
                    "success": True,
                    "message": (
                        "Integration configuration "
                        "created successfully"
                    ),
                    "data": _serialize_integration(
                        integration
                    ),
                }
            ),
            201,
        )

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except Exception as exc:
        return _handle_route_error(exc)


@settings_bp.get("/integrations/<string:provider>")
@role_required(*SETTINGS_VIEW_ROLES)
def get_integration(provider: str):
    try:
        user = _get_current_user()
        clinic_id = _get_current_clinic_id(user)

        integration = get_integration_config(
            clinic_id=clinic_id,
            provider=provider,
        )

        return (
            jsonify(
                {
                    "success": True,
                    "data": _serialize_integration(
                        integration
                    ),
                }
            ),
            200,
        )

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except Exception as exc:
        return _handle_route_error(exc)


@settings_bp.get("/integrations/id/<int:integration_id>")
@role_required(*SETTINGS_VIEW_ROLES)
def get_integration_by_id(integration_id: int):
    try:
        user = _get_current_user()
        clinic_id = _get_current_clinic_id(user)

        integration = get_integration_config_by_id(
            clinic_id=clinic_id,
            integration_id=integration_id,
        )

        return (
            jsonify(
                {
                    "success": True,
                    "data": _serialize_integration(
                        integration
                    ),
                }
            ),
            200,
        )

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except Exception as exc:
        return _handle_route_error(exc)


@settings_bp.patch("/integrations/<string:provider>")
@role_required(*SETTINGS_WRITE_ROLES)
def update_integration(provider: str):
    try:
        user = _get_current_user()
        clinic_id = _get_current_clinic_id(user)

        payload = IntegrationConfigUpdateSchema.model_validate(
            request.get_json(silent=True) or {}
        )

        integration = update_integration_config(
            clinic_id=clinic_id,
            provider=provider,
            payload=payload,
        )

        return (
            jsonify(
                {
                    "success": True,
                    "message": (
                        "Integration configuration "
                        "updated successfully"
                    ),
                    "data": _serialize_integration(
                        integration
                    ),
                }
            ),
            200,
        )

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except Exception as exc:
        return _handle_route_error(exc)


@settings_bp.post(
    "/integrations/<string:provider>/enable"
)
@role_required(*SETTINGS_WRITE_ROLES)
def enable_integration(provider: str):
    try:
        user = _get_current_user()
        clinic_id = _get_current_clinic_id(user)

        integration = enable_integration_config(
            clinic_id=clinic_id,
            provider=provider,
        )

        return (
            jsonify(
                {
                    "success": True,
                    "message": (
                        "Integration configuration "
                        "enabled successfully"
                    ),
                    "data": _serialize_integration(
                        integration
                    ),
                }
            ),
            200,
        )

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except Exception as exc:
        return _handle_route_error(exc)


@settings_bp.post(
    "/integrations/<string:provider>/disable"
)
@role_required(*SETTINGS_WRITE_ROLES)
def disable_integration(provider: str):
    try:
        user = _get_current_user()
        clinic_id = _get_current_clinic_id(user)

        integration = disable_integration_config(
            clinic_id=clinic_id,
            provider=provider,
        )

        return (
            jsonify(
                {
                    "success": True,
                    "message": (
                        "Integration configuration "
                        "disabled successfully"
                    ),
                    "data": _serialize_integration(
                        integration
                    ),
                }
            ),
            200,
        )

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except Exception as exc:
        return _handle_route_error(exc)


@settings_bp.post(
    "/integrations/<string:provider>/rotate"
)
@role_required(*SETTINGS_WRITE_ROLES)
def rotate_integration(provider: str):
    try:
        user = _get_current_user()
        clinic_id = _get_current_clinic_id(user)

        body = request.get_json(silent=True) or {}

        if not isinstance(body, dict):
            raise ValidationError(
                "Request body must be an object"
            )

        credentials = body.get("credentials")

        if credentials is None:
            raise ValidationError(
                "Credentials are required"
            )

        payload = IntegrationConfigUpdateSchema.model_validate(
            {
                "credentials": credentials,
            }
        )

        if payload.credentials is None:
            raise ValidationError(
                "Credentials are required"
            )

        integration = rotate_integration_credentials(
            clinic_id=clinic_id,
            provider=provider,
            credentials=payload.credentials,
        )

        return (
            jsonify(
                {
                    "success": True,
                    "message": (
                        "Integration credentials "
                        "rotated successfully"
                    ),
                    "data": _serialize_integration(
                        integration
                    ),
                }
            ),
            200,
        )

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except Exception as exc:
        return _handle_route_error(exc)


@settings_bp.delete(
    "/integrations/<string:provider>"
)
@role_required(*SETTINGS_WRITE_ROLES)
def delete_integration(provider: str):
    try:
        user = _get_current_user()
        clinic_id = _get_current_clinic_id(user)

        delete_integration_config(
            clinic_id=clinic_id,
            provider=provider,
        )

        return (
            jsonify(
                {
                    "success": True,
                    "message": (
                        "Integration configuration "
                        "deleted successfully"
                    ),
                }
            ),
            200,
        )

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except Exception as exc:
        return _handle_route_error(exc)