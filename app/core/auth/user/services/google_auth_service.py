import secrets
from datetime import timedelta
from urllib.parse import urlencode

import requests
from flask import current_app
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
)

from app.core.audit.services.audit_service import (
    create_audit_log,
)
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role
from app.core.exceptions import (
    ConflictError,
    ValidationError,
)
from app.core.auth.user.models.user_model import User
from app.core.auth.user.models.user_auth_identity_model import (
    UserAuthIdentity,
)
from app.core.auth.user.schema.user_schema import (
    GoogleUserInfoSchema,
)
from app.extensions import db, redis_client


GOOGLE_AUTHORIZATION_URL = (
    "https://accounts.google.com/o/oauth2/v2/auth"
)

GOOGLE_TOKEN_URL = (
    "https://oauth2.googleapis.com/token"
)

GOOGLE_USERINFO_URL = (
    "https://openidconnect.googleapis.com/v1/userinfo"
)

GOOGLE_PROVIDER = "google"

GOOGLE_OAUTH_STATE_PREFIX = (
    "oauth:google:state:"
)

GOOGLE_OAUTH_STATE_TTL = 600


def _google_state_key(state: str) -> str:
    return (
        f"{GOOGLE_OAUTH_STATE_PREFIX}{state}"
    )


def create_google_oauth_state() -> str:
    """
    Generate and persist a short-lived Google OAuth state.

    The state is single-use and expires after 10 minutes.
    """
    if redis_client is None:
        raise ValidationError(
            "Redis is not available for OAuth state management"
        )

    state = secrets.token_urlsafe(32)

    redis_client.setex(
        _google_state_key(state),
        GOOGLE_OAUTH_STATE_TTL,
        "1",
    )

    return state


def validate_google_oauth_state(
    state: str,
) -> None:
    """
    Validate and consume a Google OAuth state.

    State is deleted immediately after successful validation
    so it cannot be reused.
    """
    if not state:
        raise ValidationError(
            "OAuth state is required"
        )

    if redis_client is None:
        raise ValidationError(
            "Redis is not available for OAuth state validation"
        )

    key = _google_state_key(state)

    stored_state = redis_client.get(key)

    if stored_state is None:
        raise ValidationError(
            "Invalid or expired OAuth state"
        )

    redis_client.delete(key)


def get_google_authorization_url() -> tuple[str, str]:
    """
    Generate the Google authorization URL and persist
    the OAuth state in Redis.
    """
    client_id = current_app.config.get(
        "GOOGLE_CLIENT_ID"
    )

    redirect_uri = current_app.config.get(
        "GOOGLE_REDIRECT_URI"
    )

    if not client_id:
        raise ValidationError(
            "Google OAuth is not configured: "
            "GOOGLE_CLIENT_ID is missing"
        )

    if not redirect_uri:
        raise ValidationError(
            "Google OAuth is not configured: "
            "GOOGLE_REDIRECT_URI is missing"
        )

    state = create_google_oauth_state()

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
        "state": state,
    }

    authorization_url = (
        f"{GOOGLE_AUTHORIZATION_URL}?"
        f"{urlencode(params)}"
    )

    return authorization_url, state


def exchange_google_code(
    code: str,
) -> dict:
    """
    Exchange Google's authorization code for tokens.
    """
    if not code:
        raise ValidationError(
            "Google authorization code is required"
        )

    client_id = current_app.config.get(
        "GOOGLE_CLIENT_ID"
    )

    client_secret = current_app.config.get(
        "GOOGLE_CLIENT_SECRET"
    )

    redirect_uri = current_app.config.get(
        "GOOGLE_REDIRECT_URI"
    )

    if not client_id or not client_secret:
        raise ValidationError(
            "Google OAuth is not configured"
        )

    if not redirect_uri:
        raise ValidationError(
            "Google OAuth redirect URI is not configured"
        )

    payload = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }

    try:
        response = requests.post(
            GOOGLE_TOKEN_URL,
            data=payload,
            timeout=10,
        )
    except requests.RequestException as exc:
        raise ValidationError(
            "Unable to communicate with Google"
        ) from exc

    if not response.ok:
        try:
            error_data = response.json()
        except ValueError:
            error_data = {}

        error_description = error_data.get(
            "error_description"
        )

        raise ValidationError(
            error_description
            or "Google authorization failed"
        )

    try:
        token_data = response.json()
    except ValueError as exc:
        raise ValidationError(
            "Invalid response received from Google"
        ) from exc

    google_access_token = token_data.get(
        "access_token"
    )

    if not google_access_token:
        raise ValidationError(
            "Google did not return an access token"
        )

    return token_data


