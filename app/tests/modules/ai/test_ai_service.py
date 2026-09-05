import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.enums.ai_enums import AIFeature, AIRiskLevel
from app.core.exceptions import NotFoundError, ValidationError
from app.modules.ai.models.ai_model import AILog
from app.modules.ai.services import ai_service
from app.modules.ai.services.ai_service import (
    _call_openai,
    _get_clinic,
    _get_patient,
    _run_feature,
    _validate_provider_result,
    assist_triage,
    check_drug_interactions,
    interpret_lab_results,
)

from app.modules.lab.models.lab_model import LabOrder


# ============================================================================
# HELPERS
# ============================================================================


def valid_provider_result(feature):
    if feature is AIFeature.DRUG_INTERACTION_CHECK:
        return {
            "summary": "AI test response",
            "interactions": [],
            "recommendations": [],
        }

    if feature is AIFeature.TRIAGE_ASSISTANT:
        return {
            "summary": "AI test response",
            "risk_score": "low",
            "recommendation": "Clinical review recommended",
        }

    if feature is AIFeature.LAB_RESULT_INTERPRETER:
        return {
            "summary": "AI test response",
            "interpretation": "Results reviewed",
            "abnormal_findings": [],
            "recommendations": [],
        }

    raise AssertionError(f"Unsupported test feature: {feature}")


def make_provider(feature):
    def provider(received_feature, payload):
        assert received_feature is feature
        return valid_provider_result(feature)

    return provider


def ai_log_count(db):
    return AILog.query.count()


# ============================================================================
# _get_clinic
# ============================================================================


class TestGetClinic:
    def test_returns_existing_clinic(self, clinic):
        result = _get_clinic(clinic.id)

        assert result.id == clinic.id
        assert result.name == clinic.name

    def test_missing_clinic_raises_not_found(self, app):
        with pytest.raises(
            NotFoundError,
            match=r"Clinic 999999 not found",
        ):
            _get_clinic(999999)


# ============================================================================
# _get_patient
# ============================================================================


class TestGetPatient:
    def test_none_patient_id_returns_none(self, clinic):
        result = _get_patient(
            clinic_id=clinic.id,
            patient_id=None,
        )

        assert result is None

    def test_returns_patient_from_same_clinic(
        self,
        clinic,
        patient,
    ):
        result = _get_patient(
            clinic_id=clinic.id,
            patient_id=patient.id,
        )

        assert result.id == patient.id

    def test_missing_patient_raises_not_found(self, clinic):
        with pytest.raises(
            NotFoundError,
            match=r"Patient 999999 not found",
        ):
            _get_patient(
                clinic_id=clinic.id,
                patient_id=999999,
            )

    def test_patient_from_another_clinic_raises_validation_error(
        self,
        make_clinic,
        make_patient,
    ):
        clinic_one = make_clinic(name="Clinic One")
        clinic_two = make_clinic(name="Clinic Two")

        patient_two = make_patient(clinic_two)

        with pytest.raises(
            ValidationError,
            match="Patient does not belong to the supplied clinic",
        ):
            _get_patient(
                clinic_id=clinic_one.id,
                patient_id=patient_two.id,
            )


# ============================================================================
# _validate_provider_result
# ============================================================================


