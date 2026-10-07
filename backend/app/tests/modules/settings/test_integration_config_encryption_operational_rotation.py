from __future__ import annotations

import json

import pytest
from cryptography.fernet import Fernet

from app.core.exceptions import ValidationError
from app.extensions import db
from app.modules.settings.models.integration_config import (
    IntegrationConfig,
)
from app.modules.settings.schemas.integration_config import (
    IntegrationConfigCreateSchema,
)
from app.modules.settings.services.integration_config_service import (
    create_integration_config,
    get_integration_credentials,
    migrate_all_integration_credentials_to_active_key,
)


def _payload(
    provider: str,
    secret: str,
) -> IntegrationConfigCreateSchema:
    return IntegrationConfigCreateSchema(
        provider=provider,
        credentials={
            "secret_key": secret,
        },
        configuration={
            "environment": "test",
            "currency": "NGN",
        },
        is_enabled=True,
    )


def test_gate6_full_operational_key_rotation_cycle(
    app,
    clinic,
):
    with app.app_context():
        old_key = Fernet.generate_key().decode("utf-8")
        new_key = Fernet.generate_key().decode("utf-8")

        app.config["INTEGRATION_ENCRYPTION_KEY"] = old_key
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 1
        app.config["INTEGRATION_ENCRYPTION_LEGACY_KEYS"] = "{}"

        providers = [
            "paystack",
            "flutterwave",
            "stripe",
            "email",
            "sms",
        ]

        integrations = []

        for provider in providers:
            integration = create_integration_config(
                clinic_id=clinic.id,
                payload=_payload(
                    provider,
                    f"{provider}-secret",
                ),
            )
            integrations.append(integration)

        original_state = {
            integration.id: {
                "ciphertext": integration.encrypted_credentials,
                "credentials_version": integration.credentials_version,
                "last_rotated_at": integration.last_rotated_at,
            }
            for integration in integrations
        }

        app.config["INTEGRATION_ENCRYPTION_KEY"] = new_key
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 2
        app.config["INTEGRATION_ENCRYPTION_LEGACY_KEYS"] = (
            json.dumps({"1": old_key})
        )

        result = migrate_all_integration_credentials_to_active_key()

        assert result == {
            "inspected": 5,
            "migrated": 5,
            "already_current": 0,
            "skipped_missing_credentials": 0,
        }

        db.session.expire_all()

        for provider in providers:
            migrated = db.session.execute(
                db.select(IntegrationConfig).where(
                    IntegrationConfig.clinic_id == clinic.id,
                    IntegrationConfig.provider == provider,
                )
            ).scalar_one()

            original = original_state[migrated.id]

            assert migrated.encryption_key_version == 2
            assert migrated.credentials_version == (
                original["credentials_version"]
            )
            assert migrated.last_rotated_at == (
                original["last_rotated_at"]
            )
            assert migrated.encrypted_credentials != (
                original["ciphertext"]
            )

            assert get_integration_credentials(
                clinic_id=clinic.id,
                provider=provider,
            ) == {
                "secret_key": f"{provider}-secret",
            }

        # Retirement validation:
        # current credentials must remain readable with no legacy key.
        app.config["INTEGRATION_ENCRYPTION_LEGACY_KEYS"] = "{}"

        for provider in providers:
            assert get_integration_credentials(
                clinic_id=clinic.id,
                provider=provider,
            ) == {
                "secret_key": f"{provider}-secret",
            }

        # Application rollback validation:
        # old active key must remain usable while the new key is retained
        # as the legacy key for already-migrated records.
        app.config["INTEGRATION_ENCRYPTION_KEY"] = old_key
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 1
        app.config["INTEGRATION_ENCRYPTION_LEGACY_KEYS"] = (
            json.dumps({"2": new_key})
        )

        for provider in providers:
            assert get_integration_credentials(
                clinic_id=clinic.id,
                provider=provider,
            ) == {
                "secret_key": f"{provider}-secret",
            }

        # Restore the rotated configuration for the final state.
        app.config["INTEGRATION_ENCRYPTION_KEY"] = new_key
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 2
        app.config["INTEGRATION_ENCRYPTION_LEGACY_KEYS"] = "{}"

        for provider in providers:
            assert get_integration_credentials(
                clinic_id=clinic.id,
                provider=provider,
            ) == {
                "secret_key": f"{provider}-secret",
            }


def test_gate6_rotation_fails_closed_without_retired_key(
    app,
    clinic,
):
    with app.app_context():
        old_key = Fernet.generate_key().decode("utf-8")
        new_key = Fernet.generate_key().decode("utf-8")

        app.config["INTEGRATION_ENCRYPTION_KEY"] = old_key
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 1
        app.config["INTEGRATION_ENCRYPTION_LEGACY_KEYS"] = "{}"

        first = create_integration_config(
            clinic_id=clinic.id,
            payload=_payload("paystack", "rotation-fail-secret"),
        )

        old_ciphertext = first.encrypted_credentials

        app.config["INTEGRATION_ENCRYPTION_KEY"] = new_key
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 2
        app.config["INTEGRATION_ENCRYPTION_LEGACY_KEYS"] = "{}"

        with pytest.raises(
            ValidationError,
            match="Encryption key version 1 is not configured",
        ):
            migrate_all_integration_credentials_to_active_key()

        db.session.expire_all()

        persisted = db.session.get(
            IntegrationConfig,
            first.id,
        )

        assert persisted is not None
        assert persisted.encryption_key_version == 1
        assert persisted.encrypted_credentials == old_ciphertext