def get_google_user_info(
    google_access_token: str,
) -> GoogleUserInfoSchema:
    """
    Retrieve and validate the Google user's profile.
    """
    if not google_access_token:
        raise ValidationError(
            "Google access token is required"
        )

    headers = {
        "Authorization": (
            f"Bearer {google_access_token}"
        )
    }

    try:
        response = requests.get(
            GOOGLE_USERINFO_URL,
            headers=headers,
            timeout=10,
        )
    except requests.RequestException as exc:
        raise ValidationError(
            "Unable to retrieve Google user information"
        ) from exc

    if not response.ok:
        raise ValidationError(
            "Unable to verify Google account"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise ValidationError(
            "Invalid user information received from Google"
        ) from exc

    google_user_id = data.get("sub")
    email = data.get("email")

    if not google_user_id or not email:
        raise ValidationError(
            "Google account information is incomplete"
        )

    email_verified = data.get(
        "email_verified",
        False,
    )

    if not email_verified:
        raise ValidationError(
            "Google email address is not verified"
        )

    return GoogleUserInfoSchema(
        provider_user_id=str(
            google_user_id
        ),
        email=email,
        first_name=data.get("given_name"),
        last_name=data.get("family_name"),
        picture=data.get("picture"),
        email_verified=bool(
            email_verified
        ),
    )


def _get_user_by_google_identity(
    provider_user_id: str,
) -> User | None:
    """
    Find an existing user through their Google identity.
    """
    identity = UserAuthIdentity.query.filter_by(
        provider=GOOGLE_PROVIDER,
        provider_user_id=provider_user_id,
    ).first()

    if identity is None:
        return None

    return identity.user


def _get_or_create_google_user(
    google_user: GoogleUserInfoSchema,
) -> tuple[User, bool]:
    """
    Resolve a Google identity to an application user.

    Returns:
        (user, created)
    """
    existing_user = _get_user_by_google_identity(
        google_user.provider_user_id
    )

    if existing_user is not None:
        return existing_user, False

    email = (
        str(google_user.email)
        .lower()
        .strip()
    )

    existing_user = User.query.filter_by(
        email=email
    ).first()

    if existing_user is not None:
        existing_identity = (
            UserAuthIdentity.query.filter_by(
                user_id=existing_user.id,
                provider=GOOGLE_PROVIDER,
            ).first()
        )

        if existing_identity is not None:
            if (
                existing_identity.provider_user_id
                != google_user.provider_user_id
            ):
                raise ConflictError(
                    "This user already has a different "
                    "Google identity linked"
                )

            return existing_user, False

        identity = UserAuthIdentity(
            user_id=existing_user.id,
            provider=GOOGLE_PROVIDER,
            provider_user_id=(
                google_user.provider_user_id
            ),
        )

        db.session.add(identity)

        return existing_user, False

    user = User(
        email=email,
        role=Role.PATIENT,
        password_hash=None,
    )

    db.session.add(user)
    db.session.flush()

    identity = UserAuthIdentity(
        user_id=user.id,
        provider=GOOGLE_PROVIDER,
        provider_user_id=(
            google_user.provider_user_id
        ),
    )

    db.session.add(identity)

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="User",
        entity_id=user.id,
        description=(
            f"Google user registered: {email}"
        ),
    )

    return user, True


def authenticate_google_user(
    google_user: GoogleUserInfoSchema,
) -> dict:
    """
    Authenticate an application user through Google.
    """
    if not google_user.email_verified:
        raise ValidationError(
            "Google email address is not verified"
        )

    user, created = _get_or_create_google_user(
        google_user
    )

    if not user.is_active:
        raise ValidationError(
            "This account has been deactivated"
        )

    additional_claims = {
        "role": user.role.value,
    }

    access_token = create_access_token(
    identity=str(user.id),
    additional_claims=additional_claims,
   )

    refresh_token = create_refresh_token(
      identity=str(user.id),
    )

    user.last_login_at = db.func.now()

    create_audit_log(
        action=AuditAction.LOGIN,
        entity_type="User",
        entity_id=user.id,
        description=(
            f"User '{user.email}' "
            f"logged in with Google"
        ),
        user_id=user.id,
    )

    db.session.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user_id": user.id,
        "role": user.role.value,
        "is_new_user": created,
    }


def authenticate_google_code(
    code: str,
) -> dict:
    """
    Complete Google authorization-code authentication.

    The caller must validate OAuth state before calling this
    function.
    """
    token_data = exchange_google_code(code)

    google_access_token = token_data.get(
        "access_token"
    )

    google_user = get_google_user_info(
        google_access_token
    )

    return authenticate_google_user(
        google_user
    )