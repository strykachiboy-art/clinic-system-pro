from __future__ import annotations

import pytest

from app.core.exceptions import ValidationError
from app.core.security.encryption import (
    get_encryption_key_version,
)
from app.modules.settings.schemas.integration_config import (
    IntegrationConfigCreateSchema,
    IntegrationConfigUpdateSchema,
)
from app.modules.settings.services.integration_config_service import (
    create_integration_config,
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
