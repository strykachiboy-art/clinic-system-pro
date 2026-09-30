from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from app.core.enums.clinical_safety_enums import (
    ClinicalAlertStatus,
    ClinicalRuleAction,
    ClinicalRuleScope,
    ClinicalRuleSeverity,
    ClinicalRuleType,
)
from app.core.enums.role_enums import Role


TEST_TIMESTAMP = datetime.now(timezone.utc)


BASE_RULE_PAYLOAD = {
    "rule_code": "ROUTE_TEST_RULE",
    "name": "Route Test Rule",
    "description": "Route test rule",
    "scope": "clinic",
    "rule_type": "drug_interaction",
    "severity": "high",
    "action": "alert",
    "conditions": {},
    "configuration": {
        "drug_a_id": 1,
        "drug_b_id": 2,
        "minimum_severity": "moderate",
    },
    "priority": 100,
    "enabled": True,
}


class TestClinicalSafetyRuleRoutes:
    def test_create_rule_forwards_authenticated_context(
        self,
        client,
        auth_headers_for,
        clinical_safety_admin,
        clinic,
        monkeypatch,
    ):
        rule = SimpleNamespace(
            id=10,
            clinic_id=clinic.id,
            rule_code="ROUTE_TEST_RULE",
            name="Route Test Rule",
            description="Route test rule",
            scope=ClinicalRuleScope.CLINIC,
            rule_type=ClinicalRuleType.DRUG_INTERACTION,
            severity=ClinicalRuleSeverity.HIGH,
            action=ClinicalRuleAction.ALERT,
            conditions={},
            configuration={
                "drug_a_id": 1,
                "drug_b_id": 2,
                "minimum_severity": "moderate",
            },
            department_code=None,
            priority=100,
            enabled=True,
            is_hard_rule=False,
            version=1,
            effective_from=TEST_TIMESTAMP,
            effective_until=None,
            created_at=TEST_TIMESTAMP,
            updated_at=TEST_TIMESTAMP,
        )

        create_mock = Mock(return_value=rule)

        monkeypatch.setattr(
            "app.core.clinical_safety.routes.clinical_safety_routes.create_clinical_rule",
            create_mock,
        )

        response = client.post(
            "/api/v1/clinical-safety/rules",
            json=BASE_RULE_PAYLOAD,
            headers=auth_headers_for(
                clinical_safety_admin,
                role=Role.ADMIN,
            ),
        )

        assert response.status_code == 201

        create_mock.assert_called_once()

        call = create_mock.call_args.kwargs

        assert call["actor_user_id"] == clinical_safety_admin.id
        assert call["clinic_id"] == clinic.id
        assert call["is_hard_rule"] is False
        assert call["data"].rule_code == "ROUTE_TEST_RULE"

    def test_create_global_rule_requires_super_admin(
        self,
        client,
        auth_headers_for,
        clinical_safety_admin,
    ):
        payload = {
            **BASE_RULE_PAYLOAD,
            "rule_code": "GLOBAL_ROUTE_RULE",
            "scope": "global",
        }

        response = client.post(
            "/api/v1/clinical-safety/rules",
            json=payload,
            headers=auth_headers_for(
                clinical_safety_admin,
                role=Role.ADMIN,
            ),
        )

        assert response.status_code == 422

    def test_super_admin_can_create_global_rule(
        self,
        client,
        auth_headers_for,
        clinical_safety_super_admin,
        monkeypatch,
    ):
        rule = SimpleNamespace(
            id=11,
            clinic_id=None,
            rule_code="GLOBAL_ROUTE_RULE",
            name="Global Route Rule",
            description=None,
            scope=ClinicalRuleScope.GLOBAL,
            rule_type=ClinicalRuleType.DRUG_INTERACTION,
            severity=ClinicalRuleSeverity.CRITICAL,
            action=ClinicalRuleAction.BLOCK,
            conditions={},
            configuration={
                "drug_a_id": 1,
                "drug_b_id": 2,
                "minimum_severity": "moderate",
            },
            department_code=None,
            priority=100,
            enabled=True,
            is_hard_rule=False,
            version=1,
            effective_from=TEST_TIMESTAMP,
            effective_until=None,
            created_at=TEST_TIMESTAMP,
            updated_at=TEST_TIMESTAMP,
        )

        create_mock = Mock(return_value=rule)

        monkeypatch.setattr(
            "app.core.clinical_safety.routes.clinical_safety_routes.create_clinical_rule",
            create_mock,
        )

        payload = {
            **BASE_RULE_PAYLOAD,
            "rule_code": "GLOBAL_ROUTE_RULE",
            "scope": "global",
            "severity": "critical",
            "action": "block",
        }

        response = client.post(
            "/api/v1/clinical-safety/rules",
            json=payload,
            headers=auth_headers_for(
                clinical_safety_super_admin,
                role=Role.SUPER_ADMIN,
            ),
        )

        assert response.status_code == 201

        call = create_mock.call_args.kwargs

        assert call["actor_user_id"] == clinical_safety_super_admin.id
        assert call["clinic_id"] is None
        assert call["is_hard_rule"] is False

    def test_list_rules_forwards_authenticated_user(
        self,
        client,
        auth_headers_for,
        clinical_safety_admin,
        clinic,
        monkeypatch,
    ):
        rule = SimpleNamespace(
            id=1,
            clinic_id=clinic.id,
            rule_code="ROUTE_TEST_RULE",
            name="Route Test Rule",
            description=None,
            scope=ClinicalRuleScope.CLINIC,
            rule_type=ClinicalRuleType.DRUG_INTERACTION,
            severity=ClinicalRuleSeverity.HIGH,
            action=ClinicalRuleAction.ALERT,
            conditions={},
            configuration={
                "drug_a_id": 1,
                "drug_b_id": 2,
                "minimum_severity": "moderate",
            },
            department_code=None,
            priority=100,
            enabled=True,
            is_hard_rule=False,
            version=1,
            effective_from=TEST_TIMESTAMP,
            effective_until=None,
            created_at=TEST_TIMESTAMP,
            updated_at=TEST_TIMESTAMP,
        )

        list_mock = Mock(
            return_value={
                "items": [rule],
                "total": 1,
                "page": 1,
                "per_page": 50,
            }
        )

        monkeypatch.setattr(
            "app.core.clinical_safety.routes.clinical_safety_routes.list_clinical_rules",
            list_mock,
        )

        response = client.get(
            "/api/v1/clinical-safety/rules",
            headers=auth_headers_for(
                clinical_safety_admin,
                role=Role.ADMIN,
            ),
        )

        assert response.status_code == 200
        assert response.get_json()["total"] == 1
        assert len(response.get_json()["items"]) == 1

    def test_non_management_role_is_forbidden(
        self,
        client,
        auth_headers_for,
        make_user,
        clinic,
    ):
        doctor = make_user(
            clinic,
            role=Role.DOCTOR,
            email="clinical.safety.route.doctor@test.com",
        )

        response = client.post(
            "/api/v1/clinical-safety/rules",
            json=BASE_RULE_PAYLOAD,
            headers=auth_headers_for(
                doctor,
                role=Role.DOCTOR,
            ),
        )

        assert response.status_code == 403

    def test_get_rule_forwards_rule_id_and_actor(
        self,
        client,
        auth_headers_for,
        clinical_safety_admin,
        clinical_rule,
        monkeypatch,
    ):
        get_mock = Mock(return_value=clinical_rule)

        monkeypatch.setattr(
            "app.core.clinical_safety.routes.clinical_safety_routes.get_clinical_rule",
            get_mock,
        )

        response = client.get(
            f"/api/v1/clinical-safety/rules/{clinical_rule.id}",
            headers=auth_headers_for(
                clinical_safety_admin,
                role=Role.ADMIN,
            ),
        )

        assert response.status_code == 200
        assert (
            response.get_json()["rule"]["id"]
            == clinical_rule.id
        )

        call = get_mock.call_args.kwargs

        assert call["rule_id"] == clinical_rule.id
        assert call["actor_user_id"] == clinical_safety_admin.id

    def test_update_rule_forwards_authenticated_context(
        self,
        client,
        auth_headers_for,
        clinical_safety_admin,
        clinical_rule,
        monkeypatch,
    ):
        updated = SimpleNamespace(
            **{
                **clinical_rule.__dict__,
                "id": clinical_rule.id + 1,
                "version": 2,
                "name": "Updated Route Rule",
                "effective_from": TEST_TIMESTAMP,
                "effective_until": None,
                "created_at": TEST_TIMESTAMP,
                "updated_at": TEST_TIMESTAMP,
            }
        )

        update_mock = Mock(return_value=updated)

        monkeypatch.setattr(
            "app.core.clinical_safety.routes.clinical_safety_routes.update_clinical_rule",
            update_mock,
        )

        response = client.patch(
            f"/api/v1/clinical-safety/rules/{clinical_rule.id}",
            json={
                "name": "Updated Route Rule",
                "effective_from": TEST_TIMESTAMP.isoformat(),
            },
            headers=auth_headers_for(
                clinical_safety_admin,
                role=Role.ADMIN,
            ),
        )

        assert response.status_code == 200

        call = update_mock.call_args.kwargs

        assert call["rule_id"] == clinical_rule.id
        assert call["actor_user_id"] == clinical_safety_admin.id

    def test_disable_rule_forwards_authenticated_context(
        self,
        client,
        auth_headers_for,
        clinical_safety_admin,
        clinical_rule,
        monkeypatch,
    ):
        disabled = SimpleNamespace(
            **{
                **clinical_rule.__dict__,
                "id": clinical_rule.id + 1,
                "version": 2,
                "enabled": False,
                "effective_from": TEST_TIMESTAMP,
                "effective_until": None,
                "created_at": TEST_TIMESTAMP,
                "updated_at": TEST_TIMESTAMP,
            }
        )

        disable_mock = Mock(return_value=disabled)

        monkeypatch.setattr(
            "app.core.clinical_safety.routes.clinical_safety_routes.disable_clinical_rule",
            disable_mock,
        )

        response = client.post(
            f"/api/v1/clinical-safety/rules/{clinical_rule.id}/disable",
            headers=auth_headers_for(
                clinical_safety_admin,
                role=Role.ADMIN,
            ),
        )

        assert response.status_code == 200

        call = disable_mock.call_args.kwargs

        assert call["rule_id"] == clinical_rule.id
        assert call["actor_user_id"] == clinical_safety_admin.id


