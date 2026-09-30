from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.clinical_safety.services.rule_evaluator import (
    OUTCOME_ACKNOWLEDGEMENT_REQUIRED,
    OUTCOME_BLOCKED,
    OUTCOME_INFORMATION,
    OUTCOME_JUSTIFICATION_REQUIRED,
    OUTCOME_SAFE,
    OUTCOME_WARNING,
    evaluate_rule,
)
from app.core.enums.clinical_safety_enums import (
    ClinicalRuleAction,
    ClinicalRuleSeverity,
    ClinicalRuleType,
)
from app.core.exceptions import ValidationError


def make_rule(
    *,
    rule_id=1,
    rule_code="TEST_RULE",
    version=1,
    severity=ClinicalRuleSeverity.MODERATE,
    action=ClinicalRuleAction.ALERT,
    rule_type=ClinicalRuleType.MAX_DOSE,
    priority=100,
    is_hard_rule=False,
    conditions=None,
    configuration=None,
):
    return SimpleNamespace(
        id=rule_id,
        rule_code=rule_code,
        version=version,
        severity=severity,
        action=action,
        rule_type=rule_type,
        priority=priority,
        is_hard_rule=is_hard_rule,
        conditions={} if conditions is None else conditions,
        configuration={} if configuration is None else configuration,
    )


def max_dose_rule(**overrides):
    data = {
        "rule_type": ClinicalRuleType.MAX_DOSE,
        "configuration": {
            "drug_id": 10,
            "threshold": 1000,
            "unit": "mg",
            "frequency": "24h",
        },
    }
    data.update(overrides)
    return make_rule(**data)


class TestEvaluateRuleOutcomes:
    def test_unmatched_rule_returns_safe(self):
        rule = max_dose_rule()

        result = evaluate_rule(
            rule,
            {
                "proposed_medication": {
                    "drug_id": 10,
                    "dose": 500,
                }
            },
        )

        assert result.matched is False
        assert result.outcome == OUTCOME_SAFE
        assert result.blocked is False

    def test_inform_action_returns_information(self):
        rule = max_dose_rule(
            action=ClinicalRuleAction.INFORM,
        )

        result = evaluate_rule(
            rule,
            {
                "proposed_medication": {
                    "drug_id": 10,
                    "dose": 1500,
                }
            },
        )

        assert result.matched is True
        assert result.outcome == OUTCOME_INFORMATION

    def test_alert_action_returns_warning(self):
        rule = max_dose_rule(
            action=ClinicalRuleAction.ALERT,
        )

        result = evaluate_rule(
            rule,
            {
                "proposed_medication": {
                    "drug_id": 10,
                    "dose": 1500,
                }
            },
        )

        assert result.outcome == OUTCOME_WARNING

    def test_acknowledgement_action_requires_acknowledgement(self):
        rule = max_dose_rule(
            action=ClinicalRuleAction.REQUIRE_ACKNOWLEDGEMENT,
        )

        result = evaluate_rule(
            rule,
            {
                "proposed_medication": {
                    "drug_id": 10,
                    "dose": 1500,
                }
            },
        )

        assert result.outcome == OUTCOME_ACKNOWLEDGEMENT_REQUIRED
        assert result.requires_acknowledgement is True

    def test_justification_action_requires_justification(self):
        rule = max_dose_rule(
            action=ClinicalRuleAction.REQUIRE_JUSTIFICATION,
        )

        result = evaluate_rule(
            rule,
            {
                "proposed_medication": {
                    "drug_id": 10,
                    "dose": 1500,
                }
            },
        )

        assert result.outcome == OUTCOME_JUSTIFICATION_REQUIRED
        assert result.requires_justification is True

    def test_block_action_returns_blocked(self):
        rule = max_dose_rule(
            action=ClinicalRuleAction.BLOCK,
        )

        result = evaluate_rule(
            rule,
            {
                "proposed_medication": {
                    "drug_id": 10,
                    "dose": 1500,
                }
            },
        )

        assert result.outcome == OUTCOME_BLOCKED
        assert result.blocked is True


