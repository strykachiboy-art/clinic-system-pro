from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.core.enums.ai_enums import (
    AIFeature,
    AIApprovalStatus,
    AIRiskLevel,
)
from app.core.exceptions import NotFoundError, ValidationError
from app.extensions import db
from app.modules.ai.models.ai_model import AILog
from app.modules.ai.services import ai_service


# ============================================================================
# HELPERS
# ============================================================================


def make_drug_result(**overrides):
    result = {
        "summary": "No clinically significant interaction found.",
        "interactions": [],
        "recommendations": ["Continue routine monitoring."],
    }
    result.update(overrides)
    return result


def make_triage_result(**overrides):
    result = {
        "summary": "Patient requires clinical assessment.",
        "risk_score": AIRiskLevel.MEDIUM.value,
        "recommendation": "Arrange clinical review.",
    }
    result.update(overrides)
    return result


def make_lab_result(**overrides):
    result = {
        "summary": "Laboratory results reviewed.",
        "interpretation": "Results require clinical correlation.",
        "abnormal_findings": [],
        "recommendations": [
            "Review results with the treating clinician."
        ],
    }
    result.update(overrides)
    return result


def make_provider(result):
    def provider(feature, payload):
        return result

    return provider


# ============================================================================
# CONFIGURATION HELPERS
# ============================================================================


def test_get_model_name_returns_configured_model(app):
    with app.app_context():
        app.config["OPENAI_MODEL"] = "custom-model"

        assert ai_service._get_model_name() == "custom-model"


def test_get_model_name_uses_default(app):
    with app.app_context():
        app.config.pop("OPENAI_MODEL", None)

        assert ai_service._get_model_name() == "gpt-4o-mini"


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        123,
        [],
    ],
)
def test_get_model_name_rejects_invalid_configuration(app, value):
    with app.app_context():
        app.config["OPENAI_MODEL"] = value

        with pytest.raises(
            ValidationError,
            match="OPENAI_MODEL is not configured",
        ):
            ai_service._get_model_name()


def test_get_model_version_returns_configured_value(app):
    with app.app_context():
        app.config["OPENAI_MODEL_VERSION"] = "2026-01"

        assert ai_service._get_model_version() == "2026-01"


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
    ],
)
def test_get_model_version_returns_none_when_missing_or_blank(
    app,
    value,
):
    with app.app_context():
        app.config["OPENAI_MODEL_VERSION"] = value

        assert ai_service._get_model_version() is None


def test_get_model_version_rejects_non_string(app):
    with app.app_context():
        app.config["OPENAI_MODEL_VERSION"] = 123

        with pytest.raises(
            ValidationError,
            match="OPENAI_MODEL_VERSION must be a string",
        ):
            ai_service._get_model_version()


def test_get_input_context_version_returns_configured_value(app):
    with app.app_context():
        app.config["AI_INPUT_CONTEXT_VERSION"] = "v2"

        assert ai_service._get_input_context_version() == "v2"


def test_get_input_context_version_defaults_to_v1(app):
    with app.app_context():
        app.config.pop("AI_INPUT_CONTEXT_VERSION", None)

        assert ai_service._get_input_context_version() == "v1"


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
    ],
)
def test_get_input_context_version_rejects_invalid_configuration(
    app,
    value,
):
    with app.app_context():
        app.config["AI_INPUT_CONTEXT_VERSION"] = value

        with pytest.raises(
            ValidationError,
            match="AI_INPUT_CONTEXT_VERSION must be a non-empty string",
        ):
            ai_service._get_input_context_version()


# ============================================================================
# PAYLOAD HELPERS
# ============================================================================


def test_build_provider_payload_serializes_feature_and_data():
    payload = {
        "drug_names": ["Aspirin", "Warfarin"],
    }

    result = ai_service._build_provider_payload(
        AIFeature.DRUG_INTERACTION_CHECK,
        payload,
    )

    parsed = json.loads(result)

    assert parsed["feature"] == AIFeature.DRUG_INTERACTION_CHECK.value
    assert parsed["data"] == payload


