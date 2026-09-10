from __future__ import annotations

import pytest

from app.core.enums.clinic_enums import ClinicStatus
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.security.encryption import decrypt_credentials
from app.extensions import db
from app.modules.clinic.models.clinic_model import Clinic
from app.modules.settings.models.integration_config import IntegrationConfig
from app.modules.settings.schemas.integration_config import (
    IntegrationConfigCreateSchema,
    IntegrationConfigUpdateSchema,
)
from app.modules.settings.services.integration_config_service import (
    create_integration_config,
    delete_integration_config,
    disable_integration_config,
    enable_integration_config,
    get_integration_config,
    get_integration_config_by_id,
    get_integration_credentials,
    list_integration_configs,
    rotate_integration_credentials,
    update_integration_config,
)


def _create_clinic(
    *,
    name: str,
    status: ClinicStatus = ClinicStatus.ACTIVE,
) -> Clinic:
    clinic = Clinic(
        name=name,
        status=status,
    )

    db.session.add(clinic)
    db.session.flush()

    return clinic


def _create_payload(
    *,
    provider: str = "paystack",
    credentials: dict | None = None,
    configuration: dict | None = None,
    is_enabled: bool = False,
) -> IntegrationConfigCreateSchema:
    return IntegrationConfigCreateSchema(
        provider=provider,
        credentials=credentials
        or {
            "secret_key": "sk_test_secret",
            "public_key": "pk_test_public",
        },
        configuration=configuration
        or {
            "currency": "NGN",
            "environment": "test",
        },
        is_enabled=is_enabled,
    )


def _create_integration(
    clinic_id: int,
    *,
    provider: str = "paystack",
    enabled: bool = False,
    credentials: dict | None = None,
) -> IntegrationConfig:
    return create_integration_config(
        clinic_id=clinic_id,
        payload=_create_payload(
            provider=provider,
            credentials=credentials,
            is_enabled=enabled,
        ),
    )


def test_create_integration_config_success(app):
    with app.app_context():
        clinic = _create_clinic(
            name="Test Clinic",
        )

        credentials = {
            "secret_key": "sk_test_123",
            "public_key": "pk_test_123",
        }

        payload = _create_payload(
            credentials=credentials,
            is_enabled=True,
        )

        integration = create_integration_config(
            clinic_id=clinic.id,
            payload=payload,
        )

        assert integration.id is not None
        assert integration.clinic_id == clinic.id
        assert integration.provider == "paystack"
        assert integration.is_enabled is True
        assert integration.configuration["currency"] == "NGN"

        assert integration.encrypted_credentials
        assert "sk_test_123" not in integration.encrypted_credentials
        assert "pk_test_123" not in integration.encrypted_credentials

        assert integration.credentials_version == 1
        assert integration.last_rotated_at is not None


def test_create_integration_config_encrypts_credentials(app):
    with app.app_context():
        clinic = _create_clinic(
            name="Encryption Clinic",
        )

        credentials = {
            "secret_key": "super-secret-value",
            "public_key": "public-value",
        }

        integration = create_integration_config(
            clinic.id,
            _create_payload(
                credentials=credentials,
            ),
        )

        assert integration.encrypted_credentials != str(
            credentials
        )

        decrypted = decrypt_credentials(
            integration.encrypted_credentials
        )

        assert decrypted == credentials


def test_create_integration_config_rejects_duplicate_provider(
    app,
):
    with app.app_context():
        clinic = _create_clinic(
            name="Duplicate Clinic",
        )

        _create_integration(
            clinic.id,
            provider="paystack",
        )

        with pytest.raises(ConflictError):
            _create_integration(
                clinic.id,
                provider="paystack",
            )


def test_create_integration_config_allows_same_provider_for_different_clinics(
    app,
):
    with app.app_context():
        clinic_one = _create_clinic(
            name="Clinic One",
        )

        clinic_two = _create_clinic(
            name="Clinic Two",
        )

        first = _create_integration(
            clinic_one.id,
            provider="paystack",
        )

        second = _create_integration(
            clinic_two.id,
            provider="paystack",
        )

        assert first.id != second.id
        assert first.clinic_id != second.clinic_id


