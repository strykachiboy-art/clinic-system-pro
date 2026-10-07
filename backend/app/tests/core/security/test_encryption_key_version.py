from __future__ import annotations

import json

import pytest
from cryptography.fernet import Fernet

from app.core.exceptions import ValidationError
from app.core.security.encryption import (
    decrypt_credentials,
    get_encryption_key_version,
)
from app.modules.settings.schemas.integration_config import (
    IntegrationConfigCreateSchema,
    IntegrationConfigUpdateSchema,
)
from app.modules.settings.services.integration_config_service import (
    create_integration_config,
    get_integration_credentials,
    rotate_integration_credentials,
    update_integration_config,
)


def _create_payload():
    return IntegrationConfigCreateSchema(
        provider="paystack",
        credentials={
            "secret_key": "versioned-secret",
        },
        configuration={
            "environment": "test",
            "currency": "NGN",
        },
        is_enabled=True,
    )


def test_encryption_key_version_defaults_to_one(app):
    with app.app_context():
        assert get_encryption_key_version() == 1


def test_encryption_key_version_accepts_configured_version(
    app,
):
    with app.app_context():
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 2

        assert get_encryption_key_version() == 2


@pytest.mark.parametrize(
    "configured_value",
    [
        None,
        "",
        "0",
        0,
        "-1",
        "not-a-number",
        True,
    ],
)
def test_encryption_key_version_rejects_invalid_values(
    app,
    configured_value,
):
    with app.app_context():
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = (
            configured_value
        )

        with pytest.raises(
            ValidationError,
            match="INTEGRATION_ENCRYPTION_KEY_VERSION",
        ):
            get_encryption_key_version()


def test_create_stamps_active_encryption_key_version(
    app,
    clinic,
):
    with app.app_context():
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 2

        integration = create_integration_config(
            clinic_id=clinic.id,
            payload=_create_payload(),
        )

        assert integration.encryption_key_version == 2
        assert integration.credentials_version == 1


def test_update_credentials_stamps_active_encryption_key_version(
    app,
    clinic,
):
    with app.app_context():
        create_integration_config(
            clinic_id=clinic.id,
            payload=_create_payload(),
        )

        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 2

        updated = update_integration_config(
            clinic_id=clinic.id,
            provider="paystack",
            payload=IntegrationConfigUpdateSchema(
                credentials={
                    "secret_key": "updated-secret",
                },
            ),
        )

        assert updated.encryption_key_version == 2
        assert updated.credentials_version == 2


def test_rotate_credentials_stamps_active_encryption_key_version(
    app,
    clinic,
):
    with app.app_context():
        integration = create_integration_config(
            clinic_id=clinic.id,
            payload=_create_payload(),
        )

        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 3

        rotated = rotate_integration_credentials(
            clinic_id=clinic.id,
            provider="paystack",
            credentials={
                "secret_key": "rotated-secret",
            },
        )

        assert rotated.id == integration.id
        assert rotated.encryption_key_version == 3
        assert rotated.credentials_version == 2


def test_credential_version_and_encryption_key_version_are_independent(
    app,
    clinic,
):
    with app.app_context():
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 2

        integration = create_integration_config(
            clinic_id=clinic.id,
            payload=_create_payload(),
        )

        assert integration.credentials_version == 1
        assert integration.encryption_key_version == 2

        rotated = rotate_integration_credentials(
            clinic_id=clinic.id,
            provider="paystack",
            credentials={
                "secret_key": "rotated-again",
            },
        )

        assert rotated.credentials_version == 2
        assert rotated.encryption_key_version == 2


def test_decrypt_credentials_uses_exact_legacy_key_version(
    app,
):
    with app.app_context():
        legacy_key = Fernet.generate_key().decode("utf-8")

        app.config["INTEGRATION_ENCRYPTION_KEY"] = legacy_key
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 1

        from app.core.security.encryption import (
            encrypt_credentials,
        )

        credentials = {
            "secret_key": "legacy-secret",
        }

        encrypted = encrypt_credentials(
            credentials
        )

        app.config["INTEGRATION_ENCRYPTION_KEY"] = (
            Fernet.generate_key().decode("utf-8")
        )
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 2
        app.config["INTEGRATION_ENCRYPTION_LEGACY_KEYS"] = (
            json.dumps({"1": legacy_key})
        )

        assert decrypt_credentials(
            encrypted,
            encryption_key_version=1,
        ) == credentials


def test_decrypt_credentials_rejects_unknown_legacy_key_version(
    app,
):
    with app.app_context():
        legacy_key = Fernet.generate_key().decode("utf-8")

        app.config["INTEGRATION_ENCRYPTION_KEY"] = legacy_key
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 1

        from app.core.security.encryption import (
            encrypt_credentials,
        )

        encrypted = encrypt_credentials(
            {
                "secret_key": "legacy-secret",
            }
        )

        with pytest.raises(
            ValidationError,
            match="Encryption key version 99 is not configured",
        ):
            decrypt_credentials(
                encrypted,
                encryption_key_version=99,
            )


def test_decrypt_credentials_rejects_wrong_legacy_key(
    app,
):
    with app.app_context():
        legacy_key = Fernet.generate_key().decode("utf-8")

        app.config["INTEGRATION_ENCRYPTION_KEY"] = legacy_key
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 1

        from app.core.security.encryption import (
            encrypt_credentials,
        )

        encrypted = encrypt_credentials(
            {
                "secret_key": "legacy-secret",
            }
        )

        wrong_key = Fernet.generate_key().decode("utf-8")

        app.config["INTEGRATION_ENCRYPTION_KEY"] = (
            Fernet.generate_key().decode("utf-8")
        )
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 2
        app.config["INTEGRATION_ENCRYPTION_LEGACY_KEYS"] = (
            json.dumps({"1": wrong_key})
        )

        with pytest.raises(
            ValidationError,
            match="Unable to decrypt integration credentials",
        ):
            decrypt_credentials(
                encrypted,
                encryption_key_version=1,
            )


def test_decrypt_credentials_rejects_invalid_legacy_keyring(
    app,
):
    with app.app_context():
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 2
        app.config["INTEGRATION_ENCRYPTION_LEGACY_KEYS"] = (
            "not-json"
        )

        with pytest.raises(
            ValidationError,
            match="INTEGRATION_ENCRYPTION_LEGACY_KEYS is invalid",
        ):
            decrypt_credentials(
                "synthetic-ciphertext",
                encryption_key_version=1,
            )


def test_get_integration_credentials_uses_recorded_legacy_key(
    app,
    clinic,
):
    with app.app_context():
        legacy_key = app.config[
            "INTEGRATION_ENCRYPTION_KEY"
        ]

        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 1

        integration = create_integration_config(
            clinic_id=clinic.id,
            payload=_create_payload(),
        )

        app.config["INTEGRATION_ENCRYPTION_KEY"] = (
            Fernet.generate_key().decode("utf-8")
        )
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 2
        app.config["INTEGRATION_ENCRYPTION_LEGACY_KEYS"] = (
            json.dumps({"1": legacy_key})
        )

        credentials = get_integration_credentials(
            clinic_id=clinic.id,
            provider=integration.provider,
        )

        assert credentials == {
            "secret_key": "versioned-secret",
        }