def test_build_provider_payload_preserves_unicode():
    payload = {
        "symptoms": "Fever with café-au-lait findings",
    }

    result = ai_service._build_provider_payload(
        AIFeature.TRIAGE_ASSISTANT,
        payload,
    )

    assert "café" in result


# ============================================================================
# RISK HELPERS
# ============================================================================


@pytest.mark.parametrize(
    "risk_value,expected",
    [
        (AIRiskLevel.LOW.value, AIRiskLevel.LOW),
        (AIRiskLevel.MEDIUM.value, AIRiskLevel.MEDIUM),
        (AIRiskLevel.HIGH.value, AIRiskLevel.HIGH),
        (AIRiskLevel.CRITICAL.value, AIRiskLevel.CRITICAL),
    ],
)
def test_determine_triage_risk_level(risk_value, expected):
    result = {
        "risk_score": risk_value,
    }

    assert (
        ai_service._determine_risk_level(
            AIFeature.TRIAGE_ASSISTANT,
            result,
        )
        == expected
    )


def test_determine_risk_level_rejects_invalid_triage_risk():
    with pytest.raises(
        ValidationError,
        match="AI triage response contains an invalid risk level",
    ):
        ai_service._determine_risk_level(
            AIFeature.TRIAGE_ASSISTANT,
            {
                "risk_score": "not-valid",
            },
        )


@pytest.mark.parametrize(
    "feature",
    [
        AIFeature.DRUG_INTERACTION_CHECK,
        AIFeature.LAB_RESULT_INTERPRETER,
    ],
)
def test_non_triage_features_use_medium_risk(feature):
    assert (
        ai_service._determine_risk_level(
            feature,
            {},
        )
        == AIRiskLevel.MEDIUM
    )


@pytest.mark.parametrize(
    "risk_level,expected",
    [
        (AIRiskLevel.LOW, False),
        (AIRiskLevel.MEDIUM, False),
        (AIRiskLevel.HIGH, True),
        (AIRiskLevel.CRITICAL, True),
    ],
)
def test_requires_human_review(risk_level, expected):
    assert ai_service._requires_human_review(risk_level) is expected


# ============================================================================
# USAGE EXTRACTION
# ============================================================================


def test_extract_usage_returns_token_counts():
    response = SimpleNamespace(
        usage=SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )
    )

    assert ai_service._extract_usage(response) == (
        10,
        20,
        30,
    )


def test_extract_usage_returns_none_when_usage_missing():
    response = SimpleNamespace()

    assert ai_service._extract_usage(response) == (
        None,
        None,
        None,
    )


def test_extract_usage_returns_none_when_usage_is_none():
    response = SimpleNamespace(usage=None)

    assert ai_service._extract_usage(response) == (
        None,
        None,
        None,
    )


# ============================================================================
# RESPONSE VALIDATION
# ============================================================================


def test_validate_drug_provider_result():
    result = ai_service._validate_provider_result(
        AIFeature.DRUG_INTERACTION_CHECK,
        make_drug_result(),
    )

    assert result["summary"] == (
        "No clinically significant interaction found."
    )
    assert result["interactions"] == []
    assert result["recommendations"] == [
        "Continue routine monitoring."
    ]


def test_validate_drug_provider_result_allows_summary_only():
    result = ai_service._validate_provider_result(
        AIFeature.DRUG_INTERACTION_CHECK,
        {
            "summary": "No interaction detected.",
        },
    )

    assert result == {
        "summary": "No interaction detected.",
        "interactions": None,
        "recommendations": None,
    }


def test_validate_triage_provider_result():
    result = ai_service._validate_provider_result(
        AIFeature.TRIAGE_ASSISTANT,
        make_triage_result(),
    )

    assert result["risk_score"] == AIRiskLevel.MEDIUM.value
    assert result["recommendation"] == "Arrange clinical review."


def test_validate_triage_provider_result_rejects_missing_risk_score():
    with pytest.raises(
        ValidationError,
        match="AI provider returned invalid triage_assistant response",
    ):
        ai_service._validate_provider_result(
            AIFeature.TRIAGE_ASSISTANT,
            {
                "summary": "Missing risk score",
            },
        )