def test_create_integration_config_rejects_inactive_clinic(
    app,
):
    with app.app_context():
        clinic = _create_clinic(
            name="Inactive Clinic",
            status=ClinicStatus.INACTIVE,
        )

        with pytest.raises(ValidationError):
            _create_integration(
                clinic.id,
            )


def test_create_integration_config_rejects_missing_clinic(
    app,
):
    with app.app_context():
        payload = _create_payload()

        with pytest.raises(NotFoundError):
            create_integration_config(
                clinic_id=999999,
                payload=payload,
            )


def test_get_integration_config_success(app):
    with app.app_context():
        clinic = _create_clinic(
            name="Read Clinic",
        )

        created = _create_integration(
            clinic.id,
            provider="paystack",
        )

        result = get_integration_config(
            clinic_id=clinic.id,
            provider="PAYSTACK",
        )

        assert result.id == created.id
        assert result.provider == "paystack"
        assert result.clinic_id == clinic.id


def test_get_integration_config_normalizes_provider(
    app,
):
    with app.app_context():
        clinic = _create_clinic(
            name="Provider Clinic",
        )

        created = _create_integration(
            clinic.id,
            provider="paystack",
        )

        result = get_integration_config(
            clinic.id,
            "  PAYSTACK  ",
        )

        assert result.id == created.id


def test_get_integration_config_rejects_empty_provider(
    app,
):
    with app.app_context():
        clinic = _create_clinic(
            name="Provider Validation Clinic",
        )

        with pytest.raises(ValidationError):
            get_integration_config(
                clinic.id,
                "   ",
            )


def test_get_integration_config_not_found(app):
    with app.app_context():
        clinic = _create_clinic(
            name="Missing Integration Clinic",
        )

        with pytest.raises(NotFoundError):
            get_integration_config(
                clinic.id,
                "paystack",
            )


def test_get_integration_config_by_id_success(app):
    with app.app_context():
        clinic = _create_clinic(
            name="ID Clinic",
        )

        created = _create_integration(
            clinic.id,
        )

        result = get_integration_config_by_id(
            clinic.id,
            created.id,
        )

        assert result.id == created.id


def test_get_integration_config_by_id_rejects_invalid_id(
    app,
):
    with app.app_context():
        clinic = _create_clinic(
            name="Invalid ID Clinic",
        )

        with pytest.raises(ValidationError):
            get_integration_config_by_id(
                clinic.id,
                0,
            )


def test_get_integration_config_by_id_prevents_idor(
    app,
):
    with app.app_context():
        clinic_one = _create_clinic(
            name="Owner Clinic",
        )

        clinic_two = _create_clinic(
            name="Attacker Clinic",
        )

        integration = _create_integration(
            clinic_one.id,
        )

        with pytest.raises(NotFoundError):
            get_integration_config_by_id(
                clinic_two.id,
                integration.id,
            )


def test_list_integration_configs_returns_only_enabled_by_default(
    app,
):
    with app.app_context():
        clinic = _create_clinic(
            name="List Clinic",
        )

        enabled = _create_integration(
            clinic.id,
            provider="paystack",
            enabled=True,
        )

        _create_integration(
            clinic.id,
            provider="stripe",
            enabled=False,
        )

        results, total = list_integration_configs(
            clinic.id,
        )

        assert total == 1
        assert len(results) == 1
        assert results[0].id == enabled.id
        assert results[0].is_enabled is True


def test_list_integration_configs_can_include_disabled(
    app,
):
    with app.app_context():
        clinic = _create_clinic(
            name="Disabled List Clinic",
        )

        _create_integration(
            clinic.id,
            provider="paystack",
            enabled=True,
        )

        _create_integration(
            clinic.id,
            provider="stripe",
            enabled=False,
        )

        results, total = list_integration_configs(
            clinic.id,
            include_disabled=True,
        )

        assert total == 2
        assert len(results) == 2

        providers = {
            integration.provider
            for integration in results
        }

        assert providers == {
            "paystack",
            "stripe",
        }


