from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.core.clinical_safety.services.medication_safety_service import (
    evaluate_medication_safety,
)
from app.core.clinical_safety.services.rule_evaluator import (
    OUTCOME_BLOCKED,
    OUTCOME_SAFE,
    OUTCOME_WARNING,
)
from app.core.exceptions import ValidationError


class TestEvaluateMedicationSafety:
    def test_no_interactions_and_no_rules_is_safe(
        self,
        monkeypatch,
    ):
        clinical_result = Mock()
        clinical_result.outcome = OUTCOME_SAFE
        clinical_result.blocked = False
        clinical_result.requires_acknowledgement = False
        clinical_result.requires_justification = False
        clinical_result.to_dict.return_value = {}

        monkeypatch.setattr(
            "app.core.clinical_safety.services.medication_safety_service.check_interactions",
            Mock(return_value=[]),
        )
        monkeypatch.setattr(
            "app.core.clinical_safety.services.medication_safety_service.evaluate_clinical_rules",
            Mock(return_value=clinical_result),
        )

        result = evaluate_medication_safety(
            clinic_id=1,
            medication_ids=[10, 20],
        )

        assert result.outcome == OUTCOME_SAFE
        assert result.known_interactions == ()
        assert result.medication_ids == (10, 20)

    def test_existing_interaction_becomes_warning(
        self,
        monkeypatch,
    ):
        clinical_result = Mock()
        clinical_result.outcome = OUTCOME_SAFE
        clinical_result.blocked = False
        clinical_result.requires_acknowledgement = False
        clinical_result.requires_justification = False
        clinical_result.to_dict.return_value = {}

        monkeypatch.setattr(
            "app.core.clinical_safety.services.medication_safety_service.check_interactions",
            Mock(
                return_value=[
                    {
                        "drug_a_id": 10,
                        "drug_b_id": 20,
                        "severity": "severe",
                        "description": "Known interaction",
                    }
                ]
            ),
        )
        monkeypatch.setattr(
            "app.core.clinical_safety.services.medication_safety_service.evaluate_clinical_rules",
            Mock(return_value=clinical_result),
        )

        result = evaluate_medication_safety(
            clinic_id=1,
            medication_ids=[20, 10],
        )

        assert result.outcome == OUTCOME_WARNING
        assert len(result.known_interactions) == 1
        assert result.known_interactions[0]["drug_a_id"] == 10
        assert result.known_interactions[0]["drug_b_id"] == 20

    def test_blocked_rule_remains_blocked(
        self,
        monkeypatch,
    ):
        clinical_result = Mock()
        clinical_result.outcome = OUTCOME_BLOCKED
        clinical_result.blocked = True
        clinical_result.requires_acknowledgement = False
        clinical_result.requires_justification = False
        clinical_result.to_dict.return_value = {}

        monkeypatch.setattr(
            "app.core.clinical_safety.services.medication_safety_service.check_interactions",
            Mock(return_value=[]),
        )
        monkeypatch.setattr(
            "app.core.clinical_safety.services.medication_safety_service.evaluate_clinical_rules",
            Mock(return_value=clinical_result),
        )

        result = evaluate_medication_safety(
            clinic_id=1,
            medication_ids=[10, 20],
        )

        assert result.outcome == OUTCOME_BLOCKED
        assert result.blocked is True

    def test_interaction_warning_does_not_downgrade_block(
        self,
        monkeypatch,
    ):
        clinical_result = Mock()
        clinical_result.outcome = OUTCOME_BLOCKED
        clinical_result.blocked = True
        clinical_result.requires_acknowledgement = False
        clinical_result.requires_justification = False
        clinical_result.to_dict.return_value = {}

        monkeypatch.setattr(
            "app.core.clinical_safety.services.medication_safety_service.check_interactions",
            Mock(
                return_value=[
                    {
                        "drug_a_id": 10,
                        "drug_b_id": 20,
                        "severity": "moderate",
                        "description": "Known interaction",
                    }
                ]
            ),
        )
        monkeypatch.setattr(
            "app.core.clinical_safety.services.medication_safety_service.evaluate_clinical_rules",
            Mock(return_value=clinical_result),
        )

        result = evaluate_medication_safety(
            clinic_id=1,
            medication_ids=[10, 20],
        )

        assert result.outcome == OUTCOME_BLOCKED
        assert result.blocked is True
        assert result.has_interaction_warnings is True

    def test_proposed_medication_is_added_to_medication_ids(
        self,
        monkeypatch,
    ):
        interaction_mock = Mock(
            return_value=[]
        )

        clinical_result = Mock()
        clinical_result.outcome = OUTCOME_SAFE
        clinical_result.blocked = False
        clinical_result.requires_acknowledgement = False
        clinical_result.requires_justification = False
        clinical_result.to_dict.return_value = {}

        monkeypatch.setattr(
            "app.core.clinical_safety.services.medication_safety_service.check_interactions",
            interaction_mock,
        )
        monkeypatch.setattr(
            "app.core.clinical_safety.services.medication_safety_service.evaluate_clinical_rules",
            Mock(return_value=clinical_result),
        )

        result = evaluate_medication_safety(
            clinic_id=1,
            medication_ids=[10],
            context={
                "proposed_medication": {
                    "drug_id": 20,
                    "dose": 500,
                }
            },
        )

        assert result.medication_ids == (10, 20)

        interaction_mock.assert_called_once_with(
            drug_ids=[10, 20],
            clinic_id=1,
        )

    def test_duplicate_medication_ids_are_normalized(
        self,
        monkeypatch,
    ):
        interaction_mock = Mock(
            return_value=[]
        )

        clinical_result = Mock()
        clinical_result.outcome = OUTCOME_SAFE
        clinical_result.blocked = False
        clinical_result.requires_acknowledgement = False
        clinical_result.requires_justification = False
        clinical_result.to_dict.return_value = {}

        monkeypatch.setattr(
            "app.core.clinical_safety.services.medication_safety_service.check_interactions",
            interaction_mock,
        )
        monkeypatch.setattr(
            "app.core.clinical_safety.services.medication_safety_service.evaluate_clinical_rules",
            Mock(return_value=clinical_result),
        )

        result = evaluate_medication_safety(
            clinic_id=1,
            medication_ids=[20, 10, 20, 10],
        )

        assert result.medication_ids == (10, 20)

        interaction_mock.assert_called_once_with(
            drug_ids=[10, 20],
            clinic_id=1,
        )

    def test_interactions_are_deterministically_sorted(
        self,
        monkeypatch,
    ):
        clinical_result = Mock()
        clinical_result.outcome = OUTCOME_SAFE
        clinical_result.blocked = False
        clinical_result.requires_acknowledgement = False
        clinical_result.requires_justification = False
        clinical_result.to_dict.return_value = {}

        monkeypatch.setattr(
            "app.core.clinical_safety.services.medication_safety_service.check_interactions",
            Mock(
                return_value=[
                    {
                        "drug_a_id": 30,
                        "drug_b_id": 40,
                        "severity": "mild",
                        "description": "Mild",
                    },
                    {
                        "drug_a_id": 10,
                        "drug_b_id": 20,
                        "severity": "severe",
                        "description": "Severe",
                    },
                    {
                        "drug_a_id": 20,
                        "drug_b_id": 30,
                        "severity": "moderate",
                        "description": "Moderate",
                    },
                ]
            ),
        )
        monkeypatch.setattr(
            "app.core.clinical_safety.services.medication_safety_service.evaluate_clinical_rules",
            Mock(return_value=clinical_result),
        )

        result = evaluate_medication_safety(
            clinic_id=1,
            medication_ids=[10, 20, 30, 40],
        )

        assert [
            interaction["severity"]
            for interaction in result.known_interactions
        ] == [
            "severe",
            "moderate",
            "mild",
        ]

    def test_duplicate_interactions_are_removed(
        self,
        monkeypatch,
    ):
        clinical_result = Mock()
        clinical_result.outcome = OUTCOME_SAFE
        clinical_result.blocked = False
        clinical_result.requires_acknowledgement = False
        clinical_result.requires_justification = False
        clinical_result.to_dict.return_value = {}

        monkeypatch.setattr(
            "app.core.clinical_safety.services.medication_safety_service.check_interactions",
            Mock(
                return_value=[
                    {
                        "drug_a_id": 20,
                        "drug_b_id": 10,
                        "severity": "moderate",
                        "description": "Known interaction",
                    },
                    {
                        "drug_a_id": 10,
                        "drug_b_id": 20,
                        "severity": "moderate",
                        "description": "Duplicate interaction",
                    },
                ]
            ),
        )
        monkeypatch.setattr(
            "app.core.clinical_safety.services.medication_safety_service.evaluate_clinical_rules",
            Mock(return_value=clinical_result),
        )

        result = evaluate_medication_safety(
            clinic_id=1,
            medication_ids=[10, 20],
        )

        assert len(result.known_interactions) == 1
        assert result.known_interactions[0]["drug_a_id"] == 10
        assert result.known_interactions[0]["drug_b_id"] == 20

    def test_invalid_clinic_id_is_rejected(
        self,
        monkeypatch,
    ):
        with pytest.raises(ValidationError):
            evaluate_medication_safety(
                clinic_id=0,
                medication_ids=[],
            )

    def test_invalid_medication_id_is_rejected(
        self,
    ):
        with pytest.raises(ValidationError):
            evaluate_medication_safety(
                clinic_id=1,
                medication_ids=[10, 0],
            )

    def test_invalid_proposed_drug_id_is_rejected(
        self,
    ):
        with pytest.raises(ValidationError):
            evaluate_medication_safety(
                clinic_id=1,
                medication_ids=[10],
                context={
                    "proposed_medication": {
                        "drug_id": 0,
                    }
                },
            )

    def test_non_mapping_context_is_rejected(
        self,
    ):
        with pytest.raises(ValidationError):
            evaluate_medication_safety(
                clinic_id=1,
                medication_ids=[10],
                context="invalid",
            )

    def test_invalid_interaction_response_is_rejected(
        self,
        monkeypatch,
    ):
        clinical_result = Mock()
        clinical_result.outcome = OUTCOME_SAFE
        clinical_result.blocked = False
        clinical_result.requires_acknowledgement = False
        clinical_result.requires_justification = False
        clinical_result.to_dict.return_value = {}

        monkeypatch.setattr(
            "app.core.clinical_safety.services.medication_safety_service.check_interactions",
            Mock(return_value="invalid"),
        )
        monkeypatch.setattr(
            "app.core.clinical_safety.services.medication_safety_service.evaluate_clinical_rules",
            Mock(return_value=clinical_result),
        )

        with pytest.raises(ValidationError):
            evaluate_medication_safety(
                clinic_id=1,
                medication_ids=[10, 20],
            )

    def test_to_dict_contains_full_safety_result(
        self,
        monkeypatch,
    ):
        clinical_result = Mock()
        clinical_result.outcome = OUTCOME_SAFE
        clinical_result.blocked = False
        clinical_result.requires_acknowledgement = False
        clinical_result.requires_justification = False
        clinical_result.to_dict.return_value = {
            "outcome": "safe",
            "results": [],
        }

        monkeypatch.setattr(
            "app.core.clinical_safety.services.medication_safety_service.check_interactions",
            Mock(return_value=[]),
        )
        monkeypatch.setattr(
            "app.core.clinical_safety.services.medication_safety_service.evaluate_clinical_rules",
            Mock(return_value=clinical_result),
        )

        result = evaluate_medication_safety(
            clinic_id=1,
            medication_ids=[10],
        )

        payload = result.to_dict()

        assert payload["clinic_id"] == 1
        assert payload["medication_ids"] == [10]
        assert payload["known_interactions"] == []
        assert payload["outcome"] == "safe"
        assert payload["clinical_safety"]["outcome"] == "safe"