def test_validate_triage_provider_result_rejects_invalid_risk_score():
    with pytest.raises(
        ValidationError,
        match="AI provider returned invalid triage_assistant response",
    ):
        ai_service._validate_provider_result(
            AIFeature.TRIAGE_ASSISTANT,
            {
                "summary": "Invalid risk score",
                "risk_score": "not-a-real-risk-level",
            },
        )


def test_validate_lab_provider_result():
    result = ai_service._validate_provider_result(
        AIFeature.LAB_RESULT_INTERPRETER,
        make_lab_result(),
    )

    assert result["summary"] == "Laboratory results reviewed."
    assert result["interpretation"] == (
        "Results require clinical correlation."
    )


def test_validate_lab_provider_result_allows_summary_only():
    result = ai_service._validate_provider_result(
        AIFeature.LAB_RESULT_INTERPRETER,
        {
            "summary": "Results reviewed.",
        },
    )

    assert result == {
        "summary": "Results reviewed.",
        "interpretation": None,
        "abnormal_findings": None,
        "recommendations": None,
    }


def test_validate_provider_result_rejects_unsupported_feature():
    class FakeFeature:
        value = "unsupported_feature"

    with pytest.raises(
        ValidationError,
        match="Unsupported AI feature 'unsupported_feature'",
    ):
        ai_service._validate_provider_result(
            FakeFeature(),
            {},
        )


# ============================================================================
# ENTITY LOOKUPS
# ============================================================================


def test_get_clinic_returns_clinic(app, clinic):
    with app.app_context():
        result = ai_service._get_clinic(clinic.id)

        assert result.id == clinic.id


def test_get_clinic_raises_not_found(app):
    with app.app_context():
        with pytest.raises(
            NotFoundError,
            match="Clinic 99999 not found",
        ):
            ai_service._get_clinic(99999)


def test_get_patient_returns_none_when_patient_id_is_none(
    app,
    clinic,
):
    with app.app_context():
        assert (
            ai_service._get_patient(
                clinic.id,
                None,
            )
            is None
        )


def test_get_patient_returns_patient(app, clinic, patient):
    with app.app_context():
        result = ai_service._get_patient(
            clinic.id,
            patient.id,
        )

        assert result.id == patient.id


def test_get_patient_raises_not_found(app, clinic):
    with app.app_context():
        with pytest.raises(
            NotFoundError,
            match="Patient 99999 not found",
        ):
            ai_service._get_patient(
                clinic.id,
                99999,
            )


def test_get_patient_rejects_cross_clinic_patient(
    app,
    clinic,
    make_clinic,
    make_patient,
):
    with app.app_context():
        other_clinic = make_clinic()
        other_patient = make_patient(other_clinic)

        with pytest.raises(
            ValidationError,
            match="Patient does not belong to the authenticated clinic",
        ):
            ai_service._get_patient(
                clinic.id,
                other_patient.id,
            )


def test_get_lab_order_returns_order(
    app,
    clinic,
    patient,
    staff,
    make_lab_test,
    make_lab_order,
):
    with app.app_context():
        lab_test = make_lab_test(clinic)

        order = make_lab_order(
            clinic,
            patient,
            staff,
            [lab_test],
        )

        result = ai_service._get_lab_order(
            clinic.id,
            order.id,
        )

        assert result.id == order.id


def test_get_lab_order_raises_not_found(app, clinic):
    with app.app_context():
        with pytest.raises(
            NotFoundError,
            match="Lab order 99999 not found",
        ):
            ai_service._get_lab_order(
                clinic.id,
                99999,
            )


def test_get_lab_order_rejects_cross_clinic_order(
    app,
    clinic,
    patient,
    staff,
    make_clinic,
    make_patient,
    make_lab_test,
    make_lab_order,
):
    with app.app_context():
        other_clinic = make_clinic()
        other_patient = make_patient(other_clinic)
        other_test = make_lab_test(other_clinic)

        other_order = make_lab_order(
            other_clinic,
            other_patient,
            staff,
            [other_test],
        )

        with pytest.raises(
            ValidationError,
            match="Lab order does not belong to the authenticated clinic",
        ):
            ai_service._get_lab_order(
                clinic.id,
                other_order.id,
            )