def test_list_integration_configs_filters_by_provider(
    app,
):
    with app.app_context():
        clinic = _create_clinic(
            name="Provider Filter Clinic",
        )

        paystack = _create_integration(
            clinic.id,
            provider="paystack",
            enabled=True,
        )

        _create_integration(
            clinic.id,
            provider="stripe",
            enabled=True,
        )

        results, total = list_integration_configs(
            clinic.id,
            provider="PAYSTACK",
        )

        assert total == 1
        assert len(results) == 1
        assert results[0].id == paystack.id


def test_list_integration_configs_is_tenant_scoped(
    app,
):
    with app.app_context():
        clinic_one = _create_clinic(
            name="Tenant One",
        )

        clinic_two = _create_clinic(
            name="Tenant Two",
        )

        first = _create_integration(
            clinic_one.id,
            provider="paystack",
            enabled=True,
        )

        second = _create_integration(
            clinic_two.id,
            provider="paystack",
            enabled=True,
        )

        results, total = list_integration_configs(
            clinic_one.id,
            include_disabled=True,
        )

        assert total == 1
        assert len(results) == 1
        assert results[0].id == first.id
        assert results[0].id != second.id


def test_list_integration_configs_default_pagination(app):
    with app.app_context():
        clinic = _create_clinic(
            name="Default Pagination Clinic",
        )

        providers = [
            "paystack",
            "flutterwave",
            "stripe",
            "email",
            "sms",
        ]

        for provider in providers:
            _create_integration(
                clinic.id,
                provider=provider,
                enabled=True,
            )

        results, total = list_integration_configs(
            clinic.id,
        )

        assert total == 5
        assert len(results) == 5

        assert [
            integration.provider
            for integration in results
        ] == [
            "email",
            "flutterwave",
            "paystack",
            "sms",
            "stripe",
        ]


def test_list_integration_configs_custom_pagination(app):
    with app.app_context():
        clinic = _create_clinic(
            name="Custom Pagination Clinic",
        )

        providers = [
            "paystack",
            "flutterwave",
            "stripe",
            "email",
            "sms",
        ]

        integrations = [
            _create_integration(
                clinic.id,
                provider=provider,
                enabled=True,
            )
            for provider in providers
        ]

        results, total = list_integration_configs(
            clinic.id,
            page=1,
            per_page=2,
        )

        assert total == 5
        assert len(results) == 2

        assert [
            integration.id
            for integration in results
        ] == [
            integrations[3].id,
            integrations[1].id,
        ]


def test_list_integration_configs_returns_middle_page(app):
    with app.app_context():
        clinic = _create_clinic(
            name="Middle Page Clinic",
        )

        providers = [
            "paystack",
            "flutterwave",
            "stripe",
            "email",
            "sms",
        ]

        integrations = [
            _create_integration(
                clinic.id,
                provider=provider,
                enabled=True,
            )
            for provider in providers
        ]

        results, total = list_integration_configs(
            clinic.id,
            page=2,
            per_page=2,
        )

        assert total == 5
        assert len(results) == 2

        assert [
            integration.id
            for integration in results
        ] == [
            integrations[0].id,
            integrations[4].id,
        ]


def test_list_integration_configs_returns_last_partial_page(app):
    with app.app_context():
        clinic = _create_clinic(
            name="Last Page Clinic",
        )

        providers = [
            "paystack",
            "flutterwave",
            "stripe",
            "email",
            "sms",
        ]

        integrations = [
            _create_integration(
                clinic.id,
                provider=provider,
                enabled=True,
            )
            for provider in providers
        ]

        results, total = list_integration_configs(
            clinic.id,
            page=3,
            per_page=2,
        )

        assert total == 5
        assert len(results) == 1
        assert results[0].id == integrations[2].id