class TestValidateProviderResult:
    def test_valid_drug_interaction_result(self):
        result = _validate_provider_result(
            AIFeature.DRUG_INTERACTION_CHECK,
            {
                "summary": "No major interactions found",
                "interactions": [],
                "recommendations": [],
            },
        )

        assert result == {
            "summary": "No major interactions found",
            "interactions": [],
            "recommendations": [],
        }

    @pytest.mark.parametrize(
        "risk_score",
        [
            AIRiskLevel.LOW.value,
            AIRiskLevel.MEDIUM.value,
            AIRiskLevel.HIGH.value,
            AIRiskLevel.CRITICAL.value,
        ],
    )
    def test_valid_triage_risk_scores(self, risk_score):
        result = _validate_provider_result(
            AIFeature.TRIAGE_ASSISTANT,
            {
                "summary": "Triage assessment",
                "risk_score": risk_score,
                "recommendation": "Clinical review recommended",
            },
        )

        assert result["risk_score"] == risk_score

    def test_valid_lab_interpreter_result(self):
        result = _validate_provider_result(
            AIFeature.LAB_RESULT_INTERPRETER,
            {
                "summary": "Lab interpretation",
                "interpretation": "Results reviewed",
                "abnormal_findings": [],
                "recommendations": [],
            },
        )

        assert result["interpretation"] == "Results reviewed"

    def test_invalid_triage_risk_score_raises_validation_error(self):
        with pytest.raises(
            ValidationError,
            match="AI provider returned invalid triage_assistant response",
        ):
            _validate_provider_result(
                AIFeature.TRIAGE_ASSISTANT,
                {
                    "summary": "Bad response",
                    "risk_score": "extreme",
                    "recommendation": "Review",
                },
            )

    def test_missing_triage_risk_score_raises_validation_error(self):
        with pytest.raises(
            ValidationError,
            match="AI provider returned invalid triage_assistant response",
        ):
            _validate_provider_result(
                AIFeature.TRIAGE_ASSISTANT,
                {
                    "summary": "Missing risk score",
                    "recommendation": "Review",
                },
            )

    def test_invalid_drug_interaction_field_type_raises_validation_error(
        self,
    ):
        with pytest.raises(
            ValidationError,
            match="AI provider returned invalid drug_interaction_check response",
        ):
            _validate_provider_result(
                AIFeature.DRUG_INTERACTION_CHECK,
                {
                    "summary": "Invalid response",
                    "interactions": "not-a-list",
                    "recommendations": [],
                },
            )

    def test_invalid_lab_interpreter_field_type_raises_validation_error(
        self,
    ):
        with pytest.raises(
            ValidationError,
            match="AI provider returned invalid lab_result_interpreter response",
        ):
            _validate_provider_result(
                AIFeature.LAB_RESULT_INTERPRETER,
                {
                    "summary": "Invalid response",
                    "interpretation": 123,
                    "abnormal_findings": [],
                    "recommendations": [],
                },
            )

    def test_non_dict_provider_result_is_rejected_by_run_feature(
        self,
        clinic,
    ):
        provider = Mock(return_value=["not", "a", "dict"])

        with pytest.raises(
            ValidationError,
            match="AI provider must return a JSON object",
        ):
            _run_feature(
                feature=AIFeature.DRUG_INTERACTION_CHECK,
                clinic_id=clinic.id,
                payload={
                    "drug_names": ["Aspirin", "Warfarin"],
                },
                provider=provider,
            )

        provider.assert_called_once()


# ============================================================================
# _run_feature
# ============================================================================