# ============================================================================
# DRUG INTERACTION
# ============================================================================


def test_check_drug_interactions_requires_at_least_two_drugs(
    app,
    clinic,
):
    with app.app_context():
        with pytest.raises(
            ValidationError,
            match="At least two drug names are required",
        ):
            ai_service.check_drug_interactions(
                clinic.id,
                ["Aspirin"],
            )


def test_check_drug_interactions_requires_valid_drug_names(
    app,
    clinic,
):
    with app.app_context():
        with pytest.raises(
            ValidationError,
            match="At least two valid drug names are required",
        ):
            ai_service.check_drug_interactions(
                clinic.id,
                [" ", "", None],
            )


def test_check_drug_interactions_strips_drug_names(
    app,
    clinic,
    monkeypatch,
):
    with app.app_context():
        captured = {}

        def provider(feature, payload):
            captured["feature"] = feature
            captured["payload"] = payload
            return make_drug_result()

        monkeypatch.setattr(
            ai_service,
            "consume_ai_credit",
            lambda clinic_id: None,
        )

        result = ai_service.check_drug_interactions(
            clinic.id,
            [
                " Aspirin ",
                " Warfarin ",
            ],
            provider=provider,
        )

        assert result["summary"] == (
            "No clinically significant interaction found."
        )
        assert captured["feature"] == (
            AIFeature.DRUG_INTERACTION_CHECK
        )
        assert captured["payload"] == {
            "drug_names": [
                "Aspirin",
                "Warfarin",
            ]
        }


def test_check_drug_interactions_accepts_patient(
    app,
    clinic,
    patient,
    monkeypatch,
):
    with app.app_context():
        monkeypatch.setattr(
            ai_service,
            "consume_ai_credit",
            lambda clinic_id: None,
        )

        result = ai_service.check_drug_interactions(
            clinic.id,
            ["Aspirin", "Warfarin"],
            patient_id=patient.id,
            provider=make_provider(make_drug_result()),
        )

        assert result["summary"] == (
            "No clinically significant interaction found."
        )

        logs = db.session.scalars(
            db.select(AILog).where(
                AILog.clinic_id == clinic.id,
                AILog.patient_id == patient.id,
                AILog.feature_used
                == AIFeature.DRUG_INTERACTION_CHECK,
            )
        ).all()

        assert len(logs) == 1


# ============================================================================
# TRIAGE
# ============================================================================


def test_assist_triage_requires_symptoms(
    app,
    clinic,
    patient,
):
    with app.app_context():
        with pytest.raises(
            ValidationError,
            match="Symptoms are required",
        ):
            ai_service.assist_triage(
                clinic.id,
                patient.id,
                "   ",
            )


def test_assist_triage_rejects_non_dict_vitals(
    app,
    clinic,
    patient,
):
    with app.app_context():
        with pytest.raises(
            ValidationError,
            match="Vitals must be provided as an object",
        ):
            ai_service.assist_triage(
                clinic.id,
                patient.id,
                "Fever",
                vitals="invalid",
            )


def test_assist_triage_strips_symptoms(
    app,
    clinic,
    patient,
    monkeypatch,
):
    with app.app_context():
        captured = {}

        def provider(feature, payload):
            captured["feature"] = feature
            captured["payload"] = payload
            return make_triage_result()

        monkeypatch.setattr(
            ai_service,
            "consume_ai_credit",
            lambda clinic_id: None,
        )

        result = ai_service.assist_triage(
            clinic.id,
            patient.id,
            "  Fever and cough  ",
            vitals={
                "temperature": 38.5,
            },
            provider=provider,
        )

        assert result["risk_score"] == AIRiskLevel.MEDIUM.value
        assert captured["feature"] == AIFeature.TRIAGE_ASSISTANT
        assert captured["payload"] == {
            "symptoms": "Fever and cough",
            "vitals": {
                "temperature": 38.5,
            },
        }