def test_list_integration_configs_out_of_range_page_returns_empty(
    app,
):
    with app.app_context():
        clinic = _create_clinic(
            name="Out Of Range Clinic",
        )

        for provider in [
            "paystack",
            "flutterwave",
            "stripe",
        ]:
            _create_integration(
                clinic.id,
                provider=provider,
                enabled=True,
            )

        results, total = list_integration_configs(
            clinic.id,
            page=4,
            per_page=2,
        )

        assert total == 3
        assert results == []


def test_list_integration_configs_empty_result_returns_zero_total(
    app,
):
    with app.app_context():
        clinic = _create_clinic(
            name="Empty Result Clinic",
        )

        results, total = list_integration_configs(
            clinic.id,
        )

        assert total == 0
        assert results == []


def test_list_integration_configs_provider_filter_with_pagination(
    app,
):
    with app.app_context():
        clinic = _create_clinic(
            name="Provider Pagination Clinic",
        )

        paystack = _create_integration(
            clinic.id,
            provider="paystack",
            enabled=True,
        )

        _create_integration(
            clinic.id,
            provider="stripe",
            enabled=True,
        )

        results, total = list_integration_configs(
            clinic.id,
            provider="PAYSTACK",
            page=1,
            per_page=1,
        )

        assert total == 1
        assert len(results) == 1
        assert results[0].id == paystack.id
        assert results[0].provider == "paystack"

        results, total = list_integration_configs(
            clinic.id,
            provider="PAYSTACK",
            page=2,
            per_page=1,
        )

        assert total == 1
        assert results == []


def test_list_integration_configs_include_disabled_with_pagination(
    app,
):
    with app.app_context():
        clinic = _create_clinic(
            name="Disabled Pagination Clinic",
        )

        for provider in [
            "paystack",
            "flutterwave",
            "stripe",
        ]:
            _create_integration(
                clinic.id,
                provider=provider,
                enabled=True,
            )

        _create_integration(
            clinic.id,
            provider="email",
            enabled=False,
        )

        results, total = list_integration_configs(
            clinic.id,
            include_disabled=True,
            page=1,
            per_page=2,
        )

        assert total == 4
        assert len(results) == 2

        assert [
            integration.provider
            for integration in results
        ] == [
            "email",
            "flutterwave",
        ]


def test_list_integration_configs_enabled_filter_with_pagination(
    app,
):
    with app.app_context():
        clinic = _create_clinic(
            name="Enabled Pagination Clinic",
        )

        _create_integration(
            clinic.id,
            provider="email",
            enabled=False,
        )

        _create_integration(
            clinic.id,
            provider="flutterwave",
            enabled=True,
        )

        _create_integration(
            clinic.id,
            provider="paystack",
            enabled=True,
        )

        results, total = list_integration_configs(
            clinic.id,
            page=1,
            per_page=1,
        )

        assert total == 2
        assert len(results) == 1
        assert results[0].provider == "flutterwave"


def test_list_integration_configs_rejects_invalid_page(app):
    with app.app_context():
        clinic = _create_clinic(
            name="Invalid Page Clinic",
        )

        with pytest.raises(ValidationError):
            list_integration_configs(
                clinic.id,
                page=0,
            )


def test_list_integration_configs_rejects_invalid_per_page(app):
    with app.app_context():
        clinic = _create_clinic(
            name="Invalid Per Page Clinic",
        )

        with pytest.raises(ValidationError):
            list_integration_configs(
                clinic.id,
                per_page=0,
            )


def test_list_integration_configs_rejects_excessive_per_page(
    app,
):
    with app.app_context():
        clinic = _create_clinic(
            name="Excessive Per Page Clinic",
        )

        with pytest.raises(ValidationError):
            list_integration_configs(
                clinic.id,
                per_page=101,
            )


def test_list_integration_configs_accepts_maximum_per_page(
    app,
):
    with app.app_context():
        clinic = _create_clinic(
            name="Maximum Per Page Clinic",
        )

        for provider in [
            "paystack",
            "flutterwave",
            "stripe",
        ]:
            _create_integration(
                clinic.id,
                provider=provider,
                enabled=True,
            )

        results, total = list_integration_configs(
            clinic.id,
            per_page=100,
        )

        assert total == 3
        assert len(results) == 3


