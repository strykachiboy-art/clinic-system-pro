from datetime import datetime, timezone

from flask_jwt_extended import get_jwt

from app.core.exceptions import ValidationError
from app import extensions


REVOKED_TOKEN_PREFIX = "auth:revoked:"


def _revoked_token_key(jti: str) -> str:
    return f"{REVOKED_TOKEN_PREFIX}{jti}"


def _token_remaining_seconds(jwt_payload: dict | None = None) -> int:
    if jwt_payload is None:
        jwt_payload = get_jwt()

    exp = jwt_payload.get("exp")

    if exp is None:
        raise ValidationError("JWT expiration is missing")

    now = datetime.now(timezone.utc).timestamp()
    remaining = int(exp - now)

    return max(remaining, 1)


def revoke_token(jwt_payload: dict) -> None:
    """
    Revoke a JWT using its JTI.

    The Redis entry expires automatically when the JWT itself
    expires, so revoked-token storage does not grow forever.
    """
    if extensions.redis_client is None:
        raise ValidationError(
            "Redis is not available for token revocation"
        )

    jti = jwt_payload.get("jti")

    if not jti:
        raise ValidationError("JWT ID is missing")

    extensions.redis_client.setex(
        _revoked_token_key(jti),
        _token_remaining_seconds(jwt_payload),
        "1",
    )


def revoke_current_token() -> None:
    """
    Revoke the JWT currently authenticated on the request.
    """
    revoke_token(get_jwt())


def is_token_revoked(jwt_payload: dict) -> bool:
    """
    Return True when the JWT has been revoked.

    Redis failure fails closed so authentication does not
    silently bypass token revocation.
    """
    if extensions.redis_client is None:
        return True

    jti = jwt_payload.get("jti")

    if not jti:
        return True

    return bool(
        extensions.redis_client.exists(
            _revoked_token_key(jti)
        )
    )