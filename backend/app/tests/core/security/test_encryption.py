from __future__ import annotations

import json

import pytest
from cryptography.fernet import Fernet

from app.core.exceptions import ValidationError
from app.core.security.encryption import (
    decrypt_credentials,
    encrypt_credentials,
    generate_encryption_key,
)


def test_encrypt_decrypt_credentials_round_trip(app):
    with app.app_context():
        credentials = {
            "secret_key": "sk_test_secret",
            "public_key": "pk_test_public",
        }

        encrypted = encrypt_credentials(credentials)

        assert isinstance(encrypted, str)
        assert encrypted
        assert "sk_test_secret" not in encrypted
        assert "pk_test_public" not in encrypted

        assert decrypt_credentials(encrypted) == credentials


def test_generate_encryption_key_produces_valid_fernet_key():
    key = generate_encryption_key()

    assert isinstance(key, str)
    assert key

    Fernet(key.encode("utf-8"))


def test_encrypt_credentials_rejects_empty_credentials(app):
    with app.app_context():
        with pytest.raises(
            ValidationError,
            match="Credentials cannot be empty",
        ):
            encrypt_credentials({})


def test_encrypt_credentials_rejects_non_object(app):
    with app.app_context():
        with pytest.raises(
            ValidationError,
            match="Credentials must be an object",
        ):
            encrypt_credentials(["secret"])


def test_decrypt_credentials_fails_closed_when_key_is_missing(
    app,
):
    with app.app_context():
        app.config["INTEGRATION_ENCRYPTION_KEY"] = None

        with pytest.raises(
            ValidationError,
            match="INTEGRATION_ENCRYPTION_KEY is not configured",
        ):
            decrypt_credentials("synthetic-ciphertext")


def test_decrypt_credentials_fails_closed_when_key_is_invalid(
    app,
):
    with app.app_context():
        app.config["INTEGRATION_ENCRYPTION_KEY"] = (
            "not-a-valid-fernet-key"
        )

        with pytest.raises(
            ValidationError,
            match="INTEGRATION_ENCRYPTION_KEY is invalid",
        ):
            decrypt_credentials("synthetic-ciphertext")


def test_decrypt_credentials_fails_closed_with_wrong_key(
    app,
):
    with app.app_context():
        credentials = {
            "secret_key": "sk_test_secret",
            "public_key": "pk_test_public",
        }

        encrypted = encrypt_credentials(credentials)

        app.config["INTEGRATION_ENCRYPTION_KEY"] = (
            Fernet.generate_key().decode("utf-8")
        )

        with pytest.raises(
            ValidationError,
            match="Unable to decrypt integration credentials",
        ):
            decrypt_credentials(encrypted)


def test_decrypt_credentials_fails_closed_with_corrupted_ciphertext(
    app,
):
    with app.app_context():
        encrypted = encrypt_credentials(
            {
                "secret_key": "sk_test_secret",
            }
        )

        corrupted = encrypted[:-1] + (
            "A"
            if encrypted[-1] != "A"
            else "B"
        )

        with pytest.raises(
            ValidationError,
            match="Unable to decrypt integration credentials",
        ):
            decrypt_credentials(corrupted)


def test_decrypt_credentials_rejects_non_object_plaintext(
    app,
):
    with app.app_context():
        fernet = Fernet(
            app.config["INTEGRATION_ENCRYPTION_KEY"].encode(
                "utf-8"
            )
        )

        encrypted = fernet.encrypt(
            json.dumps(
                ["not", "a", "credential", "object"]
            ).encode("utf-8")
        ).decode("utf-8")

        with pytest.raises(
            ValidationError,
            match="Decrypted credentials must be an object",
        ):
            decrypt_credentials(encrypted)
