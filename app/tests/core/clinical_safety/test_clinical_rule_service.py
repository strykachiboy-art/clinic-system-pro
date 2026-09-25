from __future__ import annotations

from datetime import timedelta, timezone

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.clinical_safety.models.clinical_rule_model import ClinicalRule
from app.core.clinical_safety.schemas.clinical_rule_schema import (
    ClinicalRuleCreateSchema,
    ClinicalRuleListQuerySchema,
    ClinicalRuleUpdateSchema,
)
from app.core.clinical_safety.services.clinical_rule_service import (
    create_clinical_rule,
    disable_clinical_rule,
    get_clinical_rule,
    list_clinical_rules,
    update_clinical_rule,
)
from app.core.enums.audit_enums import AuditAction
from app.core.enums.clinic_enums import ClinicStatus
from app.core.enums.clinical_safety_enums import (
    ClinicalRuleAction,
    ClinicalRuleScope,
    ClinicalRuleSeverity,
    ClinicalRuleType,
)
from app.core.enums.role_enums import Role
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)


def _drug_interaction_payload(**overrides):
    data = {
        "rule_code": "DRUG_INTERACTION_TEST",
        "name": "Drug Interaction Test Rule",
        "description": "Test clinical safety rule.",
        "scope": ClinicalRuleScope.CLINIC,
        "rule_type": ClinicalRuleType.DRUG_INTERACTION,
        "severity": ClinicalRuleSeverity.MODERATE,
        "action": ClinicalRuleAction.ALERT,
        "conditions": {},
        "configuration": {
            "drug_a_id": 1,
            "drug_b_id": 2,
            "minimum_severity": "moderate",
        },
        "priority": 100,
        "enabled": True,
    }
    data.update(overrides)
    return ClinicalRuleCreateSchema(**data)