class TestHardRuleSafety:
    def test_hard_rule_cannot_be_weakened_by_runtime_action(self):
        rule = max_dose_rule(
            action=ClinicalRuleAction.ALERT,
            is_hard_rule=True,
        )

        result = evaluate_rule(
            rule,
            {
                "proposed_medication": {
                    "drug_id": 10,
                    "dose": 1500,
                }
            },
        )

        assert result.matched is True
        assert result.outcome == OUTCOME_BLOCKED
        assert result.blocked is True

    def test_invalid_hard_rule_fails_closed(self):
        rule = max_dose_rule(
            is_hard_rule=True,
            configuration={
                "drug_id": 10,
                "threshold": 0,
            },
        )

        result = evaluate_rule(
            rule,
            {
                "proposed_medication": {
                    "drug_id": 10,
                    "dose": 1500,
                }
            },
        )

        assert result.matched is True
        assert result.outcome == OUTCOME_BLOCKED
        assert result.evidence["configuration_error"] is True

    def test_invalid_non_hard_rule_does_not_become_safe(self):
        rule = max_dose_rule(
            configuration={
                "drug_id": 10,
                "threshold": 0,
            },
        )

        with pytest.raises(ValidationError):
            evaluate_rule(
                rule,
                {
                    "proposed_medication": {
                        "drug_id": 10,
                        "dose": 1500,
                    }
                },
            )