class TestClinicalSafetyAlertRoutes:
    def test_list_alerts_is_clinic_scoped(
        self,
        client,
        auth_headers_for,
        clinical_safety_admin,
        clinic,
        monkeypatch,
    ):
        alert = SimpleNamespace(
            id=1,
            clinic_id=clinic.id,
            patient_id=1,
            rule_id=1,
            rule_version=1,
            severity=ClinicalRuleSeverity.HIGH,
            action=ClinicalRuleAction.ALERT,
            status=ClinicalAlertStatus.OPEN,
            title="Test Alert",
            message="Test clinical safety alert",
            context={},
            source_type="prescription",
            source_id=10,
            deduplication_key="test-key",
            generated_at=TEST_TIMESTAMP,
            resolved_at=None,
            created_at=TEST_TIMESTAMP,
            updated_at=TEST_TIMESTAMP,
        )

        list_mock = Mock(
            return_value={
                "items": [alert],
                "total": 1,
                "page": 1,
                "per_page": 50,
            }
        )

        monkeypatch.setattr(
            "app.core.clinical_safety.routes.clinical_safety_routes.list_clinical_alerts",
            list_mock,
        )

        response = client.get(
            "/api/v1/clinical-safety/alerts",
            headers=auth_headers_for(
                clinical_safety_admin,
                role=Role.ADMIN,
            ),
        )

        assert response.status_code == 200

        call = list_mock.call_args.kwargs

        assert call["clinic_id"] == clinic.id

    def test_get_alert_forwards_current_clinic(
        self,
        client,
        auth_headers_for,
        clinical_safety_admin,
        clinic,
        monkeypatch,
    ):
        alert = SimpleNamespace(
            id=1,
            clinic_id=clinic.id,
            patient_id=1,
            rule_id=1,
            rule_version=1,
            severity=ClinicalRuleSeverity.HIGH,
            action=ClinicalRuleAction.ALERT,
            status=ClinicalAlertStatus.OPEN,
            title="Test Alert",
            message="Test clinical safety alert",
            context={},
            source_type="prescription",
            source_id=10,
            deduplication_key="test-key",
            generated_at=TEST_TIMESTAMP,
            resolved_at=None,
            created_at=TEST_TIMESTAMP,
            updated_at=TEST_TIMESTAMP,
        )

        get_mock = Mock(return_value=alert)

        monkeypatch.setattr(
            "app.core.clinical_safety.routes.clinical_safety_routes.get_clinical_alert",
            get_mock,
        )

        response = client.get(
            "/api/v1/clinical-safety/alerts/1",
            headers=auth_headers_for(
                clinical_safety_admin,
                role=Role.ADMIN,
            ),
        )

        assert response.status_code == 200
        assert response.get_json()["alert"]["id"] == 1

        call = get_mock.call_args.kwargs

        assert call["alert_id"] == 1
        assert call["clinic_id"] == clinic.id

    def test_acknowledge_alert_forwards_authenticated_user(
        self,
        client,
        auth_headers_for,
        clinical_safety_admin,
        clinic,
        monkeypatch,
    ):
        acknowledgement = SimpleNamespace(
            id=1,
            alert_id=1,
            acknowledged_by_user_id=clinical_safety_admin.id,
            acknowledgement_type="acknowledged",
            justification=None,
            acknowledged_at=TEST_TIMESTAMP,
            created_at=TEST_TIMESTAMP,
            updated_at=TEST_TIMESTAMP,
        )

        acknowledge_mock = Mock(
            return_value=acknowledgement
        )

        monkeypatch.setattr(
            "app.core.clinical_safety.routes.clinical_safety_routes.acknowledge_clinical_alert",
            acknowledge_mock,
        )

        response = client.post(
            "/api/v1/clinical-safety/alerts/1/acknowledge",
            json={
                "acknowledgement_type": "acknowledged",
            },
            headers=auth_headers_for(
                clinical_safety_admin,
                role=Role.ADMIN,
            ),
        )

        assert response.status_code == 201

        call = acknowledge_mock.call_args.kwargs

        assert call["clinic_id"] == clinic.id
        assert call["alert_id"] == 1
        assert call["actor_user_id"] == clinical_safety_admin.id

    def test_resolve_alert_forwards_authenticated_user(
        self,
        client,
        auth_headers_for,
        clinical_safety_admin,
        clinic,
        monkeypatch,
    ):
        alert = SimpleNamespace(
            id=1,
            clinic_id=clinic.id,
            patient_id=1,
            rule_id=1,
            rule_version=1,
            severity=ClinicalRuleSeverity.HIGH,
            action=ClinicalRuleAction.ALERT,
            status=ClinicalAlertStatus.RESOLVED,
            title="Resolved Alert",
            message="Resolved clinical safety alert",
            context={},
            source_type="prescription",
            source_id=10,
            deduplication_key="test-key",
            generated_at=TEST_TIMESTAMP,
            resolved_at=TEST_TIMESTAMP,
            created_at=TEST_TIMESTAMP,
            updated_at=TEST_TIMESTAMP,
        )

        resolve_mock = Mock(return_value=alert)

        monkeypatch.setattr(
            "app.core.clinical_safety.routes.clinical_safety_routes.resolve_clinical_alert",
            resolve_mock,
        )

        response = client.post(
            "/api/v1/clinical-safety/alerts/1/resolve",
            headers=auth_headers_for(
                clinical_safety_admin,
                role=Role.ADMIN,
            ),
        )

        assert response.status_code == 200

        call = resolve_mock.call_args.kwargs

        assert call["clinic_id"] == clinic.id
        assert call["alert_id"] == 1
        assert call["actor_user_id"] == clinical_safety_admin.id

    def test_unauthenticated_request_is_rejected(
        self,
        client,
    ):
        response = client.get(
            "/api/v1/clinical-safety/rules"
        )

        assert response.status_code == 401