class TestCreateClinicalRule:
    def test_create_clinic_rule_success(
        self,
        db_session,
        clinic,
        clinical_safety_admin,
        clinical_rule_audit_mock,
    ):
        payload = _drug_interaction_payload()

        rule = create_clinical_rule(
            actor_user_id=clinical_safety_admin.id,
            clinic_id=clinic.id,
            data=payload,
        )

        assert rule.id is not None
        assert rule.clinic_id == clinic.id
        assert rule.rule_code == "DRUG_INTERACTION_TEST"
        assert rule.version == 1
        assert rule.enabled is True
        assert rule.is_hard_rule is False
        assert rule.action == ClinicalRuleAction.ALERT
        assert rule.severity == ClinicalRuleSeverity.MODERATE

        persisted = db_session.get(
            ClinicalRule,
            rule.id,
        )

        assert persisted is not None
        assert persisted.clinic_id == clinic.id
        assert persisted.created_by_user_id == clinical_safety_admin.id
        assert persisted.updated_by_user_id == clinical_safety_admin.id

        clinical_rule_audit_mock.assert_called_once()

        audit_call = clinical_rule_audit_mock.call_args
        assert audit_call.kwargs["action"] == AuditAction.CREATE
        assert audit_call.kwargs["entity_type"] == "ClinicalRule"
        assert audit_call.kwargs["entity_id"] == rule.id
        assert audit_call.kwargs["user_id"] == clinical_safety_admin.id

    def test_create_department_rule_success(
        self,
        clinic,
        clinical_safety_admin,
    ):
        payload = _drug_interaction_payload(
            rule_code="DEPARTMENT_DRUG_RULE",
            name="Department Drug Rule",
            scope=ClinicalRuleScope.DEPARTMENT,
            rule_type=ClinicalRuleType.MAX_DOSE,
            severity=ClinicalRuleSeverity.HIGH,
            action=ClinicalRuleAction.BLOCK,
            department_code="CARDIOLOGY",
            configuration={
                "drug_id": 10,
                "threshold": 1000,
                "unit": "mg",
                "frequency": "24h",
            },
        )

        rule = create_clinical_rule(
            actor_user_id=clinical_safety_admin.id,
            clinic_id=clinic.id,
            data=payload,
        )

        assert rule.scope == ClinicalRuleScope.DEPARTMENT
        assert rule.department_code == "CARDIOLOGY"
        assert rule.rule_type == ClinicalRuleType.MAX_DOSE
        assert rule.action == ClinicalRuleAction.BLOCK

    def test_create_global_rule_requires_super_admin(
        self,
        clinic,
        clinical_safety_admin,
    ):
        payload = _drug_interaction_payload(
            rule_code="GLOBAL_TEST_RULE",
            scope=ClinicalRuleScope.GLOBAL,
        )

        with pytest.raises(ValidationError):
            create_clinical_rule(
                actor_user_id=clinical_safety_admin.id,
                clinic_id=None,
                data=payload,
            )

    def test_super_admin_can_create_global_rule(
        self,
        clinical_safety_super_admin,
        clinical_rule_audit_mock,
    ):
        payload = _drug_interaction_payload(
            rule_code="GLOBAL_TEST_RULE",
            scope=ClinicalRuleScope.GLOBAL,
            action=ClinicalRuleAction.BLOCK,
            severity=ClinicalRuleSeverity.CRITICAL,
        )

        rule = create_clinical_rule(
            actor_user_id=clinical_safety_super_admin.id,
            clinic_id=None,
            data=payload,
        )

        assert rule.clinic_id is None
        assert rule.scope == ClinicalRuleScope.GLOBAL
        assert rule.version == 1
        assert rule.action == ClinicalRuleAction.BLOCK
        assert rule.is_hard_rule is False

        clinical_rule_audit_mock.assert_called_once()

    def test_non_admin_cannot_manage_clinical_rules(
        self,
        make_user,
        clinic,
    ):
        clinician = make_user(
            clinic,
            role=Role.DOCTOR,
            email="clinical.rule.doctor@test.com",
        )

        payload = _drug_interaction_payload()

        with pytest.raises(ValidationError):
            create_clinical_rule(
                actor_user_id=clinician.id,
                clinic_id=clinic.id,
                data=payload,
            )

    def test_inactive_actor_cannot_create_rule(
        self,
        make_user,
        clinic,
        db_session,
    ):
        actor = make_user(
            clinic,
            role=Role.ADMIN,
            email="clinical.rule.inactive@test.com",
        )

        actor.is_active = False
        db_session.flush()

        payload = _drug_interaction_payload()

        with pytest.raises(ValidationError):
            create_clinical_rule(
                actor_user_id=actor.id,
                clinic_id=clinic.id,
                data=payload,
            )

    def test_create_rule_rejects_inactive_clinic(
        self,
        make_clinic,
        make_user,
    ):
        inactive_clinic = make_clinic(
            name="Inactive Clinical Safety Clinic",
            status=ClinicStatus.INACTIVE,
        )

        admin = make_user(
            inactive_clinic,
            role=Role.ADMIN,
            email="clinical.rule.inactive.clinic@test.com",
        )

        payload = _drug_interaction_payload()

        with pytest.raises(ValidationError):
            create_clinical_rule(
                actor_user_id=admin.id,
                clinic_id=inactive_clinic.id,
                data=payload,
            )

    def test_create_rule_rejects_suspended_clinic(
        self,
        make_clinic,
        make_user,
    ):
        suspended_clinic = make_clinic(
            name="Suspended Clinical Safety Clinic",
            status=ClinicStatus.SUSPENDED,
        )

        admin = make_user(
            suspended_clinic,
            role=Role.ADMIN,
            email="clinical.rule.suspended.clinic@test.com",
        )

        payload = _drug_interaction_payload()

        with pytest.raises(ValidationError):
            create_clinical_rule(
                actor_user_id=admin.id,
                clinic_id=suspended_clinic.id,
                data=payload,
            )

    def test_hard_rule_requires_super_admin(
        self,
        clinic,
        clinical_safety_admin,
    ):
        payload = _drug_interaction_payload(
            rule_code="ADMIN_HARD_RULE",
        )

        with pytest.raises(ValidationError):
            create_clinical_rule(
                actor_user_id=clinical_safety_admin.id,
                clinic_id=clinic.id,
                data=payload,
                is_hard_rule=True,
            )

    def test_hard_rule_must_be_global(
        self,
        clinical_safety_super_admin,
        clinic,
    ):
        payload = _drug_interaction_payload(
            rule_code="CLINIC_HARD_RULE",
        )

        with pytest.raises(ValidationError):
            create_clinical_rule(
                actor_user_id=clinical_safety_super_admin.id,
                clinic_id=clinic.id,
                data=payload,
                is_hard_rule=True,
            )

    def test_hard_rule_must_use_block_action(
        self,
        clinical_safety_super_admin,
    ):
        payload = _drug_interaction_payload(
            rule_code="INVALID_HARD_RULE",
            scope=ClinicalRuleScope.GLOBAL,
            action=ClinicalRuleAction.ALERT,
        )

        with pytest.raises(ValidationError):
            create_clinical_rule(
                actor_user_id=clinical_safety_super_admin.id,
                clinic_id=None,
                data=payload,
                is_hard_rule=True,
            )

    def test_invalid_drug_interaction_configuration_is_rejected(
        self,
        clinic,
        clinical_safety_admin,
    ):
        payload = _drug_interaction_payload(
            configuration={
                "drug_a_id": 10,
                "drug_b_id": 10,
                "minimum_severity": "moderate",
            },
        )

        with pytest.raises(ValidationError):
            create_clinical_rule(
                actor_user_id=clinical_safety_admin.id,
                clinic_id=clinic.id,
                data=payload,
            )

    def test_invalid_max_dose_configuration_is_rejected(
        self,
        clinic,
        clinical_safety_admin,
    ):
        payload = _drug_interaction_payload(
            rule_code="INVALID_MAX_DOSE",
            rule_type=ClinicalRuleType.MAX_DOSE,
            configuration={
                "drug_id": 10,
                "threshold": 0,
                "unit": "mg",
                "frequency": "24h",
            },
        )

        with pytest.raises(ValidationError):
            create_clinical_rule(
                actor_user_id=clinical_safety_admin.id,
                clinic_id=clinic.id,
                data=payload,
            )