class TestRuleTypes:
    def test_drug_interaction_matches_two_configured_drugs(self):
        rule = make_rule(
            rule_type=ClinicalRuleType.DRUG_INTERACTION,
            action=ClinicalRuleAction.BLOCK,
            configuration={
                "drug_a_id": 10,
                "drug_b_id": 20,
                "minimum_severity": "moderate",
            },
        )

        result = evaluate_rule(
            rule,
            {
                "medication_ids": [10, 20],
            },
        )

        assert result.matched is True
        assert result.outcome == OUTCOME_BLOCKED

    def test_drug_interaction_does_not_match_single_drug(self):
        rule = make_rule(
            rule_type=ClinicalRuleType.DRUG_INTERACTION,
            configuration={
                "drug_a_id": 10,
                "drug_b_id": 20,
                "minimum_severity": "moderate",
            },
        )

        result = evaluate_rule(
            rule,
            {
                "medication_ids": [10],
            },
        )

        assert result.matched is False
        assert result.outcome == OUTCOME_SAFE

    def test_allergy_conflict_matches(self):
        rule = make_rule(
            rule_type=ClinicalRuleType.ALLERGY_CONFLICT,
            action=ClinicalRuleAction.BLOCK,
            configuration={
                "allergen": "penicillin",
            },
        )

        result = evaluate_rule(
            rule,
            {
                "allergies": [
                    {
                        "allergen": "Penicillin",
                    }
                ],
            },
        )

        assert result.matched is True
        assert result.outcome == OUTCOME_BLOCKED

    def test_contraindication_matches_code(self):
        rule = make_rule(
            rule_type=ClinicalRuleType.CONTRAINDICATION,
            configuration={
                "contraindication_codes": [
                    "CKD_STAGE_4",
                ],
            },
        )

        result = evaluate_rule(
            rule,
            {
                "contraindication_codes": [
                    "CKD_STAGE_4",
                ],
            },
        )

        assert result.matched is True

    def test_max_dose_matches(self):
        result = evaluate_rule(
            max_dose_rule(
                action=ClinicalRuleAction.BLOCK,
            ),
            {
                "proposed_medication": {
                    "drug_id": 10,
                    "dose": 1500,
                }
            },
        )

        assert result.matched is True
        assert result.outcome == OUTCOME_BLOCKED

    def test_max_dose_does_not_match_within_limit(self):
        result = evaluate_rule(
            max_dose_rule(),
            {
                "proposed_medication": {
                    "drug_id": 10,
                    "dose": 1000,
                }
            },
        )

        assert result.matched is False
        assert result.outcome == OUTCOME_SAFE

    def test_min_dose_matches(self):
        rule = make_rule(
            rule_type=ClinicalRuleType.MIN_DOSE,
            configuration={
                "drug_id": 10,
                "threshold": 500,
                "unit": "mg",
                "frequency": "24h",
            },
        )

        result = evaluate_rule(
            rule,
            {
                "proposed_medication": {
                    "drug_id": 10,
                    "dose": 250,
                }
            },
        )

        assert result.matched is True

    def test_age_restriction_matches(self):
        rule = make_rule(
            rule_type=ClinicalRuleType.AGE_RESTRICTION,
            action=ClinicalRuleAction.BLOCK,
            configuration={
                "max_age": 12,
            },
        )

        result = evaluate_rule(
            rule,
            {
                "age": 16,
            },
        )

        assert result.matched is True
        assert result.outcome == OUTCOME_BLOCKED

    def test_weight_restriction_matches(self):
        rule = make_rule(
            rule_type=ClinicalRuleType.WEIGHT_RESTRICTION,
            configuration={
                "min_weight": 50,
            },
        )

        result = evaluate_rule(
            rule,
            {
                "weight": 42,
            },
        )

        assert result.matched is True

    def test_pregnancy_restriction_matches(self):
        rule = make_rule(
            rule_type=ClinicalRuleType.PREGNANCY_RESTRICTION,
            configuration={
                "restricted_statuses": [
                    "pregnant",
                ],
            },
        )

        result = evaluate_rule(
            rule,
            {
                "pregnancy_status": "PREGNANT",
            },
        )

        assert result.matched is True

    def test_duplicate_therapy_matches(self):
        rule = make_rule(
            rule_type=ClinicalRuleType.DUPLICATE_THERAPY,
            configuration={
                "drug_ids": [10, 20],
            },
        )

        result = evaluate_rule(
            rule,
            {
                "medication_ids": [10, 20, 30],
            },
        )

        assert result.matched is True

    def test_lab_conflict_matches(self):
        rule = make_rule(
            rule_type=ClinicalRuleType.LAB_CONFLICT,
            configuration={
                "measure": "creatinine",
                "operator": "gt",
                "threshold": 3.0,
            },
        )

        result = evaluate_rule(
            rule,
            {
                "labs": [
                    {
                        "measure": "creatinine",
                        "value": 4.2,
                    }
                ],
            },
        )

        assert result.matched is True

    def test_renal_function_matches(self):
        rule = make_rule(
            rule_type=ClinicalRuleType.RENAL_FUNCTION,
            configuration={
                "measure": "egfr",
                "operator": "lt",
                "threshold": 30,
            },
        )

        result = evaluate_rule(
            rule,
            {
                "renal_function": {
                    "egfr": 25,
                },
            },
        )

        assert result.matched is True

    def test_hepatic_function_matches(self):
        rule = make_rule(
            rule_type=ClinicalRuleType.HEPATIC_FUNCTION,
            configuration={
                "measure": "alt",
                "operator": "gt",
                "threshold": 200,
            },
        )

        result = evaluate_rule(
            rule,
            {
                "hepatic_function": {
                    "alt": 250,
                },
            },
        )

        assert result.matched is True

    def test_diagnosis_conflict_matches(self):
        rule = make_rule(
            rule_type=ClinicalRuleType.DIAGNOSIS_CONFLICT,
            configuration={
                "diagnosis_codes": [
                    "G40.0",
                ],
            },
        )

        result = evaluate_rule(
            rule,
            {
                "diagnosis_codes": [
                    "G40.0",
                    "I10",
                ],
            },
        )

        assert result.matched is True

    def test_frequency_limit_matches(self):
        rule = make_rule(
            rule_type=ClinicalRuleType.FREQUENCY_LIMIT,
            configuration={
                "max_occurrences": 3,
                "interval_hours": 24,
            },
        )

        result = evaluate_rule(
            rule,
            {
                "proposed_medication": {
                    "frequency_occurrences": 4,
                }
            },
        )

        assert result.matched is True

    def test_duration_limit_matches(self):
        rule = make_rule(
            rule_type=ClinicalRuleType.DURATION_LIMIT,
            configuration={
                "maximum_days": 7,
            },
        )

        result = evaluate_rule(
            rule,
            {
                "proposed_medication": {
                    "duration_days": 10,
                }
            },
        )

        assert result.matched is True

    def test_patient_specific_restriction_matches(self):
        rule = make_rule(
            rule_type=ClinicalRuleType.PATIENT_SPECIFIC_RESTRICTION,
            configuration={
                "field": "patient.risk_level",
                "operator": "eq",
                "value": "high",
            },
        )

        result = evaluate_rule(
            rule,
            {
                "patient": {
                    "risk_level": "high",
                }
            },
        )

        assert result.matched is True