class TestRunFeature:
    def test_runs_feature_successfully(
        self,
        db,
        clinic,
    ):
        provider = Mock(
            return_value=valid_provider_result(
                AIFeature.DRUG_INTERACTION_CHECK
            )
        )

        result = _run_feature(
            feature=AIFeature.DRUG_INTERACTION_CHECK,
            clinic_id=clinic.id,
            payload={
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
            provider=provider,
        )

        assert result["summary"] == "AI test response"
        assert result["interactions"] == []
        assert result["recommendations"] == []

        provider.assert_called_once_with(
            AIFeature.DRUG_INTERACTION_CHECK,
            {
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
        )

        log = AILog.query.one()

        assert log.clinic_id == clinic.id
        assert log.patient_id is None
        assert log.user_id is None
        assert log.feature_used == AIFeature.DRUG_INTERACTION_CHECK
        assert log.input_data == {
            "drug_names": [
                "Aspirin",
                "Warfarin",
            ]
        }
        assert log.output_data["summary"] == "AI test response"
        assert log.credits_used == 1

        refreshed_clinic = db.session.get(
            type(clinic),
            clinic.id,
        )

        assert refreshed_clinic.ai_credits == 4

    def test_stores_patient_and_user_on_ai_log(
        self,
        db,
        clinic,
        patient,
        user,
    ):
        provider = Mock(
            return_value=valid_provider_result(
                AIFeature.DRUG_INTERACTION_CHECK
            )
        )

        result = _run_feature(
            feature=AIFeature.DRUG_INTERACTION_CHECK,
            clinic_id=clinic.id,
            payload={
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
            patient_id=patient.id,
            user_id=user.id,
            provider=provider,
        )

        assert result["summary"] == "AI test response"

        log = AILog.query.one()

        assert log.clinic_id == clinic.id
        assert log.patient_id == patient.id
        assert log.user_id == user.id

    def test_triage_updates_patient_ai_data(
        self,
        db,
        clinic,
        patient,
    ):
        provider = Mock(
            return_value={
                "summary": "Patient appears stable",
                "risk_score": "medium",
                "recommendation": "Monitor patient",
            }
        )

        result = _run_feature(
            feature=AIFeature.TRIAGE_ASSISTANT,
            clinic_id=clinic.id,
            payload={
                "symptoms": "Headache",
                "vitals": {
                    "temperature": 37.0,
                },
            },
            patient_id=patient.id,
            provider=provider,
        )

        assert result["risk_score"] == "medium"

        db.session.refresh(patient)

        assert patient.ai_triage_data == result
        assert patient.ai_summary == "Patient appears stable"
        assert patient.ai_risk_score == "medium"

    def test_triage_without_patient_does_not_update_patient(
        self,
        clinic,
    ):
        provider = Mock(
            return_value=valid_provider_result(
                AIFeature.TRIAGE_ASSISTANT
            )
        )

        result = _run_feature(
            feature=AIFeature.TRIAGE_ASSISTANT,
            clinic_id=clinic.id,
            payload={
                "symptoms": "Headache",
                "vitals": None,
            },
            patient_id=None,
            provider=provider,
        )

        assert result["risk_score"] == "low"

    def test_invalid_provider_output_does_not_create_ai_log(
        self,
        db,
        clinic,
    ):
        provider = Mock(
            return_value={
                "summary": "Invalid triage response",
                "risk_score": "invalid-risk",
            }
        )

        starting_credits = clinic.ai_credits

        with pytest.raises(
            ValidationError,
            match="AI provider returned invalid triage_assistant response",
        ):
            _run_feature(
                feature=AIFeature.TRIAGE_ASSISTANT,
                clinic_id=clinic.id,
                payload={
                    "symptoms": "Headache",
                    "vitals": None,
                },
                provider=provider,
            )

        assert ai_log_count(db) == 0

        db.session.refresh(clinic)

        assert clinic.ai_credits == starting_credits

    def test_provider_failure_rolls_back_ai_credit(
        self,
        db,
        clinic,
    ):
        provider = Mock(
            side_effect=ValidationError(
                "Provider failure"
            )
        )

        starting_credits = clinic.ai_credits

        with pytest.raises(
            ValidationError,
            match="Provider failure",
        ):
            _run_feature(
                feature=AIFeature.DRUG_INTERACTION_CHECK,
                clinic_id=clinic.id,
                payload={
                    "drug_names": [
                        "Aspirin",
                        "Warfarin",
                    ]
                },
                provider=provider,
            )

        assert ai_log_count(db) == 0

        db.session.refresh(clinic)

        assert clinic.ai_credits == starting_credits

    def test_invalid_provider_output_rolls_back_credit(
        self,
        db,
        clinic,
    ):
        provider = Mock(
            return_value={
                "summary": "Bad output",
                "risk_score": "not-valid",
            }
        )

        starting_credits = clinic.ai_credits

        with pytest.raises(ValidationError):
            _run_feature(
                feature=AIFeature.TRIAGE_ASSISTANT,
                clinic_id=clinic.id,
                payload={
                    "symptoms": "Headache",
                    "vitals": None,
                },
                provider=provider,
            )

        db.session.refresh(clinic)

        assert clinic.ai_credits == starting_credits
        assert ai_log_count(db) == 0

    def test_insufficient_ai_credits_prevents_provider_call(
        self,
        db,
        clinic,
    ):
        clinic.ai_credits = 0
        db.session.commit()

        provider = Mock(
            return_value=valid_provider_result(
                AIFeature.DRUG_INTERACTION_CHECK
            )
        )

        with pytest.raises(
            ValidationError,
            match="Insufficient AI credits",
        ):
            _run_feature(
                feature=AIFeature.DRUG_INTERACTION_CHECK,
                clinic_id=clinic.id,
                payload={
                    "drug_names": [
                        "Aspirin",
                        "Warfarin",
                    ]
                },
                provider=provider,
            )

        provider.assert_not_called()
        assert ai_log_count(db) == 0

    def test_missing_clinic_prevents_provider_call(
        self,
    ):
        provider = Mock(
            return_value=valid_provider_result(
                AIFeature.DRUG_INTERACTION_CHECK
            )
        )

        with pytest.raises(
            NotFoundError,
            match=r"Clinic 999999 not found",
        ):
            _run_feature(
                feature=AIFeature.DRUG_INTERACTION_CHECK,
                clinic_id=999999,
                payload={
                    "drug_names": [
                        "Aspirin",
                        "Warfarin",
                    ]
                },
                provider=provider,
            )

        provider.assert_not_called()


# ============================================================================
# check_drug_interactions
# ============================================================================


class TestCheckDrugInteractions:
    def test_checks_drug_interactions_successfully(
        self,
        clinic,
    ):
        provider = Mock(
            return_value=valid_provider_result(
                AIFeature.DRUG_INTERACTION_CHECK
            )
        )

        result = check_drug_interactions(
            clinic_id=clinic.id,
            drug_names=[
                "Aspirin",
                "Warfarin",
            ],
            provider=provider,
        )

        assert result["summary"] == "AI test response"

        provider.assert_called_once_with(
            AIFeature.DRUG_INTERACTION_CHECK,
            {
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
        )

    def test_strips_drug_names(
        self,
        clinic,
    ):
        provider = Mock(
            return_value=valid_provider_result(
                AIFeature.DRUG_INTERACTION_CHECK
            )
        )

        check_drug_interactions(
            clinic_id=clinic.id,
            drug_names=[
                "  Aspirin  ",
                " Warfarin ",
            ],
            provider=provider,
        )

        provider.assert_called_once_with(
            AIFeature.DRUG_INTERACTION_CHECK,
            {
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
        )

    def test_requires_at_least_two_drug_names(
        self,
        clinic,
    ):
        provider = Mock()

        with pytest.raises(
            ValidationError,
            match="At least two drug names are required",
        ):
            check_drug_interactions(
                clinic_id=clinic.id,
                drug_names=["Aspirin"],
                provider=provider,
            )

        provider.assert_not_called()

    @pytest.mark.parametrize(
        "drug_names",
        [
            [],
            None,
            "Aspirin, Warfarin",
            ("Aspirin", "Warfarin"),
        ],
    )
    def test_rejects_invalid_drug_names_container(
        self,
        clinic,
        drug_names,
    ):
        provider = Mock()

        with pytest.raises(
            ValidationError,
            match="At least two drug names are required",
        ):
            check_drug_interactions(
                clinic_id=clinic.id,
                drug_names=drug_names,
                provider=provider,
            )

        provider.assert_not_called()

    def test_requires_two_valid_drug_names_after_cleaning(
        self,
        clinic,
    ):
        provider = Mock()

        with pytest.raises(
            ValidationError,
            match="At least two valid drug names are required",
        ):
            check_drug_interactions(
                clinic_id=clinic.id,
                drug_names=[
                    "Aspirin",
                    "",
                    "   ",
                    None,
                ],
                provider=provider,
            )

        provider.assert_not_called()

    def test_ignores_non_string_drug_entries(
        self,
        clinic,
    ):
        provider = Mock(
            return_value=valid_provider_result(
                AIFeature.DRUG_INTERACTION_CHECK
            )
        )

        check_drug_interactions(
            clinic_id=clinic.id,
            drug_names=[
                "Aspirin",
                123,
                "Warfarin",
                None,
            ],
            provider=provider,
        )

        provider.assert_called_once_with(
            AIFeature.DRUG_INTERACTION_CHECK,
            {
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
        )

    def test_accepts_patient_and_user(
        self,
        clinic,
        patient,
        user,
    ):
        provider = Mock(
            return_value=valid_provider_result(
                AIFeature.DRUG_INTERACTION_CHECK
            )
        )

        check_drug_interactions(
            clinic_id=clinic.id,
            drug_names=[
                "Aspirin",
                "Warfarin",
            ],
            patient_id=patient.id,
            user_id=user.id,
            provider=provider,
        )

        log = AILog.query.one()

        assert log.patient_id == patient.id
        assert log.user_id == user.id

    def test_rejects_patient_from_another_clinic(
        self,
        make_clinic,
        make_patient,
    ):
        clinic_one = make_clinic(name="Clinic One")
        clinic_two = make_clinic(name="Clinic Two")
        patient_two = make_patient(clinic_two)

        provider = Mock()

        with pytest.raises(
            ValidationError,
            match="Patient does not belong to the supplied clinic",
        ):
            check_drug_interactions(
                clinic_id=clinic_one.id,
                drug_names=[
                    "Aspirin",
                    "Warfarin",
                ],
                patient_id=patient_two.id,
                provider=provider,
            )

        provider.assert_not_called()


# ============================================================================
# assist_triage
# ============================================================================


class TestAssistTriage:
    def test_assists_triage_successfully(
        self,
        clinic,
        patient,
    ):
        provider = Mock(
            return_value=valid_provider_result(
                AIFeature.TRIAGE_ASSISTANT
            )
        )

        result = assist_triage(
            clinic_id=clinic.id,
            patient_id=patient.id,
            symptoms="Mild headache and dizziness",
            vitals={
                "temperature": 37.0,
                "heart_rate": 72,
            },
            provider=provider,
        )

        assert result["risk_score"] == "low"

        provider.assert_called_once_with(
            AIFeature.TRIAGE_ASSISTANT,
            {
                "symptoms": "Mild headache and dizziness",
                "vitals": {
                    "temperature": 37.0,
                    "heart_rate": 72,
                },
            },
        )

    def test_strips_symptoms(
        self,
        clinic,
        patient,
    ):
        provider = Mock(
            return_value=valid_provider_result(
                AIFeature.TRIAGE_ASSISTANT
            )
        )

        assist_triage(
            clinic_id=clinic.id,
            patient_id=patient.id,
            symptoms="   Headache and dizziness   ",
            provider=provider,
        )

        provider.assert_called_once_with(
            AIFeature.TRIAGE_ASSISTANT,
            {
                "symptoms": "Headache and dizziness",
                "vitals": None,
            },
        )

    @pytest.mark.parametrize(
        "symptoms",
        [
            "",
            "   ",
            None,
            123,
            [],
            {},
        ],
    )
    def test_requires_symptoms(
        self,
        clinic,
        patient,
        symptoms,
    ):
        provider = Mock()

        with pytest.raises(
            ValidationError,
            match="Symptoms are required",
        ):
            assist_triage(
                clinic_id=clinic.id,
                patient_id=patient.id,
                symptoms=symptoms,
                provider=provider,
            )

        provider.assert_not_called()

    @pytest.mark.parametrize(
        "vitals",
        [
            "37",
            37,
            [],
            ("temperature", 37),
            True,
        ],
    )
    def test_rejects_non_dict_vitals(
        self,
        clinic,
        patient,
        vitals,
    ):
        provider = Mock()

        with pytest.raises(
            ValidationError,
            match="Vitals must be provided as an object",
        ):
            assist_triage(
                clinic_id=clinic.id,
                patient_id=patient.id,
                symptoms="Headache",
                vitals=vitals,
                provider=provider,
            )

        provider.assert_not_called()

    def test_allows_vitals_to_be_omitted(
        self,
        clinic,
        patient,
    ):
        provider = Mock(
            return_value=valid_provider_result(
                AIFeature.TRIAGE_ASSISTANT
            )
        )

        result = assist_triage(
            clinic_id=clinic.id,
            patient_id=patient.id,
            symptoms="Headache",
            provider=provider,
        )

        assert result["risk_score"] == "low"

        provider.assert_called_once_with(
            AIFeature.TRIAGE_ASSISTANT,
            {
                "symptoms": "Headache",
                "vitals": None,
            },
        )

    def test_patient_must_belong_to_clinic(
        self,
        make_clinic,
        make_patient,
    ):
        clinic_one = make_clinic(name="Clinic One")
        clinic_two = make_clinic(name="Clinic Two")
        patient_two = make_patient(clinic_two)

        provider = Mock()

        with pytest.raises(
            ValidationError,
            match="Patient does not belong to the supplied clinic",
        ):
            assist_triage(
                clinic_id=clinic_one.id,
                patient_id=patient_two.id,
                symptoms="Headache",
                provider=provider,
            )

        provider.assert_not_called()

    def test_missing_patient_is_rejected(
        self,
        clinic,
    ):
        provider = Mock()

        with pytest.raises(
            NotFoundError,
            match=r"Patient 999999 not found",
        ):
            assist_triage(
                clinic_id=clinic.id,
                patient_id=999999,
                symptoms="Headache",
                provider=provider,
            )

        provider.assert_not_called()

    @pytest.mark.parametrize(
        "risk_score",
        [
            "low",
            "medium",
            "high",
            "critical",
        ],
    )
    def test_persists_valid_risk_score(
        self,
        db,
        clinic,
        patient,
        risk_score,
    ):
        provider = Mock(
            return_value={
                "summary": "Triage result",
                "risk_score": risk_score,
                "recommendation": "Clinical review recommended",
            }
        )

        result = assist_triage(
            clinic_id=clinic.id,
            patient_id=patient.id,
            symptoms="Chest discomfort",
            provider=provider,
        )

        assert result["risk_score"] == risk_score

        db.session.refresh(patient)

        assert patient.ai_risk_score == risk_score
        assert patient.ai_summary == "Triage result"
        assert patient.ai_triage_data == result

    def test_invalid_risk_score_does_not_persist_patient_data(
        self,
        db,
        clinic,
        patient,
    ):
        provider = Mock(
            return_value={
                "summary": "Invalid result",
                "risk_score": "extreme",
                "recommendation": "Review",
            }
        )

        starting_credits = clinic.ai_credits

        with pytest.raises(
            ValidationError,
            match="AI provider returned invalid triage_assistant response",
        ):
            assist_triage(
                clinic_id=clinic.id,
                patient_id=patient.id,
                symptoms="Headache",
                provider=provider,
            )

        db.session.refresh(patient)
        db.session.refresh(clinic)

        assert patient.ai_triage_data is None
        assert patient.ai_summary is None
        assert patient.ai_risk_score is None
        assert clinic.ai_credits == starting_credits
        assert AILog.query.count() == 0


# ============================================================================
# interpret_lab_results
# ============================================================================


class TestInterpretLabResults:
    def test_interprets_lab_results_successfully(
        self,
        clinic,
    ):
        provider = Mock(
            return_value=valid_provider_result(
                AIFeature.LAB_RESULT_INTERPRETER
            )
        )

        result = interpret_lab_results(
            clinic_id=clinic.id,
            result_data={
                "hemoglobin": 13.5,
                "glucose": 95,
            },
            provider=provider,
        )

        assert result["summary"] == "AI test response"
        assert result["interpretation"] == "Results reviewed"

        provider.assert_called_once_with(
            AIFeature.LAB_RESULT_INTERPRETER,
            {
                "result_data": {
                    "hemoglobin": 13.5,
                    "glucose": 95,
                },
                "lab_order_id": None,
            },
        )

    def test_requires_result_data(
        self,
        clinic,
    ):
        provider = Mock()

        with pytest.raises(
            ValidationError,
            match="Result data is required",
        ):
            interpret_lab_results(
                clinic_id=clinic.id,
                result_data={},
                provider=provider,
            )

        provider.assert_not_called()

    @pytest.mark.parametrize(
        "result_data",
        [
            None,
            "",
            [],
            (),
            123,
            True,
        ],
    )
    def test_rejects_non_dict_result_data(
        self,
        clinic,
        result_data,
    ):
        provider = Mock()

        with pytest.raises(
            ValidationError,
            match="Result data is required",
        ):
            interpret_lab_results(
                clinic_id=clinic.id,
                result_data=result_data,
                provider=provider,
            )

        provider.assert_not_called()

    def test_accepts_patient_id(
        self,
        clinic,
        patient,
    ):
        provider = Mock(
            return_value=valid_provider_result(
                AIFeature.LAB_RESULT_INTERPRETER
            )
        )

        interpret_lab_results(
            clinic_id=clinic.id,
            result_data={
                "hemoglobin": 13.5,
            },
            patient_id=patient.id,
            provider=provider,
        )

        log = AILog.query.one()

        assert log.patient_id == patient.id

    def test_rejects_patient_from_another_clinic(
        self,
        make_clinic,
        make_patient,
    ):
        clinic_one = make_clinic(name="Clinic One")
        clinic_two = make_clinic(name="Clinic Two")
        patient_two = make_patient(clinic_two)

        provider = Mock()

        with pytest.raises(
            ValidationError,
            match="Patient does not belong to the supplied clinic",
        ):
            interpret_lab_results(
                clinic_id=clinic_one.id,
                result_data={
                    "glucose": 100,
                },
                patient_id=patient_two.id,
                provider=provider,
            )

        provider.assert_not_called()

    def test_missing_lab_order_raises_not_found(
        self,
        clinic,
    ):
        provider = Mock()

        with pytest.raises(
            NotFoundError,
            match=r"Lab order 999999 not found",
        ):
            interpret_lab_results(
                clinic_id=clinic.id,
                result_data={
                    "glucose": 100,
                },
                lab_order_id=999999,
                provider=provider,
            )

        provider.assert_not_called()

    def test_lab_order_from_another_clinic_is_rejected(
        self,
        db,
        make_clinic,
    ):
        """
        This test avoids depending on the exact LabOrder constructor
        by mocking the service's database lookup.
        """

        clinic_one = make_clinic(name="Clinic One")
        clinic_two = make_clinic(name="Clinic Two")

        fake_lab_order = SimpleNamespace(
            id=10,
            clinic_id=clinic_two.id,
            patient_id=None,
        )

        original_get = ai_service.db.session.get

        def fake_get(model, object_id):
            if model is LabOrder and object_id == 10:
                return fake_lab_order

            return original_get(model, object_id)

        db.session.get = fake_get

        provider = Mock()

        try:
            with pytest.raises(
                ValidationError,
                match="Lab order does not belong to the supplied clinic",
            ):
                interpret_lab_results(
                    clinic_id=clinic_one.id,
                    result_data={
                        "glucose": 100,
                    },
                    lab_order_id=10,
                    provider=provider,
                )
        finally:
            db.session.get = original_get

        provider.assert_not_called()

    def test_lab_order_patient_mismatch_is_rejected(
        self,
        db,
        clinic,
        patient,
    ):
        fake_lab_order = SimpleNamespace(
            id=10,
            clinic_id=clinic.id,
            patient_id=patient.id + 999,
        )

        original_get = ai_service.db.session.get

        def fake_get(model, object_id):
            if model is LabOrder and object_id == 10:
                return fake_lab_order

            return original_get(model, object_id)

        db.session.get = fake_get

        provider = Mock()

        try:
            with pytest.raises(
                ValidationError,
                match="Lab order does not belong to the supplied patient",
            ):
                interpret_lab_results(
                    clinic_id=clinic.id,
                    result_data={
                        "glucose": 100,
                    },
                    patient_id=patient.id,
                    lab_order_id=10,
                    provider=provider,
                )
        finally:
            db.session.get = original_get

        provider.assert_not_called()

    def test_lab_order_sets_patient_from_lab_order(
        self,
        db,
        clinic,
        patient,
    ):
        fake_lab_order = SimpleNamespace(
            id=10,
            clinic_id=clinic.id,
            patient_id=patient.id,
        )

        original_get = ai_service.db.session.get

        def fake_get(model, object_id):
            if model is LabOrder and object_id == 10:
                return fake_lab_order

            return original_get(model, object_id)

        db.session.get = fake_get

        provider = Mock(
            return_value=valid_provider_result(
                AIFeature.LAB_RESULT_INTERPRETER
            )
        )

        try:
            result = interpret_lab_results(
                clinic_id=clinic.id,
                result_data={
                    "glucose": 100,
                },
                lab_order_id=10,
                provider=provider,
            )
        finally:
            db.session.get = original_get

        assert result["interpretation"] == "Results reviewed"

        provider.assert_called_once_with(
            AIFeature.LAB_RESULT_INTERPRETER,
            {
                "result_data": {
                    "glucose": 100,
                },
                "lab_order_id": 10,
            },
        )

        log = AILog.query.one()

        assert log.patient_id == patient.id

    def test_lab_order_can_be_used_without_patient_id(
        self,
        db,
        clinic,
        patient,
    ):
        fake_lab_order = SimpleNamespace(
            id=10,
            clinic_id=clinic.id,
            patient_id=patient.id,
        )

        original_get = ai_service.db.session.get

        def fake_get(model, object_id):
            if model is LabOrder and object_id == 10:
                return fake_lab_order

            return original_get(model, object_id)

        db.session.get = fake_get

        provider = Mock(
            return_value=valid_provider_result(
                AIFeature.LAB_RESULT_INTERPRETER
            )
        )

        try:
            interpret_lab_results(
                clinic_id=clinic.id,
                result_data={
                    "glucose": 100,
                },
                lab_order_id=10,
                provider=provider,
            )
        finally:
            db.session.get = original_get

        log = AILog.query.one()

        assert log.patient_id == patient.id

    def test_invalid_lab_provider_output_rolls_back(
        self,
        db,
        clinic,
    ):
        provider = Mock(
            return_value={
                "summary": "Invalid lab response",
                "interpretation": 12345,
                "abnormal_findings": [],
                "recommendations": [],
            }
        )

        starting_credits = clinic.ai_credits

        with pytest.raises(
            ValidationError,
            match="AI provider returned invalid lab_result_interpreter response",
        ):
            interpret_lab_results(
                clinic_id=clinic.id,
                result_data={
                    "glucose": 100,
                },
                provider=provider,
            )

        db.session.refresh(clinic)

        assert clinic.ai_credits == starting_credits
        assert AILog.query.count() == 0


# ============================================================================
# _call_openai
# ============================================================================


class TestCallOpenAI:
    def test_requires_api_key(
        self,
        app,
    ):
        app.config["OPENAI_API_KEY"] = None

        with app.app_context():
            with pytest.raises(
                ValidationError,
                match="OPENAI_API_KEY is not configured",
            ):
                _call_openai(
                    AIFeature.DRUG_INTERACTION_CHECK,
                    {
                        "drug_names": [
                            "Aspirin",
                            "Warfarin",
                        ]
                    },
                )

    def test_rejects_missing_openai_package(
        self,
        app,
        monkeypatch,
    ):
        app.config["OPENAI_API_KEY"] = "test-key"

        real_import = __import__

        def fake_import(
            name,
            globals=None,
            locals=None,
            fromlist=(),
            level=0,
        ):
            if name == "openai":
                raise ImportError("openai missing")

            return real_import(
                name,
                globals,
                locals,
                fromlist,
                level,
            )

        monkeypatch.setattr(
            "builtins.__import__",
            fake_import,
        )

        with app.app_context():
            with pytest.raises(
                ValidationError,
                match="The OpenAI package is not installed",
            ):
                _call_openai(
                    AIFeature.DRUG_INTERACTION_CHECK,
                    {
                        "drug_names": [
                            "Aspirin",
                            "Warfarin",
                        ]
                    },
                )

    def test_returns_parsed_json_object(
        self,
        app,
        monkeypatch,
    ):
        app.config["OPENAI_API_KEY"] = "test-key"
        app.config["OPENAI_MODEL"] = "test-model"

        captured = {}

        class FakeCompletions:
            def create(self, **kwargs):
                captured["kwargs"] = kwargs

                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content=json.dumps(
                                    {
                                        "summary": "No interaction",
                                        "interactions": [],
                                        "recommendations": [],
                                    }
                                )
                            )
                        )
                    ]
                )

        class FakeClient:
            def __init__(self, api_key):
                captured["api_key"] = api_key
                self.chat = SimpleNamespace(
                    completions=FakeCompletions()
                )

        fake_openai = SimpleNamespace(
            OpenAI=FakeClient
        )

        monkeypatch.setitem(
            __import__("sys").modules,
            "openai",
            fake_openai,
        )

        with app.app_context():
            result = _call_openai(
                AIFeature.DRUG_INTERACTION_CHECK,
                {
                    "drug_names": [
                        "Aspirin",
                        "Warfarin",
                    ]
                },
            )

        assert result == {
            "summary": "No interaction",
            "interactions": [],
            "recommendations": [],
        }

        assert captured["api_key"] == "test-key"

        request_kwargs = captured["kwargs"]

        assert request_kwargs["model"] == "test-model"
        assert request_kwargs["response_format"] == {
            "type": "json_object"
        }

        assert request_kwargs["messages"][0]["role"] == "system"
        assert request_kwargs["messages"][1]["role"] == "user"

    def test_rejects_empty_choices(
        self,
        app,
        monkeypatch,
    ):
        app.config["OPENAI_API_KEY"] = "test-key"

        class FakeCompletions:
            def create(self, **kwargs):
                return SimpleNamespace(
                    choices=[]
                )

        class FakeClient:
            def __init__(self, api_key):
                self.chat = SimpleNamespace(
                    completions=FakeCompletions()
                )

        monkeypatch.setitem(
            __import__("sys").modules,
            "openai",
            SimpleNamespace(
                OpenAI=FakeClient
            ),
        )

        with app.app_context():
            with pytest.raises(
                ValidationError,
                match="AI provider returned no choices",
            ):
                _call_openai(
                    AIFeature.DRUG_INTERACTION_CHECK,
                    {
                        "drug_names": [
                            "Aspirin",
                            "Warfarin",
                        ]
                    },
                )

    def test_rejects_empty_content(
        self,
        app,
        monkeypatch,
    ):
        app.config["OPENAI_API_KEY"] = "test-key"

        class FakeCompletions:
            def create(self, **kwargs):
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content=""
                            )
                        )
                    ]
                )

        class FakeClient:
            def __init__(self, api_key):
                self.chat = SimpleNamespace(
                    completions=FakeCompletions()
                )

        monkeypatch.setitem(
            __import__("sys").modules,
            "openai",
            SimpleNamespace(
                OpenAI=FakeClient
            ),
        )

        with app.app_context():
            with pytest.raises(
                ValidationError,
                match="AI provider returned an empty response",
            ):
                _call_openai(
                    AIFeature.DRUG_INTERACTION_CHECK,
                    {
                        "drug_names": [
                            "Aspirin",
                            "Warfarin",
                        ]
                    },
                )

    def test_rejects_invalid_json(
        self,
        app,
        monkeypatch,
    ):
        app.config["OPENAI_API_KEY"] = "test-key"

        class FakeCompletions:
            def create(self, **kwargs):
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content="not valid json"
                            )
                        )
                    ]
                )

        class FakeClient:
            def __init__(self, api_key):
                self.chat = SimpleNamespace(
                    completions=FakeCompletions()
                )

        monkeypatch.setitem(
            __import__("sys").modules,
            "openai",
            SimpleNamespace(
                OpenAI=FakeClient
            ),
        )

        with app.app_context():
            with pytest.raises(
                ValidationError,
                match="AI provider returned invalid JSON",
            ):
                _call_openai(
                    AIFeature.DRUG_INTERACTION_CHECK,
                    {
                        "drug_names": [
                            "Aspirin",
                            "Warfarin",
                        ]
                    },
                )

    @pytest.mark.parametrize(
        "content",
        [
            "[]",
            '"string"',
            "123",
            "true",
            "null",
        ],
    )
    def test_rejects_non_object_json(
        self,
        app,
        monkeypatch,
        content,
    ):
        app.config["OPENAI_API_KEY"] = "test-key"

        class FakeCompletions:
            def create(self, **kwargs):
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content=content
                            )
                        )
                    ]
                )

        class FakeClient:
            def __init__(self, api_key):
                self.chat = SimpleNamespace(
                    completions=FakeCompletions()
                )

        monkeypatch.setitem(
            __import__("sys").modules,
            "openai",
            SimpleNamespace(
                OpenAI=FakeClient
            ),
        )

        with app.app_context():
            with pytest.raises(
                ValidationError,
                match="AI provider must return a JSON object",
            ):
                _call_openai(
                    AIFeature.DRUG_INTERACTION_CHECK,
                    {
                        "drug_names": [
                            "Aspirin",
                            "Warfarin",
                        ]
                    },
                )