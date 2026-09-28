from __future__ import annotations

from collections.abc import Mapping
from typing import Any


REDACTED_VALUE = "[REDACTED]"

_SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "passwd",
    "passcode",
    "secret",
    "client_secret",
    "api_key",
    "access_token",
    "refresh_token",
    "id_token",
    "token",
    "authorization",
    "cookie",
    "otp",
    "otp_code",
    "mfa_code",
    "private_key",
    "signing_key",
    "encryption_key",
}


def _normalize_key(key: Any) -> str:
    return (
        str(key)
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


def _is_sensitive_key(key: Any) -> bool:
    normalized = _normalize_key(key)

    if normalized in _SENSITIVE_KEYS:
        return True

    if normalized.endswith("_token"):
        return True

    if normalized.endswith("_secret"):
        return True

    if normalized.endswith("_api_key"):
        return True

    return False


def redact_audit_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: (
                REDACTED_VALUE
                if _is_sensitive_key(key)
                else redact_audit_payload(item)
            )
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            redact_audit_payload(item)
            for item in value
        ]

    if isinstance(value, tuple):
        return tuple(
            redact_audit_payload(item)
            for item in value
        )

    return value