def test_assist_triage_creates_pending_log(
    app,
    clinic,
    patient,
    user,
    monkeypatch,
):
    with app.app_context():
        monkeypatch.setattr(
            ai_service,
            "consume_ai_credit",
            lambda clinic_id: None,
        )

        ai_service.assist_triage(
            clinic.id,
            patient.id,
            "Chest pain",
            user_id=user.id,
            provider=make_provider(
                make_triage_result(
                    risk_score=AIRiskLevel.HIGH.value,
                )
            ),
        )

        log = db.session.scalars(
            db.select(AILog).where(
                AILog.clinic_id == clinic.id,
                AILog.patient_id == patient.id,
                AILog.feature_used
                == AIFeature.TRIAGE_ASSISTANT,
            )
        ).one()

        assert log.risk_level == AIRiskLevel.HIGH
        assert log.approval_status == AIApprovalStatus.PENDING
        assert log.user_id == user.id
        assert log.generated_by_system is True
        assert log.credits_used == 1


# ============================================================================
# LAB RESULT INTERPRETATION
# ============================================================================


def test_interpret_lab_results_requires_result_data(
    app,
    clinic,
):
    with app.app_context():
        with pytest.raises(
            ValidationError,
            match="Result data is required",
        ):
            ai_service.interpret_lab_results(
                clinic.id,
                {},
            )


def test_interpret_lab_results_rejects_non_dict_result_data(
    app,
    clinic,
):
    with app.app_context():
        with pytest.raises(
            ValidationError,
            match="Result data is required",
        ):
            ai_service.interpret_lab_results(
                clinic.id,
                [],
            )


def test_interpret_lab_results_accepts_result_data(
    app,
    clinic,
    monkeypatch,
):
    with app.app_context():
        monkeypatch.setattr(
            ai_service,
            "consume_ai_credit",
            lambda clinic_id: None,
        )

        result = ai_service.interpret_lab_results(
            clinic.id,
            {
                "hemoglobin": 13.2,
                "wbc": 7.1,
            },
            provider=make_provider(make_lab_result()),
        )

        assert result["summary"] == "Laboratory results reviewed."


def test_interpret_lab_results_lab_order_sets_patient(
    app,
    clinic,
    patient,
    staff,
    make_lab_test,
    make_lab_order,
    monkeypatch,
):
    with app.app_context():
        lab_test = make_lab_test(clinic)

        order = make_lab_order(
            clinic,
            patient,
            staff,
            [lab_test],
        )

        monkeypatch.setattr(
            ai_service,
            "consume_ai_credit",
            lambda clinic_id: None,
        )

        result = ai_service.interpret_lab_results(
            clinic.id,
            {
                "hemoglobin": 13.2,
            },
            lab_order_id=order.id,
            provider=make_provider(make_lab_result()),
        )

        assert result["summary"] == "Laboratory results reviewed."

        log = db.session.scalars(
            db.select(AILog).where(
                AILog.clinic_id == clinic.id,
                AILog.feature_used
                == AIFeature.LAB_RESULT_INTERPRETER,
            )
        ).one()

        assert log.patient_id == patient.id
        assert log.input_data["lab_order_id"] == order.id


def test_interpret_lab_results_rejects_patient_mismatch(
    app,
    clinic,
    patient,
    staff,
    make_patient,
    make_lab_test,
    make_lab_order,
):
    with app.app_context():
        supplied_patient = make_patient(clinic)

        lab_test = make_lab_test(clinic)

        order = make_lab_order(
            clinic,
            patient,
            staff,
            [lab_test],
        )

        with pytest.raises(
            ValidationError,
            match="Lab order does not belong to the supplied patient",
        ):
            ai_service.interpret_lab_results(
                clinic.id,
                {
                    "hemoglobin": 13.2,
                },
                patient_id=supplied_patient.id,
                lab_order_id=order.id,
                provider=make_provider(make_lab_result()),
            )


# ============================================================================
# _RUN_FEATURE
# ============================================================================