class TestGetClinicalRule:
    def test_get_clinical_rule_success(
        self,
        clinical_rule,
        clinical_safety_admin,
    ):
        result = get_clinical_rule(
            rule_id=clinical_rule.id,
            actor_user_id=clinical_safety_admin.id,
        )

        assert result.id == clinical_rule.id
        assert result.clinic_id == clinical_rule.clinic_id
        assert result.rule_code == clinical_rule.rule_code

    def test_get_clinical_rule_rejects_cross_clinic_access(
        self,
        clinical_rule,
        clinical_safety_other_admin,
    ):
        with pytest.raises(NotFoundError):
            get_clinical_rule(
                rule_id=clinical_rule.id,
                actor_user_id=clinical_safety_other_admin.id,
            )

    def test_super_admin_can_get_clinic_rule(
        self,
        clinical_rule,
        clinical_safety_super_admin,
    ):
        result = get_clinical_rule(
            rule_id=clinical_rule.id,
            actor_user_id=clinical_safety_super_admin.id,
        )

        assert result.id == clinical_rule.id
        assert result.clinic_id == clinical_rule.clinic_id

    def test_get_missing_rule_rejected(
        self,
        clinical_safety_admin,
    ):
        with pytest.raises(NotFoundError):
            get_clinical_rule(
                rule_id=999999,
                actor_user_id=clinical_safety_admin.id,
            )


class TestListClinicalRules:
    def test_admin_list_is_tenant_scoped(
        self,
        clinic,
        clinical_safety_admin,
        clinical_other_clinic_rule,
        clinical_rule,
    ):
        query = ClinicalRuleListQuerySchema()

        result = list_clinical_rules(
            actor_user_id=clinical_safety_admin.id,
            clinic_id=clinic.id,
            query=query,
        )

        rules = result["items"]

        ids = {rule.id for rule in rules}

        assert clinical_rule.id in ids
        assert clinical_other_clinic_rule.id not in ids

    def test_admin_can_see_global_rules(
        self,
        clinic,
        clinical_safety_admin,
        clinical_rule,
        clinical_global_rule,
    ):
        query = ClinicalRuleListQuerySchema(
            include_global=True,
        )

        result = list_clinical_rules(
            actor_user_id=clinical_safety_admin.id,
            clinic_id=clinic.id,
            query=query,
        )

        ids = {rule.id for rule in result["items"]}

        assert clinical_rule.id in ids
        assert clinical_global_rule.id in ids

    def test_super_admin_can_list_global_rules(
        self,
        clinical_safety_super_admin,
        clinical_global_rule,
    ):
        query = ClinicalRuleListQuerySchema(
            include_global=True,
        )

        result = list_clinical_rules(
            actor_user_id=clinical_safety_super_admin.id,
            clinic_id=None,
            query=query,
        )

        ids = {rule.id for rule in result["items"]}

        assert clinical_global_rule.id in ids

    def test_list_can_filter_by_rule_type(
        self,
        clinic,
        clinical_safety_admin,
        clinical_rule,
        clinical_department_rule,
    ):
        query = ClinicalRuleListQuerySchema(
            rule_type=ClinicalRuleType.MAX_DOSE,
        )

        result = list_clinical_rules(
            actor_user_id=clinical_safety_admin.id,
            clinic_id=clinic.id,
            query=query,
        )

        assert all(
            rule.rule_type == ClinicalRuleType.MAX_DOSE
            for rule in result["items"]
        )

        assert clinical_department_rule.id in {
            rule.id for rule in result["items"]
        }

        assert clinical_rule.id not in {
            rule.id for rule in result["items"]
        }