def test_update_integration_configuration(app):
    with app.app_context():
        clinic = _create_clinic(
            name="Update Clinic",
        )

        integration = _create_integration(
            clinic.id,
        )

        payload = IntegrationConfigUpdateSchema(
            configuration={
                "currency": "NGN",
                "environment": "live",
            },
        )

        updated = update_integration_config(
            clinic.id,
            "paystack",
            payload,
        )

        assert updated.id == integration.id
        assert updated.configuration["environment"] == "live"


def test_update_integration_enable_status(app):
    with app.app_context():
        clinic = _create_clinic(
            name="Status Update Clinic",
        )

        integration = _create_integration(
            clinic.id,
            enabled=False,
        )

        payload = IntegrationConfigUpdateSchema(
            is_enabled=True,
        )

        updated = update_integration_config(
            clinic.id,
            "paystack",
            payload,
        )

        assert updated.is_enabled is True


def test_update_integration_credentials_encrypts_new_credentials(
    app,
):
    with app.app_context():
        clinic = _create_clinic(
            name="Credential Update Clinic",
        )

        integration = _create_integration(
            clinic.id,
            credentials={
                "secret_key": "old-secret",
            },
        )

        old_version = integration.credentials_version

        payload = IntegrationConfigUpdateSchema(
            credentials={
                "secret_key": "new-secret",
            },
        )

        updated = update_integration_config(
            clinic.id,
            "paystack",
            payload,
        )

        assert updated.credentials_version == (
            old_version + 1
        )

        assert "new-secret" not in (
            updated.encrypted_credentials
        )

        decrypted = decrypt_credentials(
            updated.encrypted_credentials
        )

        assert decrypted == {
            "secret_key": "new-secret",
        }


def test_update_integration_rejects_empty_update(
    app,
):
    with app.app_context():
        clinic = _create_clinic(
            name="Empty Update Clinic",
        )

        _create_integration(
            clinic.id,
        )

        payload = IntegrationConfigUpdateSchema()

        with pytest.raises(ValidationError):
            update_integration_config(
                clinic.id,
                "paystack",
                payload,
            )


def test_update_integration_rejects_inactive_clinic(
    app,
):
    with app.app_context():
        clinic = _create_clinic(
            name="Inactive Update Clinic",
            status=ClinicStatus.INACTIVE,
        )

        payload = IntegrationConfigUpdateSchema(
            is_enabled=True,
        )

        with pytest.raises(ValidationError):
            update_integration_config(
                clinic.id,
                "paystack",
                payload,
            )


def test_rotate_integration_credentials(app):
    with app.app_context():
        clinic = _create_clinic(
            name="Rotation Clinic",
        )

        integration = _create_integration(
            clinic.id,
            credentials={
                "secret_key": "old-secret",
            },
        )

        old_version = integration.credentials_version
        old_rotation_time = integration.last_rotated_at

        rotated = rotate_integration_credentials(
            clinic.id,
            "paystack",
            {
                "secret_key": "rotated-secret",
                "public_key": "rotated-public",
            },
        )

        assert rotated.credentials_version == (
            old_version + 1
        )

        assert rotated.last_rotated_at is not None
        assert (
            rotated.last_rotated_at >= old_rotation_time
        )

        decrypted = decrypt_credentials(
            rotated.encrypted_credentials
        )

        assert decrypted == {
            "secret_key": "rotated-secret",
            "public_key": "rotated-public",
        }


def test_rotate_credentials_replaces_old_credentials(
    app,
):
    with app.app_context():
        clinic = _create_clinic(
            name="Credential Replacement Clinic",
        )

        _create_integration(
            clinic.id,
            credentials={
                "secret_key": "old-secret",
            },
        )

        rotate_integration_credentials(
            clinic.id,
            "paystack",
            {
                "secret_key": "new-secret",
            },
        )

        credentials = get_integration_credentials(
            clinic.id,
            "paystack",
        )

        assert credentials == {
            "secret_key": "new-secret",
        }


