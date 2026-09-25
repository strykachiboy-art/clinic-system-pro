from __future__ import annotations

from datetime import timedelta, timezone

import pytest

from app.core.clinical_safety.services.rule_engine_service import (
    evaluate_clinical_rules,
    resolve_clinical_rules,
)
from app.core.enums.clinical_safety_enums import (
    ClinicalRuleAction,
    ClinicalRuleScope,
    ClinicalRuleSeverity,
)
from app.core.exceptions import ValidationError


def test_resolve_clinical_rules_returns_active_clinic_rules(
    clinic,
    clinical_rule,
):
    rules = resolve_clinical_rules(
        clinic_id=clinic.id,
    )

    assert clinical_rule.id in {
        rule.id
        for rule in rules
    }


def test_resolve_clinical_rules_excludes_other_clinics(
    clinic,
    clinical_rule,
    clinical_other_clinic_rule,
):
    rules = resolve_clinical_rules(
        clinic_id=clinic.id,
    )

    ids = {
        rule.id
        for rule in rules
    }

    assert clinical_rule.id in ids
    assert clinical_other_clinic_rule.id not in ids


def test_global_rule_applies_to_clinic(
    clinic,
    clinical_global_rule,
):
    rules = resolve_clinical_rules(
        clinic_id=clinic.id,
    )

    ids = {
        rule.id
        for rule in rules
    }

    assert clinical_global_rule.id in ids


def test_department_rule_requires_matching_department(
    clinic,
    clinical_department_rule,
):
    rules = resolve_clinical_rules(
        clinic_id=clinic.id,
        department_code="CARDIOLOGY",
    )

    assert clinical_department_rule.id in {
        rule.id
        for rule in rules
    }


def test_department_rule_is_excluded_for_other_department(
    clinic,
    clinical_department_rule,
):
    rules = resolve_clinical_rules(
        clinic_id=clinic.id,
        department_code="PEDIATRICS",
    )

    assert clinical_department_rule.id not in {
        rule.id
        for rule in rules
    }


def test_future_rule_version_is_not_used_before_effective_time(
    clinic,
    clinical_rule,
    clinical_rule_second_version,
):
    rules = resolve_clinical_rules(
        clinic_id=clinic.id,
        evaluation_at=clinical_rule.effective_from,
    )

    ids = {
        rule.id
        for rule in rules
    }

    assert clinical_rule.id in ids
    assert clinical_rule_second_version.id not in ids


def test_future_rule_version_becomes_active_at_effective_time(
    clinic,
    clinical_rule_second_version,
):
    rules = resolve_clinical_rules(
        clinic_id=clinic.id,
        evaluation_at=(
            clinical_rule_second_version.effective_from
        ),
    )

    ids = {
        rule.id
        for rule in rules
    }

    assert clinical_rule_second_version.id in ids


def test_evaluation_returns_safe_when_no_rule_matches(
    clinic,
    clinical_rule,
):
    result = evaluate_clinical_rules(
        clinic_id=clinic.id,
        context={
            "medication_ids": [99],
        },
    )

    assert result.outcome == "safe"
    assert result.blocked is False
    assert result.matched_rule_count == 0


def test_evaluation_aggregates_blocked_result(
    clinic,
    clinical_rule,
):
    clinical_rule.action = ClinicalRuleAction.BLOCK
    clinical_rule.severity = ClinicalRuleSeverity.HIGH

    result = evaluate_clinical_rules(
        clinic_id=clinic.id,
        context={
            "medication_ids": [1, 2],
        },
    )

    assert result.blocked is True
    assert result.outcome == "blocked"
    assert result.matched_rule_count >= 1


def test_evaluation_aggregates_acknowledgement_requirement(
    clinic,
    clinical_rule,
):
    clinical_rule.action = (
        ClinicalRuleAction.REQUIRE_ACKNOWLEDGEMENT
    )

    result = evaluate_clinical_rules(
        clinic_id=clinic.id,
        context={
            "medication_ids": [1, 2],
        },
    )

    assert result.outcome == "acknowledgement_required"
    assert result.requires_acknowledgement is True


def test_blocked_has_precedence_over_warning(
    clinic,
    clinical_rule,
    clinical_department_rule,
):
    clinical_rule.action = ClinicalRuleAction.ALERT
    clinical_department_rule.action = ClinicalRuleAction.BLOCK

    result = evaluate_clinical_rules(
        clinic_id=clinic.id,
        department_code="CARDIOLOGY",
        context={
            "medication_ids": [1, 2],
            "proposed_medication": {
                "drug_id": 10,
                "dose": 1500,
            },
        },
    )

    assert result.outcome == "blocked"


def test_results_are_deterministically_sorted(
    clinic,
    clinical_rule,
    clinical_department_rule,
):
    clinical_rule.priority = 200
    clinical_rule.severity = ClinicalRuleSeverity.LOW

    clinical_department_rule.priority = 50
    clinical_department_rule.severity = ClinicalRuleSeverity.HIGH

    result = evaluate_clinical_rules(
        clinic_id=clinic.id,
        department_code="CARDIOLOGY",
        context={
            "medication_ids": [1, 2],
            "proposed_medication": {
                "drug_id": 10,
                "dose": 1500,
            },
        },
    )

    ordered = list(result.results)

    assert ordered == sorted(
        ordered,
        key=lambda item: (
            {
                "critical": 0,
                "high": 1,
                "moderate": 2,
                "low": 3,
                "info": 4,
            }.get(item.severity, 99),
            item.priority,
            item.rule_code,
            item.rule_id,
            item.rule_version,
        ),
    )


def test_hard_rule_failure_remains_blocked(
    clinic,
    clinical_hard_rule,
):
    result = evaluate_clinical_rules(
        clinic_id=clinic.id,
        context={
            "medication_ids": [1, 2],
        },
    )

    assert result.blocked is True
    assert result.outcome == "blocked"


def test_evaluation_time_must_be_timezone_aware(
    clinic,
):
    with pytest.raises(ValidationError):
        evaluate_clinical_rules(
            clinic_id=clinic.id,
            context={},
            evaluation_at=(
                clinical_naive_datetime()
            ),
        )


def test_invalid_clinic_id_is_rejected():
    with pytest.raises(ValidationError):
        resolve_clinical_rules(
            clinic_id=0,
        )


def test_result_serialization(
    clinic,
    clinical_rule,
):
    result = evaluate_clinical_rules(
        clinic_id=clinic.id,
        context={},
    )

    payload = result.to_dict()

    assert payload["clinic_id"] == clinic.id
    assert "evaluated_at" in payload
    assert "outcome" in payload
    assert "matched_rule_count" in payload
    assert "results" in payload


def clinical_naive_datetime():
    from datetime import datetime

    return datetime.now()