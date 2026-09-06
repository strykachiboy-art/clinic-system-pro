from flask import Blueprint, jsonify, request
from pydantic import ValidationError as PydanticValidationError

from app.core.auth.user.schema.user_schema import (
    GoogleAuthCallbackSchema,
    UserLoginSchema,
    UserRegisterSchema,
)
from app.core.auth.user.services.google_auth_service import (
    authenticate_google_code,
    get_google_authorization_url,
    validate_google_oauth_state,
)
from app.core.auth.user.services.user_service import (
    authenticate_user,
    register_user,
)
from app.core.enums.role_enums import Role
from app.core.exceptions import (
    ConflictError,
    DomainError,
    ValidationError,
)


auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/api/auth",
)


@auth_bp.post("/register")
def register():
    """
    Public patient registration.

    Role is intentionally NOT accepted from the client.
    Every account created through this endpoint is a PATIENT.
    """
    payload = request.get_json(silent=True) or {}

    try:
        data = UserRegisterSchema.model_validate(
            payload
        )
    except PydanticValidationError as exc:
        return jsonify(
            {
                "success": False,
                "error": "Validation failed",
                "details": exc.errors(),
            }
        ), 400

    try:
        user = register_user(
            email=str(data.email),
            password=data.password,
            role=Role.PATIENT,
            clinic_id=data.clinic_id,
        )
    except DomainError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), exc.status_code

    return jsonify(
        {
            "success": True,
            "data": {
                "id": user.id,
                "email": user.email,
                "role": user.role.value,
                "clinic_id": user.clinic_id,
                "is_active": user.is_active,
                "created_at": (
                    user.created_at.isoformat()
                    if user.created_at
                    else None
                ),
                "last_login_at": None,
            },
        }
    ), 201


@auth_bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}

    try:
        data = UserLoginSchema.model_validate(
            payload
        )
    except PydanticValidationError as exc:
        return jsonify(
            {
                "success": False,
                "error": "Validation failed",
                "details": exc.errors(),
            }
        ), 400

    try:
        result = authenticate_user(
            email=str(data.email),
            password=data.password,
        )
    except DomainError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), exc.status_code

    return jsonify(
        {
            "success": True,
            "data": result,
        }
    ), 200


@auth_bp.get("/google")
def google_login():
    """
    Start Google OAuth authentication.

    Generates a short-lived OAuth state, stores it in Redis,
    and returns the Google authorization URL.
    """
    try:
        authorization_url, state = (
            get_google_authorization_url()
        )
    except DomainError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), exc.status_code

    return jsonify(
        {
            "success": True,
            "data": {
                "authorization_url": authorization_url,
                "state": state,
            },
        }
    ), 200


@auth_bp.get("/google/callback")
def google_callback():
    """
    Complete Google OAuth authentication.

    Google redirects here with:

        ?code=...
        ?state=...

    The state is validated and consumed before the
    authorization code is exchanged.
    """
    google_error = request.args.get("error")

    if google_error:
        return jsonify(
            {
                "success": False,
                "error": google_error,
                "error_description": request.args.get(
                    "error_description"
                ),
            }
        ), 400

    payload = {
        "code": request.args.get("code"),
        "state": request.args.get("state"),
    }

    try:
        data = GoogleAuthCallbackSchema.model_validate(
            payload
        )
    except PydanticValidationError as exc:
        return jsonify(
            {
                "success": False,
                "error": "Validation failed",
                "details": exc.errors(),
            }
        ), 400

    try:
        validate_google_oauth_state(
            data.state
        )

        result = authenticate_google_code(
            code=data.code,
        )

    except DomainError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), exc.status_code

    return jsonify(
        {
            "success": True,
            "data": result,
        }
    ), 200