def test_run_feature_rejects_unknown_provider_result(
    app,
    clinic,
    monkeypatch,
):
    with app.app_context():
        monkeypatch.setattr(
            ai_service,
            "consume_ai_credit",
            lambda clinic_id: None,
        )

        def provider(feature, payload):
            return "not-a-dict"

        with pytest.raises(
            ValidationError,
            match="AI provider must return a JSON object",
        ):
            ai_service._run_feature(
                AIFeature.DRUG_INTERACTION_CHECK,
                clinic.id,
                {
                    "drug_names": [
                        "Aspirin",
                        "Warfarin",
                    ]
                },
                provider=provider,
            )


def test_run_feature_persists_log(
    app,
    clinic,
    patient,
    user,
    monkeypatch,
):
    with app.app_context():
        monkeypatch.setattr(
            ai_service,
            "consume_ai_credit",
            lambda clinic_id: None,
        )

        result = ai_service._run_feature(
            AIFeature.DRUG_INTERACTION_CHECK,
            clinic.id,
            {
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
            patient_id=patient.id,
            user_id=user.id,
            provider=make_provider(make_drug_result()),
        )

        assert result["summary"] == (
            "No clinically significant interaction found."
        )

        log = db.session.scalars(
            db.select(AILog).where(
                AILog.clinic_id == clinic.id,
                AILog.patient_id == patient.id,
                AILog.user_id == user.id,
                AILog.feature_used
                == AIFeature.DRUG_INTERACTION_CHECK,
            )
        ).one()

        assert log.feature_used == (
            AIFeature.DRUG_INTERACTION_CHECK
        )
        assert log.risk_level == AIRiskLevel.MEDIUM
        assert log.approval_status == AIApprovalStatus.PENDING
        assert log.generated_by_system is True
        assert log.credits_used == 1
        assert log.input_data == {
            "drug_names": [
                "Aspirin",
                "Warfarin",
            ]
        }
        assert log.output_data == result


def test_run_feature_persists_model_metadata(
    app,
    clinic,
    monkeypatch,
):
    with app.app_context():
        app.config["OPENAI_MODEL"] = "test-model"
        app.config["OPENAI_MODEL_VERSION"] = "2026-09"
        app.config["AI_INPUT_CONTEXT_VERSION"] = "v3"

        monkeypatch.setattr(
            ai_service,
            "consume_ai_credit",
            lambda clinic_id: None,
        )

        ai_service._run_feature(
            AIFeature.DRUG_INTERACTION_CHECK,
            clinic.id,
            {
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
            provider=make_provider(make_drug_result()),
        )

        log = db.session.scalars(
            db.select(AILog).where(
                AILog.clinic_id == clinic.id,
                AILog.feature_used
                == AIFeature.DRUG_INTERACTION_CHECK,
            )
        ).one()

        assert log.model == "test-model"
        assert log.model_version == "2026-09"
        assert log.input_context_version == "v3"


def test_run_feature_high_risk_remains_pending(
    app,
    clinic,
    patient,
    monkeypatch,
):
    with app.app_context():
        monkeypatch.setattr(
            ai_service,
            "consume_ai_credit",
            lambda clinic_id: None,
        )

        ai_service._run_feature(
            AIFeature.TRIAGE_ASSISTANT,
            clinic.id,
            {
                "symptoms": "Severe chest pain",
                "vitals": {
                    "heart_rate": 130,
                },
            },
            patient_id=patient.id,
            provider=make_provider(
                make_triage_result(
                    risk_score=AIRiskLevel.CRITICAL.value,
                )
            ),
        )

        log = db.session.scalars(
            db.select(AILog).where(
                AILog.clinic_id == clinic.id,
                AILog.patient_id == patient.id,
                AILog.feature_used
                == AIFeature.TRIAGE_ASSISTANT,
            )
        ).one()

        assert log.risk_level == AIRiskLevel.CRITICAL
        assert log.approval_status == AIApprovalStatus.PENDING


def test_run_feature_uses_supplied_provider(
    app,
    clinic,
    monkeypatch,
):
    with app.app_context():
        monkeypatch.setattr(
            ai_service,
            "consume_ai_credit",
            lambda clinic_id: None,
        )

        provider = make_provider(
            make_drug_result(
                summary="Provider was used."
            )
        )

        result = ai_service._run_feature(
            AIFeature.DRUG_INTERACTION_CHECK,
            clinic.id,
            {
                "drug_names": [
                    "Drug A",
                    "Drug B",
                ]
            },
            provider=provider,
        )

        assert result["summary"] == "Provider was used."


def test_run_feature_does_not_create_log_when_provider_fails(
    app,
    clinic,
    monkeypatch,
):
    with app.app_context():
        monkeypatch.setattr(
            ai_service,
            "consume_ai_credit",
            lambda clinic_id: None,
        )

        def provider(feature, payload):
            raise ValidationError("Provider failed")

        with pytest.raises(
            ValidationError,
            match="Provider failed",
        ):
            ai_service._run_feature(
                AIFeature.DRUG_INTERACTION_CHECK,
                clinic.id,
                {
                    "drug_names": [
                        "Drug A",
                        "Drug B",
                    ]
                },
                provider=provider,
            )

        logs = db.session.scalars(
            db.select(AILog).where(
                AILog.clinic_id == clinic.id,
                AILog.feature_used
                == AIFeature.DRUG_INTERACTION_CHECK,
            )
        ).all()

        assert logs == []


# ============================================================================
# OPENAI PROVIDER
# ============================================================================


def test_call_openai_requires_api_key(app):
    with app.app_context():
        app.config.pop("OPENAI_API_KEY", None)

        with pytest.raises(
            ValidationError,
            match="OPENAI_API_KEY is not configured",
        ):
            ai_service._call_openai(
                AIFeature.DRUG_INTERACTION_CHECK,
                {
                    "drug_names": [
                        "Aspirin",
                        "Warfarin",
                    ]
                },
            )


def test_call_openai_rejects_missing_openai_package(
    app,
    monkeypatch,
):
    with app.app_context():
        app.config["OPENAI_API_KEY"] = "test-key"

        original_import = __import__

        def fake_import(
            name,
            globals=None,
            locals=None,
            fromlist=(),
            level=0,
        ):
            if name == "openai":
                raise ImportError

            return original_import(
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

        with pytest.raises(
            ValidationError,
            match="The OpenAI package is not installed",
        ):
            ai_service._call_openai(
                AIFeature.DRUG_INTERACTION_CHECK,
                {
                    "drug_names": [
                        "Aspirin",
                        "Warfarin",
                    ]
                },
            )


def test_call_openai_returns_json_object(
    app,
    monkeypatch,
):
    with app.app_context():
        app.config["OPENAI_API_KEY"] = "test-key"
        app.config["OPENAI_MODEL"] = "test-model"

        class FakeCompletions:
            def create(self, **kwargs):
                assert kwargs["model"] == "test-model"
                assert kwargs["response_format"] == {
                    "type": "json_object"
                }

                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content=json.dumps(
                                    make_drug_result()
                                )
                            )
                        )
                    ]
                )

        class FakeClient:
            def __init__(self, api_key):
                assert api_key == "test-key"

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

        result = ai_service._call_openai(
            AIFeature.DRUG_INTERACTION_CHECK,
            {
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
        )

        assert result["summary"] == (
            "No clinically significant interaction found."
        )


def test_call_openai_rejects_provider_exception(
    app,
    monkeypatch,
):
    with app.app_context():
        app.config["OPENAI_API_KEY"] = "test-key"

        class FakeClient:
            def __init__(self, api_key):
                raise RuntimeError("connection failed")

        fake_openai = SimpleNamespace(
            OpenAI=FakeClient
        )

        monkeypatch.setitem(
            __import__("sys").modules,
            "openai",
            fake_openai,
        )

        with pytest.raises(
            ValidationError,
            match="AI provider request failed",
        ):
            ai_service._call_openai(
                AIFeature.DRUG_INTERACTION_CHECK,
                {
                    "drug_names": [
                        "Aspirin",
                        "Warfarin",
                    ]
                },
            )


def test_call_openai_rejects_no_choices(
    app,
    monkeypatch,
):
    with app.app_context():
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

        fake_openai = SimpleNamespace(
            OpenAI=FakeClient
        )

        monkeypatch.setitem(
            __import__("sys").modules,
            "openai",
            fake_openai,
        )

        with pytest.raises(
            ValidationError,
            match="AI provider returned no choices",
        ):
            ai_service._call_openai(
                AIFeature.DRUG_INTERACTION_CHECK,
                {
                    "drug_names": [
                        "Aspirin",
                        "Warfarin",
                    ]
                },
            )


def test_call_openai_rejects_empty_content(
    app,
    monkeypatch,
):
    with app.app_context():
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

        fake_openai = SimpleNamespace(
            OpenAI=FakeClient
        )

        monkeypatch.setitem(
            __import__("sys").modules,
            "openai",
            fake_openai,
        )

        with pytest.raises(
            ValidationError,
            match="AI provider returned an empty response",
        ):
            ai_service._call_openai(
                AIFeature.DRUG_INTERACTION_CHECK,
                {
                    "drug_names": [
                        "Aspirin",
                        "Warfarin",
                    ]
                },
            )


def test_call_openai_rejects_invalid_json(
    app,
    monkeypatch,
):
    with app.app_context():
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

        fake_openai = SimpleNamespace(
            OpenAI=FakeClient
        )

        monkeypatch.setitem(
            __import__("sys").modules,
            "openai",
            fake_openai,
        )

        with pytest.raises(
            ValidationError,
            match="AI provider returned invalid JSON",
        ):
            ai_service._call_openai(
                AIFeature.DRUG_INTERACTION_CHECK,
                {
                    "drug_names": [
                        "Aspirin",
                        "Warfarin",
                    ]
                },
            )


def test_call_openai_rejects_non_object_json(
    app,
    monkeypatch,
):
    with app.app_context():
        app.config["OPENAI_API_KEY"] = "test-key"

        class FakeCompletions:
            def create(self, **kwargs):
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content=json.dumps(["invalid"])
                            )
                        )
                    ]
                )

        class FakeClient:
            def __init__(self, api_key):
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

        with pytest.raises(
            ValidationError,
            match="AI provider must return a JSON object",
        ):
            ai_service._call_openai(
                AIFeature.DRUG_INTERACTION_CHECK,
                {
                    "drug_names": [
                        "Aspirin",
                        "Warfarin",
                    ]
                },
            )