class TestUpdateClinicalRule:
    def test_update_creates_new_version(
        self,
        db_session,
        clinical_rule,
        clinical_safety_admin,
        clinical_rule_audit_mock,
    ):
        effective_from = clinical_rule.effective_from + timedelta(days=30)

        payload = ClinicalRuleUpdateSchema(
            name="Updated Drug Interaction Rule",
            severity=ClinicalRuleSeverity.HIGH,
            action=ClinicalRuleAction.BLOCK,
            effective_from=effective_from,
        )

        updated = update_clinical_rule(
            rule_id=clinical_rule.id,
            actor_user_id=clinical_safety_admin.id,
            data=payload,
        )

        assert updated.id != clinical_rule.id
        assert updated.version == 2
        assert updated.rule_code == clinical_rule.rule_code
        assert updated.name == "Updated Drug Interaction Rule"
        assert updated.severity == ClinicalRuleSeverity.HIGH
        assert updated.action == ClinicalRuleAction.BLOCK

        previous = db_session.get(
            ClinicalRule,
            clinical_rule.id,
        )

        assert previous is not None
        assert previous.version == 1
        assert previous.effective_until is not None
        actual_effective_until = previous.effective_until

        if actual_effective_until.tzinfo is None:
            actual_effective_until = actual_effective_until.replace(
                tzinfo=timezone.utc
            )

        assert (
            actual_effective_until
            == effective_from - timedelta(microseconds=1)
        )

        clinical_rule_audit_mock.assert_called_once()

        audit_call = clinical_rule_audit_mock.call_args
        assert audit_call.kwargs["action"] == AuditAction.UPDATE
        assert audit_call.kwargs["entity_type"] == "ClinicalRule"
        assert audit_call.kwargs["entity_id"] == updated.id
        assert audit_call.kwargs["user_id"] == clinical_safety_admin.id

    def test_update_preserves_rule_code(
        self,
        clinical_rule,
        clinical_safety_admin,
    ):
        payload = ClinicalRuleUpdateSchema(
            name="Renamed Rule",
            effective_from=clinical_rule.effective_from + timedelta(days=10),
        )

        updated = update_clinical_rule(
            rule_id=clinical_rule.id,
            actor_user_id=clinical_safety_admin.id,
            data=payload,
        )

        assert updated.rule_code == clinical_rule.rule_code

    def test_update_cross_clinic_rule_is_rejected(
        self,
        clinical_rule,
        clinical_safety_other_admin,
    ):
        effective_from = clinical_rule.effective_from + timedelta(days=10)

        payload = ClinicalRuleUpdateSchema(
            name="Unauthorized Update",
            effective_from=effective_from,
        )

        with pytest.raises(NotFoundError):
            update_clinical_rule(
                rule_id=clinical_rule.id,
                actor_user_id=clinical_safety_other_admin.id,
                data=payload,
            )

    def test_update_non_latest_version_is_rejected(
        self,
        clinical_rule,
        clinical_rule_second_version,
        clinical_safety_admin,
    ):
        payload = ClinicalRuleUpdateSchema(
            name="Invalid Historical Update",
            effective_from=(
                clinical_rule_second_version.effective_from
                + timedelta(days=10)
            ),
        )

        with pytest.raises(ConflictError):
            update_clinical_rule(
                rule_id=clinical_rule.id,
                actor_user_id=clinical_safety_admin.id,
                data=payload,
            )

    def test_hard_rule_cannot_be_downgraded(
        self,
        clinical_hard_rule,
        clinical_safety_super_admin,
    ):
        payload = ClinicalRuleUpdateSchema(
            action=ClinicalRuleAction.INFORM,
            severity=ClinicalRuleSeverity.LOW,
            effective_from=(
                clinical_hard_rule.effective_from
                + timedelta(days=10)
            ),
        )

        with pytest.raises(ValidationError):
            update_clinical_rule(
                rule_id=clinical_hard_rule.id,
                actor_user_id=clinical_safety_super_admin.id,
                data=payload,
            )

    def test_admin_cannot_update_hard_rule(
        self,
        clinical_hard_rule,
        clinical_safety_admin,
    ):
        payload = ClinicalRuleUpdateSchema(
            name="Unauthorized Hard Rule Update",
            effective_from=(
                clinical_hard_rule.effective_from
                + timedelta(days=10)
            ),
        )

        with pytest.raises(NotFoundError):
            update_clinical_rule(
                rule_id=clinical_hard_rule.id,
                actor_user_id=clinical_safety_admin.id,
                data=payload,
            )