class TestGenericConditions:
    def test_all_conditions_must_match(self):
        rule = max_dose_rule(
            conditions={
                "all": [
                    {
                        "field": "patient.risk_level",
                        "operator": "eq",
                        "value": "high",
                    },
                    {
                        "field": "patient.age",
                        "operator": "gte",
                        "value": 18,
                    },
                ]
            },
        )

        result = evaluate_rule(
            rule,
            {
                "patient": {
                    "risk_level": "high",
                    "age": 17,
                },
                "proposed_medication": {
                    "drug_id": 10,
                    "dose": 1500,
                },
            },
        )

        assert result.matched is False
        assert result.outcome == OUTCOME_SAFE

    def test_any_condition_can_match(self):
        rule = max_dose_rule(
            conditions={
                "any": [
                    {
                        "field": "patient.risk_level",
                        "operator": "eq",
                        "value": "critical",
                    },
                    {
                        "field": "patient.risk_level",
                        "operator": "eq",
                        "value": "high",
                    },
                ]
            },
        )

        result = evaluate_rule(
            rule,
            {
                "patient": {
                    "risk_level": "high",
                },
                "proposed_medication": {
                    "drug_id": 10,
                    "dose": 1500,
                },
            },
        )

        assert result.matched is True

    def test_generic_comparison_operators(self):
        rule = max_dose_rule(
            conditions={
                "field": "patient.age",
                "operator": "between",
                "value": [18, 65],
            },
        )

        result = evaluate_rule(
            rule,
            {
                "patient": {
                    "age": 40,
                },
                "proposed_medication": {
                    "drug_id": 10,
                    "dose": 1500,
                },
            },
        )

        assert result.matched is True


class TestEvaluatorContract:
    def test_evaluation_result_serializes(self):
        rule = max_dose_rule(
            action=ClinicalRuleAction.BLOCK,
        )

        result = evaluate_rule(
            rule,
            {
                "proposed_medication": {
                    "drug_id": 10,
                    "dose": 1500,
                }
            },
        )

        payload = result.to_dict()

        assert payload["rule_id"] == 1
        assert payload["rule_code"] == "TEST_RULE"
        assert payload["rule_version"] == 1
        assert payload["matched"] is True
        assert payload["outcome"] == OUTCOME_BLOCKED
        assert payload["hard_rule"] is False

    def test_evaluator_does_not_mutate_context(self):
        rule = max_dose_rule()

        context = {
            "proposed_medication": {
                "drug_id": 10,
                "dose": 1500,
            }
        }

        original = {
            "proposed_medication": {
                "drug_id": 10,
                "dose": 1500,
            }
        }

        evaluate_rule(
            rule,
            context,
        )

        assert context == original

    def test_invalid_rule_id_is_rejected(self):
        rule = max_dose_rule(
            rule_id=0,
        )

        with pytest.raises(ValidationError):
            evaluate_rule(
                rule,
                {},
            )

    def test_unknown_rule_type_is_rejected(self):
        rule = make_rule(
            rule_type="unknown_rule_type",
        )

        with pytest.raises(ValidationError):
            evaluate_rule(
                rule,
                {},
            )

    def test_unsupported_operator_is_rejected(self):
        rule = max_dose_rule(
            conditions={
                "field": "patient.age",
                "operator": "explode",
                "value": 18,
            },
        )

        with pytest.raises(ValidationError):
            evaluate_rule(
                rule,
                {
                    "patient": {
                        "age": 30,
                    },
                    "proposed_medication": {
                        "drug_id": 10,
                        "dose": 1500,
                    },
                },
            )