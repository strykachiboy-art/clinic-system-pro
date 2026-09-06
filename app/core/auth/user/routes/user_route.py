from flask import Blueprint, jsonify, request
from pydantic import ValidationError as PydanticValidationError

from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_jwt_identity,
    jwt_required,
)

from app import db
from app.core.auth.user.models.user_model import User
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
from app.core.auth.user.services.token_service import (
    revoke_current_token,
    revoke_token,
)
from app.core.auth.user.services.user_service import (
    authenticate_user,
    register_user,
)
from app.core.enums.role_enums import Role
from app.core.exceptions import DomainError


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


@auth_bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    """
    Rotate the refresh token and issue a new access token.

    Flow:

        refresh_A
            ↓
        validate JWT
            ↓
        check blocklist
            ↓
        load user
            ↓
        verify active
            ↓
        revoke refresh_A
            ↓
        issue access_B
            ↓
        issue refresh_B
    """
    user_id = get_jwt_identity()

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return jsonify(
            {
                "success": False,
                "error": "Invalid authentication identity",
            }
        ), 401

    user = User.query.get(user_id)

    if user is None:
        return jsonify(
            {
                "success": False,
                "error": "User not found",
            }
        ), 401

    if not user.is_active:
        return jsonify(
            {
                "success": False,
                "error": "This account has been deactivated",
            }
        ), 401

    try:
        # Revoke the refresh token that was just used.
        revoke_current_token()

        access_token = create_access_token(
            identity=str(user.id),
            additional_claims={
                "role": user.role.value,
            },
        )

        refresh_token = create_refresh_token(
            identity=str(user.id),
        )

    except DomainError as exc:
        db.session.rollback()

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
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user_id": user.id,
                "role": user.role.value,
            },
        }
    ), 200


@auth_bp.post("/logout")
@jwt_required()
def logout():
    """
    Revoke both the current access token and the supplied
    refresh token.
    """
    payload = request.get_json(silent=True) or {}
    refresh_token = payload.get("refresh_token")

    if not refresh_token:
        return jsonify(
            {
                "success": False,
                "error": "Refresh token is required",
            }
        ), 400

    try:
        refresh_payload = decode_token(
            refresh_token,
            allow_expired=False,
        )

        if refresh_payload.get("type") != "refresh":
            return jsonify(
                {
                    "success": False,
                    "error": "Invalid refresh token",
                }
            ), 401

        current_user_id = get_jwt_identity()
        refresh_user_id = refresh_payload.get(
            "sub"
        )

        if str(current_user_id) != str(
            refresh_user_id
        ):
            return jsonify(
                {
                    "success": False,
                    "error": "Refresh token does not belong to the current user",
                }
            ), 401

        # Revoke the refresh token first.
        revoke_token(refresh_payload)

        # Revoke the access token used for this request.
        revoke_current_token()

    except DomainError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), exc.status_code

    except Exception:
        return jsonify(
            {
                "success": False,
                "error": "Invalid refresh token",
            }
        ), 401

    return jsonify(
        {
            "success": True,
            "message": "Successfully logged out",
        }
    ), 200