def test_enable_integration_config(app):
    with app.app_context():
        clinic = _create_clinic(
            name="Enable Clinic",
        )

        integration = _create_integration(
            clinic.id,
            enabled=False,
        )

        result = enable_integration_config(
            clinic.id,
            "paystack",
        )

        assert result.id == integration.id
        assert result.is_enabled is True


def test_enable_already_enabled_integration_is_idempotent(
    app,
):
    with app.app_context():
        clinic = _create_clinic(
            name="Idempotent Enable Clinic",
        )

        integration = _create_integration(
            clinic.id,
            enabled=True,
        )

        result = enable_integration_config(
            clinic.id,
            "paystack",
        )

        assert result.id == integration.id
        assert result.is_enabled is True


def test_disable_integration_config(app):
    with app.app_context():
        clinic = _create_clinic(
            name="Disable Clinic",
        )

        integration = _create_integration(
            clinic.id,
            enabled=True,
        )

        result = disable_integration_config(
            clinic.id,
            "paystack",
        )

        assert result.id == integration.id
        assert result.is_enabled is False


def test_disable_already_disabled_integration_is_idempotent(
    app,
):
    with app.app_context():
        clinic = _create_clinic(
            name="Idempotent Disable Clinic",
        )

        integration = _create_integration(
            clinic.id,
            enabled=False,
        )

        result = disable_integration_config(
            clinic.id,
            "paystack",
        )

        assert result.id == integration.id
        assert result.is_enabled is False


def test_delete_integration_config(app):
    with app.app_context():
        clinic = _create_clinic(
            name="Delete Clinic",
        )

        integration = _create_integration(
            clinic.id,
        )

        integration_id = integration.id

        delete_integration_config(
            clinic.id,
            "paystack",
        )

        db.session.expire_all()

        assert db.session.get(
            IntegrationConfig,
            integration_id,
        ) is None


def test_delete_integration_config_is_tenant_scoped(
    app,
):
    with app.app_context():
        clinic_one = _create_clinic(
            name="Delete Owner",
        )

        clinic_two = _create_clinic(
            name="Delete Attacker",
        )

        integration = _create_integration(
            clinic_one.id,
        )

        with pytest.raises(NotFoundError):
            delete_integration_config(
                clinic_two.id,
                "paystack",
            )

        db.session.expire_all()

        assert db.session.get(
            IntegrationConfig,
            integration.id,
        ) is not None


def test_get_integration_credentials_success(app):
    with app.app_context():
        clinic = _create_clinic(
            name="Credential Access Clinic",
        )

        credentials = {
            "secret_key": "internal-secret",
            "public_key": "internal-public",
        }

        _create_integration(
            clinic.id,
            credentials=credentials,
        )

        result = get_integration_credentials(
            clinic.id,
            "paystack",
        )

        assert result == credentials


def test_get_integration_credentials_missing_credentials(
    app,
):
    with app.app_context():
        clinic = _create_clinic(
            name="Missing Credentials Clinic",
        )

        integration = IntegrationConfig(
            clinic_id=clinic.id,
            provider="paystack",
            is_enabled=False,
            configuration={},
            encrypted_credentials=None,
            credentials_version=1,
        )

        db.session.add(integration)
        db.session.flush()

        with pytest.raises(ValidationError):
            get_integration_credentials(
                clinic.id,
                "paystack",
            )


def test_get_integration_credentials_is_tenant_scoped(
    app,
):
    with app.app_context():
        clinic_one = _create_clinic(
            name="Credential Owner",
        )

        clinic_two = _create_clinic(
            name="Credential Attacker",
        )

        _create_integration(
            clinic_one.id,
            credentials={
                "secret_key": "tenant-secret",
            },
        )

        with pytest.raises(NotFoundError):
            get_integration_credentials(
                clinic_two.id,
                "paystack",
            )