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


def test_key_migration_reencrypts_stale_credentials(
    app,
    clinic,
):
    with app.app_context():
        old_key = Fernet.generate_key().decode("utf-8")
        new_key = Fernet.generate_key().decode("utf-8")

        app.config["INTEGRATION_ENCRYPTION_KEY"] = old_key
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 1
        app.config["INTEGRATION_ENCRYPTION_LEGACY_KEYS"] = "{}"

        integration = create_integration_config(
            clinic_id=clinic.id,
            payload=_payload(
                "paystack",
                "legacy-secret",
            ),
        )

        old_ciphertext = integration.encrypted_credentials
        old_credentials_version = integration.credentials_version
        old_rotation_time = integration.last_rotated_at

        app.config["INTEGRATION_ENCRYPTION_KEY"] = new_key
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 2
        app.config["INTEGRATION_ENCRYPTION_LEGACY_KEYS"] = (
            json.dumps({"1": old_key})
        )

        result = migrate_all_integration_credentials_to_active_key()

        assert result == {
            "inspected": 1,
            "migrated": 1,
            "already_current": 0,
            "skipped_missing_credentials": 0,
        }

        db.session.expire_all()

        migrated = db.session.get(
            IntegrationConfig,
            integration.id,
        )

        assert migrated is not None
        assert migrated.encryption_key_version == 2
        assert migrated.credentials_version == old_credentials_version
        assert migrated.last_rotated_at == old_rotation_time
        assert migrated.encrypted_credentials != old_ciphertext

        assert get_integration_credentials(
            clinic_id=clinic.id,
            provider="paystack",
        ) == {
            "secret_key": "legacy-secret",
        }


def test_key_migration_is_idempotent(
    app,
    clinic,
):
    with app.app_context():
        active_key = Fernet.generate_key().decode("utf-8")

        app.config["INTEGRATION_ENCRYPTION_KEY"] = active_key
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 2
        app.config["INTEGRATION_ENCRYPTION_LEGACY_KEYS"] = "{}"

        integration = create_integration_config(
            clinic_id=clinic.id,
            payload=_payload(
                "flutterwave",
                "current-secret",
            ),
        )

        ciphertext_before = integration.encrypted_credentials

        result = migrate_all_integration_credentials_to_active_key()

        assert result == {
            "inspected": 1,
            "migrated": 0,
            "already_current": 1,
            "skipped_missing_credentials": 0,
        }

        assert integration.encryption_key_version == 2
        assert integration.credentials_version == 1
        assert integration.encrypted_credentials == ciphertext_before


def test_key_migration_skips_missing_credentials(
    app,
    clinic,
):
    with app.app_context():
        active_key = Fernet.generate_key().decode("utf-8")

        app.config["INTEGRATION_ENCRYPTION_KEY"] = active_key
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 2
        app.config["INTEGRATION_ENCRYPTION_LEGACY_KEYS"] = "{}"

        integration = IntegrationConfig(
            clinic_id=clinic.id,
            provider="gate5-missing",
            is_enabled=True,
            configuration={},
            encrypted_credentials=None,
            credentials_version=1,
            encryption_key_version=1,
        )

        db.session.add(integration)
        db.session.flush()

        result = migrate_all_integration_credentials_to_active_key()

        assert result == {
            "inspected": 1,
            "migrated": 0,
            "already_current": 0,
            "skipped_missing_credentials": 1,
        }

        assert integration.encryption_key_version == 1


def test_key_migration_rolls_back_all_changes_on_failure(
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
            payload=_payload(
                "stripe",
                "first-secret",
            ),
        )

        second = create_integration_config(
            clinic_id=clinic.id,
            payload=_payload(
                "email",
                "second-secret",
            ),
        )

        first_ciphertext = first.encrypted_credentials
        second.encrypted_credentials = (
            "corrupted-ciphertext"
        )

        db.session.commit()

        app.config["INTEGRATION_ENCRYPTION_KEY"] = new_key
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 2
        app.config["INTEGRATION_ENCRYPTION_LEGACY_KEYS"] = (
            json.dumps({"1": old_key})
        )

        with pytest.raises(
            ValidationError,
            match="Unable to decrypt integration credentials",
        ):
            migrate_all_integration_credentials_to_active_key()

        db.session.expire_all()

        persisted_first = db.session.get(
            IntegrationConfig,
            first.id,
        )

        persisted_second = db.session.get(
            IntegrationConfig,
            second.id,
        )

        assert persisted_first is not None
        assert persisted_second is not None

        assert persisted_first.encryption_key_version == 1
        assert persisted_first.encrypted_credentials == first_ciphertext
        assert persisted_second.encryption_key_version == 1
        assert persisted_second.encrypted_credentials == (
            "corrupted-ciphertext"
        )


def test_key_migration_supports_application_rollback(
    app,
    clinic,
):
    with app.app_context():
        old_key = Fernet.generate_key().decode("utf-8")
        new_key = Fernet.generate_key().decode("utf-8")

        app.config["INTEGRATION_ENCRYPTION_KEY"] = old_key
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 1
        app.config["INTEGRATION_ENCRYPTION_LEGACY_KEYS"] = "{}"

        integration = create_integration_config(
            clinic_id=clinic.id,
            payload=_payload(
                "sms",
                "rollback-secret",
            ),
        )

        app.config["INTEGRATION_ENCRYPTION_KEY"] = new_key
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 2
        app.config["INTEGRATION_ENCRYPTION_LEGACY_KEYS"] = (
            json.dumps({"1": old_key})
        )

        migrate_all_integration_credentials_to_active_key()

        assert get_integration_credentials(
            clinic_id=clinic.id,
            provider=integration.provider,
        ) == {
            "secret_key": "rollback-secret",
        }

        app.config["INTEGRATION_ENCRYPTION_KEY"] = old_key
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 1
        app.config["INTEGRATION_ENCRYPTION_LEGACY_KEYS"] = (
            json.dumps({"2": new_key})
        )

        assert get_integration_credentials(
            clinic_id=clinic.id,
            provider=integration.provider,
        ) == {
            "secret_key": "rollback-secret",
        }

        app.config["INTEGRATION_ENCRYPTION_KEY"] = new_key
        app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = 2
        app.config["INTEGRATION_ENCRYPTION_LEGACY_KEYS"] = "{}"

        assert get_integration_credentials(
            clinic_id=clinic.id,
            provider=integration.provider,
        ) == {
            "secret_key": "rollback-secret",
        }