class TestDisableClinicalRule:
    def test_disable_creates_disabled_version(
        self,
        db_session,
        clinical_rule,
        clinical_safety_admin,
        clinical_rule_audit_mock,
    ):
        disabled = disable_clinical_rule(
            rule_id=clinical_rule.id,
            actor_user_id=clinical_safety_admin.id,
        )

        assert disabled.id != clinical_rule.id
        assert disabled.version == 2
        assert disabled.enabled is False
        assert disabled.rule_code == clinical_rule.rule_code

        previous = db_session.get(
            ClinicalRule,
            clinical_rule.id,
        )

        assert previous is not None
        assert previous.enabled is True
        assert previous.effective_until is not None

        clinical_rule_audit_mock.assert_called_once()

        audit_call = clinical_rule_audit_mock.call_args
        assert audit_call.kwargs["action"] == AuditAction.UPDATE
        assert audit_call.kwargs["entity_type"] == "ClinicalRule"
        assert audit_call.kwargs["entity_id"] == disabled.id
        assert audit_call.kwargs["user_id"] == clinical_safety_admin.id

    def test_disable_cross_clinic_rule_is_rejected(
        self,
        clinical_rule,
        clinical_safety_other_admin,
    ):
        with pytest.raises(NotFoundError):
            disable_clinical_rule(
                rule_id=clinical_rule.id,
                actor_user_id=clinical_safety_other_admin.id,
            )

    def test_disable_missing_rule_is_rejected(
        self,
        clinical_safety_admin,
    ):
        with pytest.raises(NotFoundError):
            disable_clinical_rule(
                rule_id=999999,
                actor_user_id=clinical_safety_admin.id,
            )


class TestClinicalRuleSchemaBoundary:
    def test_rule_code_is_normalized_to_uppercase(self):
        payload = _drug_interaction_payload(
            rule_code="drug_interaction_test",
        )

        assert payload.rule_code == "DRUG_INTERACTION_TEST"

    def test_unknown_create_fields_are_rejected(self):
        with pytest.raises(PydanticValidationError):
            ClinicalRuleCreateSchema(
                rule_code="UNKNOWN_FIELD_TEST",
                name="Unknown Field Test",
                scope=ClinicalRuleScope.CLINIC,
                rule_type=ClinicalRuleType.DRUG_INTERACTION,
                severity=ClinicalRuleSeverity.LOW,
                action=ClinicalRuleAction.ALERT,
                configuration={
                    "drug_a_id": 1,
                    "drug_b_id": 2,
                    "minimum_severity": "moderate",
                },
                unexpected_field=True,
            )

    def test_department_rule_requires_department_code(self):
        with pytest.raises(PydanticValidationError):
            _drug_interaction_payload(
                scope=ClinicalRuleScope.DEPARTMENT,
            )

    def test_clinic_rule_rejects_department_code(self):
        with pytest.raises(PydanticValidationError):
            _drug_interaction_payload(
                department_code="CARDIOLOGY",
            )

    def test_effective_until_must_follow_effective_from(
        self,
        clinical_rule,
    ):
        with pytest.raises(PydanticValidationError):
            ClinicalRuleUpdateSchema(
                effective_from=clinical_rule.effective_from,
                effective_until=clinical_rule.effective_from,
            )


