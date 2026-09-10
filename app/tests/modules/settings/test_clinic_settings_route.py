from __future__ import annotations

from cryptography.fernet import Fernet

from app.core.auth.user.models.user_model import User
from app.core.enums.clinic_enums import ClinicStatus
from app.core.enums.role_enums import Role
from app.extensions import db

from app.modules.settings.models.clinic_settings import ClinicSettings
from app.modules.settings.models.integration_config import IntegrationConfig


SETTINGS_URL = "/api/settings/clinic"
ENABLE_URL = "/api/settings/clinic/enable"
DISABLE_URL = "/api/settings/clinic/disable"
INITIALIZE_URL = "/api/settings/clinic/initialize"

INTEGRATIONS_URL = "/api/settings/integrations"


class TestClinicSettingsRoutes:
    def test_get_settings_success(
        self,
        client,
        clinic,
        clinic_settings,
        user,
        auth_headers_for,
    ):
        response = client.get(
            SETTINGS_URL,
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert data["data"]["id"] == clinic_settings.id
        assert data["data"]["clinic_id"] == clinic.id
        assert data["data"]["language"] == clinic_settings.language
        assert data["data"]["version"] == clinic_settings.version

    def test_get_settings_returns_not_found_when_settings_do_not_exist(
        self,
        client,
        clinic,
        user,
        auth_headers_for,
    ):
        response = client.get(
            SETTINGS_URL,
            headers=auth_headers_for(user),
        )

        assert response.status_code == 404

        data = response.get_json()

        assert data["success"] is False
        assert data["error"] == "Clinic settings not found"

    def test_create_settings_success(
        self,
        client,
        clinic,
        user,
        auth_headers_for,
    ):
        payload = {
            "language": "en",
            "date_format": "DD/MM/YYYY",
            "time_format": "12h",
            "notification_preferences": {
                "email": True,
                "sms": False,
            },
            "feature_flags": {
                "ai": True,
            },
            "operational_preferences": {
                "appointment_buffer": 15,
            },
            "security_preferences": {
                "session_timeout": 30,
            },
            "system_preferences": {
                "maintenance_mode": False,
            },
            "is_enabled": True,
        }

        response = client.post(
            SETTINGS_URL,
            json=payload,
            headers=auth_headers_for(user),
        )

        assert response.status_code == 201

        data = response.get_json()

        assert data["success"] is True
        assert data["message"] == (
            "Clinic settings created successfully"
        )

        settings_data = data["data"]

        assert settings_data["clinic_id"] == clinic.id
        assert settings_data["language"] == "en"
        assert settings_data["date_format"] == "DD/MM/YYYY"
        assert settings_data["time_format"] == "12h"
        assert settings_data["notification_preferences"] == {
            "email": True,
            "sms": False,
        }
        assert settings_data["feature_flags"] == {
            "ai": True,
        }
        assert settings_data["version"] == 1

        persisted = db.session.get(
            ClinicSettings,
            settings_data["id"],
        )

        assert persisted is not None
        assert persisted.clinic_id == clinic.id

    def test_create_settings_uses_defaults(
        self,
        client,
        clinic,
        user,
        auth_headers_for,
    ):
        response = client.post(
            SETTINGS_URL,
            json={},
            headers=auth_headers_for(user),
        )

        assert response.status_code == 201

        data = response.get_json()

        assert data["success"] is True
        assert data["data"]["clinic_id"] == clinic.id
        assert data["data"]["language"] == "en"
        assert data["data"]["date_format"] == "YYYY-MM-DD"
        assert data["data"]["time_format"] == "24h"
        assert data["data"]["notification_preferences"] == {}
        assert data["data"]["feature_flags"] == {}
        assert data["data"]["version"] == 1

    def test_create_settings_rejects_duplicate(
        self,
        client,
        clinic_settings,
        user,
        auth_headers_for,
    ):
        response = client.post(
            SETTINGS_URL,
            json={
                "language": "fr",
            },
            headers=auth_headers_for(user),
        )

        assert response.status_code == 409

        data = response.get_json()

        assert data["success"] is False
        assert data["error"] == "Clinic settings already exist"

    def test_create_settings_rejects_invalid_payload(
        self,
        client,
        user,
        auth_headers_for,
    ):
        response = client.post(
            SETTINGS_URL,
            json={
                "time_format": "invalid",
            },
            headers=auth_headers_for(user),
        )

        assert response.status_code == 422

        data = response.get_json()

        assert data["success"] is False
        assert data["error"] == "Validation failed"
        assert "details" in data
        assert data["details"]

    def test_create_settings_rejects_unknown_fields(
        self,
        client,
        user,
        auth_headers_for,
    ):
        response = client.post(
            SETTINGS_URL,
            json={
                "unknown_setting": True,
            },
            headers=auth_headers_for(user),
        )

        assert response.status_code == 422

        data = response.get_json()

        assert data["success"] is False
        assert data["error"] == "Validation failed"

    def test_create_settings_rejects_inactive_clinic(
        self,
        client,
        make_clinic,
        make_user,
        auth_headers_for,
    ):
        inactive_clinic = make_clinic(
            status=ClinicStatus.INACTIVE,
        )

        inactive_clinic_user = make_user(
            clinic=inactive_clinic,
            role=Role.ADMIN,
        )

        response = client.post(
            SETTINGS_URL,
            json={},
            headers=auth_headers_for(inactive_clinic_user),
        )

        assert response.status_code == 422

        data = response.get_json()

        assert data["success"] is False
        assert data["error"] == (
            "Clinic must be active to modify settings"
        )

    def test_update_settings_success(
        self,
        client,
        clinic_settings,
        user,
        auth_headers_for,
    ):
        response = client.patch(
            SETTINGS_URL,
            json={
                "language": "fr",
                "time_format": "12h",
            },
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert data["message"] == (
            "Clinic settings updated successfully"
        )
        assert data["data"]["clinic_id"] == clinic_settings.clinic_id
        assert data["data"]["language"] == "fr"
        assert data["data"]["time_format"] == "12h"
        assert data["data"]["version"] == 2

    def test_update_settings_with_expected_version(
        self,
        client,
        clinic_settings,
        user,
        auth_headers_for,
    ):
        response = client.patch(
            f"{SETTINGS_URL}?expected_version=1",
            json={
                "language": "fr",
            },
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert data["data"]["language"] == "fr"
        assert data["data"]["version"] == 2

    def test_update_settings_rejects_stale_version(
        self,
        client,
        clinic_settings,
        user,
        auth_headers_for,
    ):
        clinic_settings.version = 2
        db.session.flush()

        response = client.patch(
            f"{SETTINGS_URL}?expected_version=1",
            json={
                "language": "fr",
            },
            headers=auth_headers_for(user),
        )

        assert response.status_code == 409

        data = response.get_json()

        assert data["success"] is False
        assert data["error"] == (
            "Clinic settings were modified by another request"
        )

    def test_update_settings_rejects_invalid_expected_version(
        self,
        client,
        clinic_settings,
        user,
        auth_headers_for,
    ):
        response = client.patch(
            f"{SETTINGS_URL}?expected_version=0",
            json={
                "language": "fr",
            },
            headers=auth_headers_for(user),
        )

        assert response.status_code == 422

        data = response.get_json()

        assert data["success"] is False
        assert data["error"] == (
            "Expected version must be greater than or equal to 1"
        )

    def test_update_settings_rejects_empty_payload(
        self,
        client,
        clinic_settings,
        user,
        auth_headers_for,
    ):
        response = client.patch(
            SETTINGS_URL,
            json={},
            headers=auth_headers_for(user),
        )

        assert response.status_code == 422

        data = response.get_json()

        assert data["success"] is False
        assert data["error"] == (
            "At least one settings field must be provided"
        )

    def test_enable_settings_success(
        self,
        client,
        disabled_clinic_settings,
        user,
        auth_headers_for,
    ):
        response = client.post(
            ENABLE_URL,
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert data["message"] == (
            "Clinic settings enabled successfully"
        )
        assert data["data"]["is_enabled"] is True
        assert data["data"]["version"] == 2

    def test_enable_settings_is_idempotent(
        self,
        client,
        clinic_settings,
        user,
        auth_headers_for,
    ):
        original_version = clinic_settings.version

        response = client.post(
            ENABLE_URL,
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert data["data"]["is_enabled"] is True
        assert data["data"]["version"] == original_version

    def test_disable_settings_success(
        self,
        client,
        clinic_settings,
        user,
        auth_headers_for,
    ):
        response = client.post(
            DISABLE_URL,
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert data["message"] == (
            "Clinic settings disabled successfully"
        )
        assert data["data"]["is_enabled"] is False
        assert data["data"]["version"] == 2

    def test_disable_settings_is_idempotent(
        self,
        client,
        disabled_clinic_settings,
        user,
        auth_headers_for,
    ):
        original_version = disabled_clinic_settings.version

        response = client.post(
            DISABLE_URL,
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert data["data"]["is_enabled"] is False
        assert data["data"]["version"] == original_version

    def test_initialize_settings_creates_defaults(
        self,
        client,
        clinic,
        user,
        auth_headers_for,
    ):
        response = client.post(
            INITIALIZE_URL,
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert data["message"] == (
            "Clinic settings initialized successfully"
        )

        settings_data = data["data"]

        assert settings_data["clinic_id"] == clinic.id
        assert settings_data["language"] == "en"
        assert settings_data["date_format"] == "YYYY-MM-DD"
        assert settings_data["time_format"] == "24h"
        assert settings_data["version"] == 1

        settings = (
            db.session.query(ClinicSettings)
            .filter(
                ClinicSettings.clinic_id == clinic.id,
            )
            .first()
        )

        assert settings is not None

    def test_initialize_settings_returns_existing_settings(
        self,
        client,
        clinic_settings,
        user,
        auth_headers_for,
    ):
        response = client.post(
            INITIALIZE_URL,
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert data["data"]["id"] == clinic_settings.id
        assert data["data"]["clinic_id"] == clinic_settings.clinic_id
        assert data["data"]["version"] == clinic_settings.version
        assert data["data"]["language"] == clinic_settings.language


class TestClinicSettingsRouteRBAC:
    def test_view_role_can_get_settings(
        self,
        client,
        clinic,
        clinic_settings,
        make_user,
        auth_headers_for,
    ):
        viewer = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        response = client.get(
            SETTINGS_URL,
            headers=auth_headers_for(viewer),
        )

        assert response.status_code == 200

    def test_non_view_role_cannot_get_settings(
        self,
        client,
        clinic,
        clinic_settings,
        make_user,
        auth_headers_for,
    ):
        user = make_user(
            clinic=clinic,
            role=Role.PARAMEDIC,
        )

        response = client.get(
            SETTINGS_URL,
            headers=auth_headers_for(user),
        )

        assert response.status_code == 403

        data = response.get_json()

        assert data["error"] == "Insufficient permissions"

    def test_admin_can_create_settings(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.post(
            SETTINGS_URL,
            json={},
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 201

    def test_non_admin_cannot_create_settings(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        doctor = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        response = client.post(
            SETTINGS_URL,
            json={},
            headers=auth_headers_for(doctor),
        )

        assert response.status_code == 403

        data = response.get_json()

        assert data["error"] == "Insufficient permissions"

    def test_non_admin_cannot_update_settings(
        self,
        client,
        clinic,
        clinic_settings,
        make_user,
        auth_headers_for,
    ):
        doctor = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        response = client.patch(
            SETTINGS_URL,
            json={
                "language": "fr",
            },
            headers=auth_headers_for(doctor),
        )

        assert response.status_code == 403

    def test_non_admin_cannot_enable_settings(
        self,
        client,
        clinic,
        clinic_settings,
        make_user,
        auth_headers_for,
    ):
        doctor = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        response = client.post(
            ENABLE_URL,
            headers=auth_headers_for(doctor),
        )

        assert response.status_code == 403

    def test_non_admin_cannot_disable_settings(
        self,
        client,
        clinic,
        clinic_settings,
        make_user,
        auth_headers_for,
    ):
        doctor = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        response = client.post(
            DISABLE_URL,
            headers=auth_headers_for(doctor),
        )

        assert response.status_code == 403

    def test_non_admin_cannot_initialize_settings(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        doctor = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        response = client.post(
            INITIALIZE_URL,
            headers=auth_headers_for(doctor),
        )

        assert response.status_code == 403


class TestClinicSettingsRouteSecurity:
    def test_settings_requires_authentication(
        self,
        client,
    ):
        response = client.get(
            SETTINGS_URL,
        )

        assert response.status_code == 401

    def test_create_settings_requires_authentication(
        self,
        client,
    ):
        response = client.post(
            SETTINGS_URL,
            json={},
        )

        assert response.status_code == 401

    def test_settings_are_scoped_to_authenticated_users_clinic(
        self,
        client,
        make_clinic,
        make_user,
        make_clinic_settings,
        auth_headers_for,
    ):
        clinic_one = make_clinic(
            name="Clinic One",
        )
        clinic_two = make_clinic(
            name="Clinic Two",
        )

        user_one = make_user(
            clinic=clinic_one,
            role=Role.ADMIN,
        )

        settings_two = make_clinic_settings(
            clinic_two,
            language="fr",
        )

        response = client.get(
            SETTINGS_URL,
            headers=auth_headers_for(user_one),
        )

        assert response.status_code == 404

        data = response.get_json()

        assert data["success"] is False
        assert data["error"] == "Clinic settings not found"

        assert data.get("data") is None
        assert settings_two.clinic_id == clinic_two.id

    def test_inactive_user_cannot_access_settings(
        self,
        client,
        clinic,
        clinic_settings,
        make_user,
        auth_headers_for,
    ):
        inactive_user = make_user(
            clinic=clinic,
            role=Role.ADMIN,
            is_active=False,
        )

        response = client.get(
            SETTINGS_URL,
            headers=auth_headers_for(inactive_user),
        )

        assert response.status_code == 422

        data = response.get_json()

        assert data["success"] is False
        assert data["error"] == "User account is inactive"

    def test_client_cannot_choose_another_clinic(
        self,
        client,
        clinic,
        make_clinic,
        make_user,
        auth_headers_for,
    ):
        other_clinic = make_clinic(
            name="Other Clinic",
        )

        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.post(
            f"{SETTINGS_URL}?clinic_id={other_clinic.id}",
            json={
                "language": "fr",
            },
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 201

        data = response.get_json()

        assert data["data"]["clinic_id"] == clinic.id
        assert data["data"]["clinic_id"] != other_clinic.id


class TestIntegrationConfigRoutes:
    def _create_integration(
        self,
        clinic,
        provider: str,
        enabled: bool = True,
        credentials: dict | None = None,
        configuration: dict | None = None,
    ) -> IntegrationConfig:
        integration = IntegrationConfig(
            clinic_id=clinic.id,
            provider=provider,
            is_enabled=enabled,
            configuration=configuration or {
                "environment": "test",
                "currency": "NGN",
            },
            encrypted_credentials="test-encrypted-value",
            credentials_version=1,
        )

        db.session.add(integration)
        db.session.flush()

        return integration

    def test_list_integrations_success(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        self._create_integration(
            clinic,
            "paystack",
        )

        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.get(
            INTEGRATIONS_URL,
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert len(data["data"]) == 1

        integration = data["data"][0]

        assert integration["clinic_id"] == clinic.id
        assert integration["provider"] == "paystack"
        assert integration["is_enabled"] is True

        assert "encrypted_credentials" not in integration
        assert "credentials" not in integration

    def test_list_integrations_returns_pagination_metadata(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        for provider in [
            "paystack",
            "flutterwave",
            "stripe",
        ]:
            self._create_integration(
                clinic,
                provider,
            )

        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.get(
            f"{INTEGRATIONS_URL}?page=1&per_page=2",
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert len(data["data"]) == 2

        pagination = data["pagination"]

        assert pagination["page"] == 1
        assert pagination["per_page"] == 2
        assert pagination["total"] == 3
        assert pagination["pages"] == 2
        assert pagination["has_next"] is True
        assert pagination["has_previous"] is False

    def test_list_integrations_pagination_second_page(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        for provider in [
            "paystack",
            "flutterwave",
            "stripe",
        ]:
            self._create_integration(
                clinic,
                provider,
            )

        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.get(
            f"{INTEGRATIONS_URL}?page=2&per_page=2",
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert len(data["data"]) == 1

        pagination = data["pagination"]

        assert pagination["page"] == 2
        assert pagination["per_page"] == 2
        assert pagination["total"] == 3
        assert pagination["pages"] == 2
        assert pagination["has_next"] is False
        assert pagination["has_previous"] is True

    def test_list_integrations_out_of_range_page_returns_empty(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        self._create_integration(
            clinic,
            "paystack",
        )

        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.get(
            f"{INTEGRATIONS_URL}?page=2&per_page=1",
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert data["data"] == []

        pagination = data["pagination"]

        assert pagination["page"] == 2
        assert pagination["per_page"] == 1
        assert pagination["total"] == 1
        assert pagination["pages"] == 1
        assert pagination["has_next"] is False
        assert pagination["has_previous"] is True

    def test_list_integrations_empty_returns_zero_pages(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.get(
            INTEGRATIONS_URL,
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert data["data"] == []

        pagination = data["pagination"]

        assert pagination["page"] == 1
        assert pagination["per_page"] == 20
        assert pagination["total"] == 0
        assert pagination["pages"] == 0
        assert pagination["has_next"] is False
        assert pagination["has_previous"] is False

    def test_list_integrations_provider_filter(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        self._create_integration(
            clinic,
            "paystack",
        )

        self._create_integration(
            clinic,
            "stripe",
        )

        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.get(
            f"{INTEGRATIONS_URL}?provider=PAYSTACK",
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert len(data["data"]) == 1
        assert data["data"][0]["provider"] == "paystack"
        assert data["pagination"]["total"] == 1

    def test_list_integrations_provider_filter_with_pagination(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        self._create_integration(
            clinic,
            "paystack",
        )

        self._create_integration(
            clinic,
            "stripe",
        )

        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.get(
            f"{INTEGRATIONS_URL}"
            "?provider=PAYSTACK&page=1&per_page=1",
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert len(data["data"]) == 1
        assert data["data"][0]["provider"] == "paystack"

        pagination = data["pagination"]

        assert pagination["page"] == 1
        assert pagination["per_page"] == 1
        assert pagination["total"] == 1
        assert pagination["pages"] == 1
        assert pagination["has_next"] is False
        assert pagination["has_previous"] is False

        response = client.get(
            f"{INTEGRATIONS_URL}"
            "?provider=PAYSTACK&page=2&per_page=1",
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert data["data"] == []

    def test_list_integrations_include_disabled(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        self._create_integration(
            clinic,
            "paystack",
            enabled=True,
        )

        self._create_integration(
            clinic,
            "stripe",
            enabled=False,
        )

        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.get(
            INTEGRATIONS_URL,
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert len(data["data"]) == 1
        assert data["data"][0]["provider"] == "paystack"

        response = client.get(
            f"{INTEGRATIONS_URL}?include_disabled=true",
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert len(data["data"]) == 2
        assert data["pagination"]["total"] == 2

    def test_list_integrations_rejects_invalid_page(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.get(
            f"{INTEGRATIONS_URL}?page=0",
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 422

        data = response.get_json()

        assert data["success"] is False
        assert data["error"] == "Validation failed"
        assert data["details"]

    def test_list_integrations_rejects_invalid_per_page(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.get(
            f"{INTEGRATIONS_URL}?per_page=0",
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 422

        data = response.get_json()

        assert data["success"] is False
        assert data["error"] == "Validation failed"
        assert data["details"]

    def test_list_integrations_rejects_per_page_above_maximum(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.get(
            f"{INTEGRATIONS_URL}?per_page=101",
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 422

        data = response.get_json()

        assert data["success"] is False
        assert data["error"] == "Validation failed"
        assert data["details"]

    def test_list_integrations_rejects_invalid_provider(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.get(
            f"{INTEGRATIONS_URL}?provider=unknown",
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 422

        data = response.get_json()

        assert data["success"] is False
        assert data["error"] == "Validation failed"
        assert data["details"]

    def test_list_integrations_scoped_to_authenticated_clinic(
        self,
        client,
        make_clinic,
        make_user,
        auth_headers_for,
    ):
        clinic_one = make_clinic(
            name="Clinic One",
        )

        clinic_two = make_clinic(
            name="Clinic Two",
        )

        self._create_integration(
            clinic_two,
            "paystack",
        )

        user_one = make_user(
            clinic=clinic_one,
            role=Role.ADMIN,
        )

        response = client.get(
            INTEGRATIONS_URL,
            headers=auth_headers_for(user_one),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert data["data"] == []
        assert data["pagination"]["total"] == 0

    def test_create_integration_success(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        payload = {
            "provider": "paystack",
            "configuration": {
                "environment": "test",
                "currency": "NGN",
            },
            "credentials": {
                "secret_key": "sk_test_example",
                "public_key": "pk_test_example",
            },
            "is_enabled": True,
        }

        response = client.post(
            INTEGRATIONS_URL,
            json=payload,
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 201

        data = response.get_json()

        assert data["success"] is True
        assert data["message"] == (
            "Integration configuration created successfully"
        )

        integration = data["data"]

        assert integration["clinic_id"] == clinic.id
        assert integration["provider"] == "paystack"
        assert integration["is_enabled"] is True

        assert "credentials" not in integration
        assert "encrypted_credentials" not in integration

        persisted = (
            db.session.query(IntegrationConfig)
            .filter(
                IntegrationConfig.clinic_id == clinic.id,
                IntegrationConfig.provider == "paystack",
            )
            .first()
        )

        assert persisted is not None
        assert persisted.encrypted_credentials is not None
        assert persisted.encrypted_credentials != (
            "sk_test_example"
        )

    def test_create_integration_rejects_duplicate_provider(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        self._create_integration(
            clinic,
            "paystack",
        )

        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.post(
            INTEGRATIONS_URL,
            json={
                "provider": "paystack",
                "credentials": {
                    "secret_key": "new-secret",
                },
            },
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 409

        data = response.get_json()

        assert data["success"] is False
        assert data["error"] == (
            "Integration configuration already exists"
        )

    def test_create_integration_rejects_invalid_payload(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.post(
            INTEGRATIONS_URL,
            json={
                "provider": "unknown",
                "credentials": {
                    "secret_key": "secret",
                },
            },
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 422

        data = response.get_json()

        assert data["success"] is False
        assert data["error"] == "Validation failed"
        assert data["details"]

    def test_get_integration_by_provider_success(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        self._create_integration(
            clinic,
            "paystack",
        )

        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.get(
            f"{INTEGRATIONS_URL}/paystack",
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert data["data"]["provider"] == "paystack"
        assert data["data"]["clinic_id"] == clinic.id
        assert "credentials" not in data["data"]
        assert "encrypted_credentials" not in data["data"]

    def test_get_integration_by_id_success(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        integration = self._create_integration(
            clinic,
            "paystack",
        )

        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.get(
            f"{INTEGRATIONS_URL}/id/{integration.id}",
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert data["data"]["id"] == integration.id
        assert data["data"]["clinic_id"] == clinic.id
        assert data["data"]["provider"] == "paystack"

    def test_get_integration_by_id_prevents_cross_clinic_access(
        self,
        client,
        make_clinic,
        make_user,
        auth_headers_for,
    ):
        clinic_one = make_clinic(
            name="Clinic One",
        )

        clinic_two = make_clinic(
            name="Clinic Two",
        )

        integration_two = self._create_integration(
            clinic_two,
            "paystack",
        )

        user_one = make_user(
            clinic=clinic_one,
            role=Role.ADMIN,
        )

        response = client.get(
            f"{INTEGRATIONS_URL}/id/{integration_two.id}",
            headers=auth_headers_for(user_one),
        )

        assert response.status_code == 404

        data = response.get_json()

        assert data["success"] is False
        assert data["error"] == "Integration configuration not found"

    def test_update_integration_success(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        self._create_integration(
            clinic,
            "paystack",
        )

        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.patch(
            f"{INTEGRATIONS_URL}/paystack",
            json={
                "configuration": {
                    "environment": "live",
                    "currency": "NGN",
                },
                "is_enabled": True,
            },
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert data["data"]["provider"] == "paystack"
        assert data["data"]["configuration"]["environment"] == "live"

    def test_update_integration_credentials_are_not_returned(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        self._create_integration(
            clinic,
            "paystack",
        )

        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.patch(
            f"{INTEGRATIONS_URL}/paystack",
            json={
                "credentials": {
                    "secret_key": "new-secret",
                },
            },
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert "credentials" not in data["data"]
        assert "encrypted_credentials" not in data["data"]

    def test_enable_integration_success(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        self._create_integration(
            clinic,
            "paystack",
            enabled=False,
        )

        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.post(
            f"{INTEGRATIONS_URL}/paystack/enable",
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert data["data"]["is_enabled"] is True

    def test_disable_integration_success(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        self._create_integration(
            clinic,
            "paystack",
            enabled=True,
        )

        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.post(
            f"{INTEGRATIONS_URL}/paystack/disable",
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert data["data"]["is_enabled"] is False

    def test_rotate_integration_credentials_success(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        integration = self._create_integration(
            clinic,
            "paystack",
        )

        original_version = integration.credentials_version
        original_ciphertext = integration.encrypted_credentials

        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.post(
            f"{INTEGRATIONS_URL}/paystack/rotate",
            json={
                "credentials": {
                    "secret_key": "rotated-secret",
                },
            },
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert data["message"] == (
            "Integration credentials rotated successfully"
        )

        assert "credentials" not in data["data"]
        assert "encrypted_credentials" not in data["data"]

        db.session.refresh(integration)

        assert integration.credentials_version == (
            original_version + 1
        )
        assert integration.encrypted_credentials != (
            original_ciphertext
        )
        assert integration.last_rotated_at is not None

    def test_rotate_integration_rejects_missing_credentials(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        self._create_integration(
            clinic,
            "paystack",
        )

        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.post(
            f"{INTEGRATIONS_URL}/paystack/rotate",
            json={},
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 422

        data = response.get_json()

        assert data["success"] is False
        assert data["error"] == "Credentials are required"

    def test_delete_integration_success(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        self._create_integration(
            clinic,
            "paystack",
        )

        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.delete(
            f"{INTEGRATIONS_URL}/paystack",
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["success"] is True
        assert data["message"] == (
            "Integration configuration deleted successfully"
        )

        integration = (
            db.session.query(IntegrationConfig)
            .filter(
                IntegrationConfig.clinic_id == clinic.id,
                IntegrationConfig.provider == "paystack",
            )
            .first()
        )

        assert integration is None


class TestIntegrationConfigRouteRBAC:
    def test_view_role_can_list_integrations(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        self._create_integration_for_test(clinic)

        doctor = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        response = client.get(
            INTEGRATIONS_URL,
            headers=auth_headers_for(doctor),
        )

        assert response.status_code == 200

    def test_non_view_role_cannot_list_integrations(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        user = make_user(
            clinic=clinic,
            role=Role.PARAMEDIC,
        )

        response = client.get(
            INTEGRATIONS_URL,
            headers=auth_headers_for(user),
        )

        assert response.status_code == 403

        data = response.get_json()

        assert data["error"] == "Insufficient permissions"

    def test_admin_can_create_integration(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        admin = make_user(
            clinic=clinic,
            role=Role.ADMIN,
        )

        response = client.post(
            INTEGRATIONS_URL,
            json={
                "provider": "paystack",
                "credentials": {
                    "secret_key": "secret",
                },
            },
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 201

    def test_non_admin_cannot_create_integration(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        doctor = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        response = client.post(
            INTEGRATIONS_URL,
            json={
                "provider": "paystack",
                "credentials": {
                    "secret_key": "secret",
                },
            },
            headers=auth_headers_for(doctor),
        )

        assert response.status_code == 403

    def test_non_admin_cannot_update_integration(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        doctor = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        response = client.patch(
            f"{INTEGRATIONS_URL}/paystack",
            json={
                "is_enabled": False,
            },
            headers=auth_headers_for(doctor),
        )

        assert response.status_code == 403

    def test_non_admin_cannot_enable_integration(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        doctor = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        response = client.post(
            f"{INTEGRATIONS_URL}/paystack/enable",
            headers=auth_headers_for(doctor),
        )

        assert response.status_code == 403

    def test_non_admin_cannot_disable_integration(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        doctor = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        response = client.post(
            f"{INTEGRATIONS_URL}/paystack/disable",
            headers=auth_headers_for(doctor),
        )

        assert response.status_code == 403

    def test_non_admin_cannot_rotate_integration(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        doctor = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        response = client.post(
            f"{INTEGRATIONS_URL}/paystack/rotate",
            json={
                "credentials": {
                    "secret_key": "secret",
                },
            },
            headers=auth_headers_for(doctor),
        )

        assert response.status_code == 403

    def test_non_admin_cannot_delete_integration(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        doctor = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        response = client.delete(
            f"{INTEGRATIONS_URL}/paystack",
            headers=auth_headers_for(doctor),
        )

        assert response.status_code == 403

    @staticmethod
    def _create_integration_for_test(
        clinic,
    ):
        integration = IntegrationConfig(
            clinic_id=clinic.id,
            provider="paystack",
            is_enabled=True,
            configuration={},
            encrypted_credentials="test-encrypted",
            credentials_version=1,
        )

        db.session.add(integration)
        db.session.flush()

        return integration


class TestIntegrationConfigRouteSecurity:
    def test_list_integrations_requires_authentication(
        self,
        client,
    ):
        response = client.get(
            INTEGRATIONS_URL,
        )

        assert response.status_code == 401

    def test_create_integration_requires_authentication(
        self,
        client,
    ):
        response = client.post(
            INTEGRATIONS_URL,
            json={
                "provider": "paystack",
                "credentials": {
                    "secret_key": "secret",
                },
            },
        )

        assert response.status_code == 401

    def test_get_integration_requires_authentication(
        self,
        client,
    ):
        response = client.get(
            f"{INTEGRATIONS_URL}/paystack",
        )

        assert response.status_code == 401

    def test_update_integration_requires_authentication(
        self,
        client,
    ):
        response = client.patch(
            f"{INTEGRATIONS_URL}/paystack",
            json={
                "is_enabled": False,
            },
        )

        assert response.status_code == 401

    def test_delete_integration_requires_authentication(
        self,
        client,
    ):
        response = client.delete(
            f"{INTEGRATIONS_URL}/paystack",
        )

        assert response.status_code == 401

    def test_integration_routes_are_scoped_to_authenticated_clinic(
        self,
        client,
        make_clinic,
        make_user,
        auth_headers_for,
    ):
        clinic_one = make_clinic(
            name="Clinic One",
        )

        clinic_two = make_clinic(
            name="Clinic Two",
        )

        integration_two = IntegrationConfig(
            clinic_id=clinic_two.id,
            provider="paystack",
            is_enabled=True,
            configuration={},
            encrypted_credentials="test-encrypted",
            credentials_version=1,
        )

        db.session.add(integration_two)
        db.session.flush()

        user_one = make_user(
            clinic=clinic_one,
            role=Role.ADMIN,
        )

        response = client.get(
            f"{INTEGRATIONS_URL}/paystack",
            headers=auth_headers_for(user_one),
        )

        assert response.status_code == 404

        data = response.get_json()

        assert data["success"] is False
        assert data["error"] == "Integration configuration not found"

        response = client.get(
            f"{INTEGRATIONS_URL}/id/{integration_two.id}",
            headers=auth_headers_for(user_one),
        )

        assert response.status_code == 404

        data = response.get_json()

        assert data["success"] is False
        assert data["error"] == "Integration configuration not found"

    def test_client_cannot_choose_another_clinic_for_integration(
        self,
        client,
        make_clinic,
        make_user,
        auth_headers_for,
    ):
        clinic_one = make_clinic(
            name="Clinic One",
        )

        clinic_two = make_clinic(
            name="Clinic Two",
        )

        admin = make_user(
            clinic=clinic_one,
            role=Role.ADMIN,
        )

        response = client.post(
            f"{INTEGRATIONS_URL}?clinic_id={clinic_two.id}",
            json={
                "provider": "paystack",
                "credentials": {
                    "secret_key": "secret",
                },
            },
            headers=auth_headers_for(admin),
        )

        assert response.status_code == 201

        data = response.get_json()

        assert data["data"]["clinic_id"] == clinic_one.id
        assert data["data"]["clinic_id"] != clinic_two.id

    def test_inactive_user_cannot_access_integrations(
        self,
        client,
        clinic,
        make_user,
        auth_headers_for,
    ):
        inactive_user = make_user(
            clinic=clinic,
            role=Role.ADMIN,
            is_active=False,
        )

        response = client.get(
            INTEGRATIONS_URL,
            headers=auth_headers_for(inactive_user),
        )

        assert response.status_code == 422

        data = response.get_json()

        assert data["success"] is False
        assert data["error"] == "User account is inactive"