# ============================================================================
# DATABASE / METADATA SANITY
# ============================================================================


def test_ai_log_defaults_are_populated_after_run(
    app,
    clinic,
    monkeypatch,
):
    with app.app_context():
        monkeypatch.setattr(
            ai_service,
            "consume_ai_credit",
            lambda clinic_id: None,
        )

        ai_service._run_feature(
            AIFeature.DRUG_INTERACTION_CHECK,
            clinic.id,
            {
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
            provider=make_provider(make_drug_result()),
        )

        log = db.session.scalars(
            db.select(AILog).where(
                AILog.clinic_id == clinic.id
            )
        ).one()

        assert log.generated_by_system is True
        assert log.approval_status == AIApprovalStatus.PENDING
        assert log.credits_used == 1
        assert log.created_at is not None
        assert log.updated_at is not None


def test_ai_log_token_fields_remain_nullable_without_usage_data(
    app,
    clinic,
    monkeypatch,
):
    with app.app_context():
        monkeypatch.setattr(
            ai_service,
            "consume_ai_credit",
            lambda clinic_id: None,
        )

        ai_service._run_feature(
            AIFeature.DRUG_INTERACTION_CHECK,
            clinic.id,
            {
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
            provider=make_provider(make_drug_result()),
        )

        log = db.session.scalars(
            db.select(AILog).where(
                AILog.clinic_id == clinic.id
            )
        ).one()

        assert log.input_tokens is None
        assert log.output_tokens is None
        assert log.total_tokens is None
        assert log.estimated_cost is None
        assert log.cost_currency is None