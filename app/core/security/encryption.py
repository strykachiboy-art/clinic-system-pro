from __future__ import annotations

import base64
import json
import os
from typing import Any

from cryptography.fernet import (
    Fernet,
    InvalidToken,
)
from flask import current_app

from app.core.exceptions import ValidationError


_ENCRYPTION_KEY_CONFIG = (
    "INTEGRATION_ENCRYPTION_KEY"
)


def _get_fernet() -> Fernet:
    """
    Return the configured Fernet encryption instance.
    """

    key = current_app.config.get(
        _ENCRYPTION_KEY_CONFIG
    )

    if not key:
        raise ValidationError(
            "INTEGRATION_ENCRYPTION_KEY is not configured"
        )

    if not isinstance(key, str):
        raise ValidationError(
            "INTEGRATION_ENCRYPTION_KEY is invalid"
        )

    try:
        return Fernet(
            key.encode("utf-8")
        )
    except (
        ValueError,
        TypeError,
    ) as exc:
        raise ValidationError(
            "INTEGRATION_ENCRYPTION_KEY is invalid"
        ) from exc


def encrypt_credentials(
    credentials: dict[str, Any],
) -> str:
    """
    Encrypt integration credentials.

    Credentials are serialized to JSON and encrypted
    using the configured Fernet key.

    The plaintext credentials are never returned.
    """

    if not isinstance(credentials, dict):
        raise ValidationError(
            "Credentials must be an object"
        )

    if not credentials:
        raise ValidationError(
            "Credentials cannot be empty"
        )

    try:
        payload = json.dumps(
            credentials,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValidationError(
            "Credentials contain unsupported values"
        ) from exc

    fernet = _get_fernet()

    encrypted = fernet.encrypt(
        payload
    )

    return encrypted.decode("utf-8")


def decrypt_credentials(
    encrypted_credentials: str,
) -> dict[str, Any]:
    """
    Decrypt integration credentials.
    """

    if not encrypted_credentials:
        raise ValidationError(
            "Encrypted credentials are missing"
        )

    if not isinstance(
        encrypted_credentials,
        str,
    ):
        raise ValidationError(
            "Encrypted credentials are invalid"
        )

    fernet = _get_fernet()

    try:
        decrypted = fernet.decrypt(
            encrypted_credentials.encode(
                "utf-8"
            )
        )

    except InvalidToken as exc:
        raise ValidationError(
            "Unable to decrypt integration credentials"
        ) from exc

    try:
        credentials = json.loads(
            decrypted.decode("utf-8")
        )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValidationError(
            "Decrypted credentials are invalid"
        ) from exc

    if not isinstance(
        credentials,
        dict,
    ):
        raise ValidationError(
            "Decrypted credentials must be an object"
        )

    return credentials


def generate_encryption_key() -> str:
    """
    Generate a new Fernet-compatible encryption key.
    """

    return base64.urlsafe_b64encode(
        os.urandom(32)
    ).decode("utf-8")