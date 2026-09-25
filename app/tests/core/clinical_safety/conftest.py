from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app.core.clinical_safety.models.clinical_rule_model import (
    ClinicalRule,
)
from app.core.enums.clinical_safety_enums import (
    ClinicalRuleAction,
    ClinicalRuleScope,
    ClinicalRuleSeverity,
    ClinicalRuleType,
)
from app.core.enums.role_enums import Role


DEFAULT_RULE_CONFIGURATION = {
    "drug_a_id": 1,
    "drug_b_id": 2,
    "minimum_severity": "moderate",
}


DEFAULT_RULE_CONDITIONS = {}


@pytest.fixture()
def clinical_safety_admin(
    make_user,
    clinic,
):
    return make_user(
        clinic,
        role=Role.ADMIN,
        email="clinical.safety.admin@test.com",
    )


@pytest.fixture()
def clinical_safety_super_admin(
    make_user,
):
    return make_user(
        clinic=None,
        role=Role.SUPER_ADMIN,
        email="clinical.safety.superadmin@test.com",
    )


@pytest.fixture()
def clinical_safety_other_clinic(
    make_clinic,
):
    return make_clinic(
        name="Clinical Safety Other Clinic",
    )


@pytest.fixture()
def clinical_safety_other_admin(
    make_user,
    clinical_safety_other_clinic,
):
    return make_user(
        clinical_safety_other_clinic,
        role=Role.ADMIN,
        email="clinical.safety.other.admin@test.com",
    )


@pytest.fixture()
def make_clinical_rule(
    db_session,
):
    def _make(
        *,
        clinic=None,
        rule_code="DRUG_INTERACTION_TEST",
        name="Drug Interaction Test Rule",
        description="Test clinical safety rule.",
        scope=ClinicalRuleScope.CLINIC,
        rule_type=ClinicalRuleType.DRUG_INTERACTION,
        severity=ClinicalRuleSeverity.MODERATE,
        action=ClinicalRuleAction.ALERT,
        conditions=None,
        configuration=None,
        department_code=None,
        priority=100,
        enabled=True,
        is_hard_rule=False,
        version=1,
        effective_from=None,
        effective_until=None,
        created_by_user=None,
        updated_by_user=None,
        **overrides,
    ):
        now = datetime.now(timezone.utc)

        rule = ClinicalRule(
            clinic_id=(
                clinic.id
                if clinic is not None
                else None
            ),
            rule_code=rule_code,
            name=name,
            description=description,
            scope=scope,
            rule_type=rule_type,
            severity=severity,
            action=action,
            conditions=(
                DEFAULT_RULE_CONDITIONS
                if conditions is None
                else conditions
            ),
            configuration=(
                DEFAULT_RULE_CONFIGURATION
                if configuration is None
                else configuration
            ),
            department_code=department_code,
            priority=priority,
            enabled=enabled,
            is_hard_rule=is_hard_rule,
            version=version,
            effective_from=(
                effective_from
                if effective_from is not None
                else now
            ),
            effective_until=effective_until,
            created_by_user_id=(
                created_by_user.id
                if created_by_user is not None
                else None
            ),
            updated_by_user_id=(
                updated_by_user.id
                if updated_by_user is not None
                else None
            ),
            **overrides,
        )

        db_session.add(rule)
        db_session.flush()

        return rule

    return _make


@pytest.fixture()
def clinical_rule(
    make_clinical_rule,
    clinic,
    clinical_safety_admin,
):
    return make_clinical_rule(
        clinic=clinic,
        created_by_user=clinical_safety_admin,
        updated_by_user=clinical_safety_admin,
    )


@pytest.fixture()
def clinical_department_rule(
    make_clinical_rule,
    clinic,
    clinical_safety_admin,
):
    return make_clinical_rule(
        clinic=clinic,
        rule_code="DEPARTMENT_DOSE_LIMIT",
        name="Department Dose Limit",
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
        created_by_user=clinical_safety_admin,
        updated_by_user=clinical_safety_admin,
    )


@pytest.fixture()
def clinical_global_rule(
    make_clinical_rule,
    clinical_safety_super_admin,
):
    return make_clinical_rule(
        clinic=None,
        rule_code="GLOBAL_DRUG_INTERACTION",
        name="Global Drug Interaction Rule",
        scope=ClinicalRuleScope.GLOBAL,
        rule_type=ClinicalRuleType.DRUG_INTERACTION,
        severity=ClinicalRuleSeverity.HIGH,
        action=ClinicalRuleAction.BLOCK,
        created_by_user=clinical_safety_super_admin,
        updated_by_user=clinical_safety_super_admin,
    )


@pytest.fixture()
def clinical_hard_rule(
    make_clinical_rule,
    clinical_safety_super_admin,
):
    return make_clinical_rule(
        clinic=None,
        rule_code="HARD_DRUG_INTERACTION",
        name="Hard Drug Interaction Rule",
        scope=ClinicalRuleScope.GLOBAL,
        rule_type=ClinicalRuleType.DRUG_INTERACTION,
        severity=ClinicalRuleSeverity.CRITICAL,
        action=ClinicalRuleAction.BLOCK,
        is_hard_rule=True,
        created_by_user=clinical_safety_super_admin,
        updated_by_user=clinical_safety_super_admin,
    )


@pytest.fixture()
def clinical_rule_second_version(
    make_clinical_rule,
    clinic,
    clinical_safety_admin,
    clinical_rule,
):
    effective_from = (
        clinical_rule.effective_from
        + timedelta(days=30)
    )

    clinical_rule.effective_until = (
        effective_from
        - timedelta(microseconds=1)
    )

    return make_clinical_rule(
        clinic=clinic,
        rule_code=clinical_rule.rule_code,
        name=clinical_rule.name,
        description=clinical_rule.description,
        scope=clinical_rule.scope,
        rule_type=clinical_rule.rule_type,
        severity=ClinicalRuleSeverity.HIGH,
        action=ClinicalRuleAction.BLOCK,
        configuration=clinical_rule.configuration,
        version=2,
        effective_from=effective_from,
        created_by_user=clinical_safety_admin,
        updated_by_user=clinical_safety_admin,
    )


@pytest.fixture()
def clinical_other_clinic_rule(
    make_clinical_rule,
    clinical_safety_other_clinic,
    clinical_safety_other_admin,
):
    return make_clinical_rule(
        clinic=clinical_safety_other_clinic,
        rule_code="OTHER_CLINIC_RULE",
        name="Other Clinic Rule",
        created_by_user=clinical_safety_other_admin,
        updated_by_user=clinical_safety_other_admin,
    )


@pytest.fixture()
def clinical_rule_audit_mock(
    monkeypatch,
):
    from app.core.clinical_safety.services import (
        clinical_rule_service,
    )

    audit = Mock()

    monkeypatch.setattr(
        clinical_rule_service,
        "create_audit_log",
        audit,
    )

    return audit