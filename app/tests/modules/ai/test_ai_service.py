import json
from unittest.mock import MagicMock, patch

import pytest

from app.core.enums.ai_enums import AIFeature
from app.core.exceptions import NotFoundError, ValidationError
from app.modules.ai.models.ai_model import AILog
from app.modules.ai.services.ai_service import (
    _call_openai,
    _get_clinic,
    _get_patient,
    _run_feature,
    assist_triage,
    check_drug_interactions,
    interpret_lab_results,
)


# ============================================================================
# HELPERS
# ============================================================================

def provider_result(feature, payload):
    """
    Simple deterministic AI provider used by service tests.
    """
    return {
        "feature": feature.value,
        "summary": "AI test response",
        "risk_score": "low",
        "payload_received": payload,
    }


# ============================================================================
# _get_clinic()
# ============================================================================

class TestGetClinic:
    def test_returns_clinic_when_it_exists(self, clinic):
        result = _get_clinic(clinic.id)

        assert result.id == clinic.id
        assert result.name == clinic.name

    def test_raises_not_found_when_clinic_does_not_exist(self, app):
        with pytest.raises(
            NotFoundError,
            match=f"Clinic 999999 not found",
        ):
            _get_clinic(999999)


# ============================================================================
# _get_patient()
# ============================================================================

class TestGetPatient:
    def test_returns_none_when_patient_id_is_none(self, clinic):
        result = _get_patient(
            clinic_id=clinic.id,
            patient_id=None,
        )

        assert result is None

    def test_returns_patient_when_patient_belongs_to_clinic(
        self,
        clinic,
        patient,
    ):
        result = _get_patient(
            clinic_id=clinic.id,
            patient_id=patient.id,
        )

        assert result.id == patient.id
        assert result.clinic_id == clinic.id

    def test_raises_not_found_when_patient_does_not_exist(
        self,
        clinic,
        app,
    ):
        with pytest.raises(
            NotFoundError,
            match="Patient 999999 not found",
        ):
            _get_patient(
                clinic_id=clinic.id,
                patient_id=999999,
            )

    def test_rejects_patient_from_different_clinic(
        self,
        make_clinic,
        make_patient,
        clinic,
    ):
        other_clinic = make_clinic(name="Other Clinic")
        other_patient = make_patient(other_clinic)

        with pytest.raises(
            ValidationError,
            match="Patient does not belong to the supplied clinic",
        ):
            _get_patient(
                clinic_id=clinic.id,
                patient_id=other_patient.id,
            )


# ============================================================================
# _call_openai()
# ============================================================================

class TestCallOpenAI:
    def test_rejects_when_openai_api_key_is_not_configured(
        self,
        app,
    ):
        app.config["OPENAI_API_KEY"] = None

        with pytest.raises(
            ValidationError,
            match="OPENAI_API_KEY is not configured",
        ):
            _call_openai(
                AIFeature.TRIAGE_ASSISTANT,
                {"symptoms": "fever"},
            )

    def test_rejects_when_openai_package_is_not_installed(
        self,
        app,
        monkeypatch,
    ):
        app.config["OPENAI_API_KEY"] = "test-key"

        import builtins

        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "openai":
                raise ImportError("openai missing")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(
            builtins,
            "__import__",
            fake_import,
        )

        with pytest.raises(
            ValidationError,
            match="The OpenAI package is not installed",
        ):
            _call_openai(
                AIFeature.TRIAGE_ASSISTANT,
                {"symptoms": "fever"},
            )

    def test_calls_openai_with_expected_configuration(
        self,
        app,
        monkeypatch,
    ):
        app.config["OPENAI_API_KEY"] = "test-key"
        app.config["OPENAI_MODEL"] = "test-model"

        response = MagicMock()
        response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"risk_score": "low"}'
                )
            )
        ]

        client = MagicMock()
        client.chat.completions.create.return_value = response

        openai_module = MagicMock()
        openai_module.OpenAI.return_value = client

        monkeypatch.setitem(
            __import__("sys").modules,
            "openai",
            openai_module,
        )

        result = _call_openai(
            AIFeature.TRIAGE_ASSISTANT,
            {"symptoms": "fever"},
        )

        assert result == {
            "risk_score": "low",
        }

        openai_module.OpenAI.assert_called_once_with(
            api_key="test-key",
        )

        client.chat.completions.create.assert_called_once()

        kwargs = client.chat.completions.create.call_args.kwargs

        assert kwargs["model"] == "test-model"
        assert kwargs["response_format"] == {
            "type": "json_object",
        }

        assert len(kwargs["messages"]) == 2
        assert kwargs["messages"][0]["role"] == "system"
        assert kwargs["messages"][1]["role"] == "user"

        user_payload = json.loads(
            kwargs["messages"][1]["content"]
        )

        assert user_payload["feature"] == (
            AIFeature.TRIAGE_ASSISTANT.value
        )
        assert user_payload["data"] == {
            "symptoms": "fever",
        }

    def test_uses_default_model_when_model_is_not_configured(
        self,
        app,
        monkeypatch,
    ):
        app.config["OPENAI_API_KEY"] = "test-key"

        response = MagicMock()
        response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"result": "ok"}'
                )
            )
        ]

        client = MagicMock()
        client.chat.completions.create.return_value = response

        openai_module = MagicMock()
        openai_module.OpenAI.return_value = client

        monkeypatch.setitem(
            __import__("sys").modules,
            "openai",
            openai_module,
        )

        result = _call_openai(
            AIFeature.DRUG_INTERACTION_CHECK,
            {"drug_names": ["Aspirin", "Warfarin"]},
        )

        assert result == {
            "result": "ok",
        }

        kwargs = client.chat.completions.create.call_args.kwargs

        assert kwargs["model"] == "gpt-4o-mini"

    def test_rejects_empty_choices_from_provider(
        self,
        app,
        monkeypatch,
    ):
        app.config["OPENAI_API_KEY"] = "test-key"

        response = MagicMock()
        response.choices = []

        client = MagicMock()
        client.chat.completions.create.return_value = response

        openai_module = MagicMock()
        openai_module.OpenAI.return_value = client

        monkeypatch.setitem(
            __import__("sys").modules,
            "openai",
            openai_module,
        )

        with pytest.raises(
            ValidationError,
            match="AI provider returned no choices",
        ):
            _call_openai(
                AIFeature.TRIAGE_ASSISTANT,
                {"symptoms": "fever"},
            )

    def test_rejects_empty_provider_content(
        self,
        app,
        monkeypatch,
    ):
        app.config["OPENAI_API_KEY"] = "test-key"

        response = MagicMock()
        response.choices = [
            MagicMock(
                message=MagicMock(
                    content=""
                )
            )
        ]

        client = MagicMock()
        client.chat.completions.create.return_value = response

        openai_module = MagicMock()
        openai_module.OpenAI.return_value = client

        monkeypatch.setitem(
            __import__("sys").modules,
            "openai",
            openai_module,
        )

        with pytest.raises(
            ValidationError,
            match="AI provider returned an empty response",
        ):
            _call_openai(
                AIFeature.TRIAGE_ASSISTANT,
                {"symptoms": "fever"},
            )

    def test_rejects_invalid_json_from_provider(
        self,
        app,
        monkeypatch,
    ):
        app.config["OPENAI_API_KEY"] = "test-key"

        response = MagicMock()
        response.choices = [
            MagicMock(
                message=MagicMock(
                    content="this is not json"
                )
            )
        ]

        client = MagicMock()
        client.chat.completions.create.return_value = response

        openai_module = MagicMock()
        openai_module.OpenAI.return_value = client

        monkeypatch.setitem(
            __import__("sys").modules,
            "openai",
            openai_module,
        )

        with pytest.raises(
            ValidationError,
            match="AI provider returned invalid JSON",
        ):
            _call_openai(
                AIFeature.TRIAGE_ASSISTANT,
                {"symptoms": "fever"},
            )

    def test_rejects_non_object_json_from_provider(
        self,
        app,
        monkeypatch,
    ):
        app.config["OPENAI_API_KEY"] = "test-key"

        response = MagicMock()
        response.choices = [
            MagicMock(
                message=MagicMock(
                    content='["not", "an", "object"]'
                )
            )
        ]

        client = MagicMock()
        client.chat.completions.create.return_value = response

        openai_module = MagicMock()
        openai_module.OpenAI.return_value = client

        monkeypatch.setitem(
            __import__("sys").modules,
            "openai",
            openai_module,
        )

        with pytest.raises(
            ValidationError,
            match="AI provider must return a JSON object",
        ):
            _call_openai(
                AIFeature.TRIAGE_ASSISTANT,
                {"symptoms": "fever"},
            )


# ============================================================================
# _run_feature()
# ============================================================================

class TestRunFeature:
    def test_runs_feature_successfully(
        self,
        clinic,
        db,
    ):
        result = _run_feature(
            feature=AIFeature.DRUG_INTERACTION_CHECK,
            clinic_id=clinic.id,
            payload={
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
            provider=provider_result,
        )

        assert result["feature"] == (
            AIFeature.DRUG_INTERACTION_CHECK.value
        )
        assert result["summary"] == "AI test response"

    def test_creates_ai_log(
        self,
        clinic,
        db,
    ):
        payload = {
            "drug_names": [
                "Aspirin",
                "Warfarin",
            ]
        }

        result = _run_feature(
            feature=AIFeature.DRUG_INTERACTION_CHECK,
            clinic_id=clinic.id,
            payload=payload,
            user_id=123,
            provider=provider_result,
        )

        db.session.flush()

        log = (
            AILog.query
            .filter_by(clinic_id=clinic.id)
            .order_by(AILog.id.desc())
            .first()
        )

        assert log is not None
        assert log.clinic_id == clinic.id
        assert log.patient_id is None
        assert log.user_id == 123
        assert log.feature_used == (
            AIFeature.DRUG_INTERACTION_CHECK
        )
        assert log.input_data == payload
        assert log.output_data == result
        assert log.credits_used == 1

    def test_consumes_one_ai_credit(
        self,
        clinic,
        db,
    ):
        starting_credits = clinic.ai_credits

        _run_feature(
            feature=AIFeature.DRUG_INTERACTION_CHECK,
            clinic_id=clinic.id,
            payload={
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
            provider=provider_result,
        )

        db.session.refresh(clinic)

        assert clinic.ai_credits == starting_credits - 1

    def test_passes_patient_to_ai_log(
        self,
        clinic,
        patient,
        db,
    ):
        _run_feature(
            feature=AIFeature.DRUG_INTERACTION_CHECK,
            clinic_id=clinic.id,
            patient_id=patient.id,
            payload={
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
            provider=provider_result,
        )

        db.session.flush()

        log = (
            AILog.query
            .filter_by(
                clinic_id=clinic.id,
                patient_id=patient.id,
            )
            .order_by(AILog.id.desc())
            .first()
        )

        assert log is not None
        assert log.patient_id == patient.id

    def test_passes_correct_feature_and_payload_to_provider(
        self,
        clinic,
    ):
        provider = MagicMock(
            return_value={
                "result": "ok",
            }
        )

        payload = {
            "drug_names": [
                "Aspirin",
                "Warfarin",
            ]
        }

        result = _run_feature(
            feature=AIFeature.DRUG_INTERACTION_CHECK,
            clinic_id=clinic.id,
            payload=payload,
            provider=provider,
        )

        assert result == {
            "result": "ok",
        }

        provider.assert_called_once_with(
            AIFeature.DRUG_INTERACTION_CHECK,
            payload,
        )

    def test_rejects_non_dict_provider_result(
        self,
        clinic,
    ):
        provider = MagicMock(
            return_value=["not", "a", "dict"]
        )

        with pytest.raises(
            ValidationError,
            match="AI provider must return a JSON object",
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

    def test_rejects_nonexistent_clinic_before_provider_call(
        self,
    ):
        provider = MagicMock(
            return_value={"result": "ok"}
        )

        with pytest.raises(
            NotFoundError,
            match="Clinic 999999 not found",
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

    def test_rejects_invalid_patient_before_provider_call(
        self,
        clinic,
    ):
        provider = MagicMock(
            return_value={"result": "ok"}
        )

        with pytest.raises(
            NotFoundError,
            match="Patient 999999 not found",
        ):
            _run_feature(
                feature=AIFeature.TRIAGE_ASSISTANT,
                clinic_id=clinic.id,
                patient_id=999999,
                payload={
                    "symptoms": "fever",
                    "vitals": None,
                },
                provider=provider,
            )

        provider.assert_not_called()

    def test_transaction_rolls_back_credit_when_provider_fails(
        self,
        clinic,
        db,
    ):
        starting_credits = clinic.ai_credits

        provider = MagicMock(
            side_effect=ValidationError(
                "AI provider failed"
            )
        )

        with pytest.raises(
            ValidationError,
            match="AI provider failed",
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

        db.session.refresh(clinic)

        assert clinic.ai_credits == starting_credits

        logs = AILog.query.filter_by(
            clinic_id=clinic.id
        ).all()

        assert logs == []


# ============================================================================
# check_drug_interactions()
# ============================================================================

class TestCheckDrugInteractions:
    def test_rejects_less_than_two_drugs(
        self,
        clinic,
    ):
        with pytest.raises(
            ValidationError,
            match="At least two drug names are required",
        ):
            check_drug_interactions(
                clinic_id=clinic.id,
                drug_names=["Aspirin"],
            )

    def test_rejects_empty_drug_list(
        self,
        clinic,
    ):
        with pytest.raises(
            ValidationError,
            match="At least two drug names are required",
        ):
            check_drug_interactions(
                clinic_id=clinic.id,
                drug_names=[],
            )

    @pytest.mark.parametrize(
        "drug_names",
        [
            ["Aspirin", ""],
            ["Aspirin", "   "],
            ["Aspirin", None],
            ["Aspirin", 123],
            ["", "   "],
        ],
    )
    def test_rejects_fewer_than_two_valid_drugs(
        self,
        clinic,
        drug_names,
    ):
        with pytest.raises(
            ValidationError,
            match="At least two valid drug names are required",
        ):
            check_drug_interactions(
                clinic_id=clinic.id,
                drug_names=drug_names,
            )

    def test_strips_valid_drug_names(
        self,
        clinic,
    ):
        provider = MagicMock(
            return_value={
                "interactions": []
            }
        )

        result = check_drug_interactions(
            clinic_id=clinic.id,
            drug_names=[
                " Aspirin ",
                " Warfarin ",
            ],
            provider=provider,
        )

        assert result == {
            "interactions": []
        }

        provider.assert_called_once_with(
            AIFeature.DRUG_INTERACTION_CHECK,
            {
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
        )

    def test_accepts_patient_and_user_context(
        self,
        clinic,
        patient,
    ):
        provider = MagicMock(
            return_value={
                "interactions": []
            }
        )

        check_drug_interactions(
            clinic_id=clinic.id,
            drug_names=[
                "Aspirin",
                "Warfarin",
            ],
            patient_id=patient.id,
            user_id=55,
            provider=provider,
        )

        provider.assert_called_once()


# ============================================================================
# assist_triage()
# ============================================================================

class TestAssistTriage:
    def test_rejects_empty_symptoms(
        self,
        clinic,
        patient,
    ):
        with pytest.raises(
            ValidationError,
            match="Symptoms are required",
        ):
            assist_triage(
                clinic_id=clinic.id,
                patient_id=patient.id,
                symptoms="",
            )

    def test_rejects_whitespace_only_symptoms(
        self,
        clinic,
        patient,
    ):
        with pytest.raises(
            ValidationError,
            match="Symptoms are required",
        ):
            assist_triage(
                clinic_id=clinic.id,
                patient_id=patient.id,
                symptoms="   ",
            )

    @pytest.mark.parametrize(
        "symptoms",
        [
            None,
            123,
            [],
            {},
        ],
    )
    def test_rejects_non_string_symptoms(
        self,
        clinic,
        patient,
        symptoms,
    ):
        with pytest.raises(
            ValidationError,
            match="Symptoms are required",
        ):
            assist_triage(
                clinic_id=clinic.id,
                patient_id=patient.id,
                symptoms=symptoms,
            )

    @pytest.mark.parametrize(
        "vitals",
        [
            [],
            [],
            "120/80",
            120,
            True,
        ],
    )
    def test_rejects_non_dict_vitals(
        self,
        clinic,
        patient,
        vitals,
    ):
        with pytest.raises(
            ValidationError,
            match="Vitals must be provided as an object",
        ):
            assist_triage(
                clinic_id=clinic.id,
                patient_id=patient.id,
                symptoms="fever",
                vitals=vitals,
            )

    def test_accepts_missing_vitals(
        self,
        clinic,
        patient,
    ):
        provider = MagicMock(
            return_value={
                "summary": "Stable",
                "risk_score": "low",
            }
        )

        result = assist_triage(
            clinic_id=clinic.id,
            patient_id=patient.id,
            symptoms=" fever ",
            provider=provider,
        )

        assert result["summary"] == "Stable"

        provider.assert_called_once_with(
            AIFeature.TRIAGE_ASSISTANT,
            {
                "symptoms": "fever",
                "vitals": None,
            },
        )

    def test_strips_symptoms_before_sending_to_provider(
        self,
        clinic,
        patient,
    ):
        provider = MagicMock(
            return_value={
                "summary": "Patient appears stable",
                "risk_score": "low",
            }
        )

        assist_triage(
            clinic_id=clinic.id,
            patient_id=patient.id,
            symptoms="  headache and fever  ",
            vitals={
                "temperature": 38.5,
            },
            provider=provider,
        )

        provider.assert_called_once_with(
            AIFeature.TRIAGE_ASSISTANT,
            {
                "symptoms": "headache and fever",
                "vitals": {
                    "temperature": 38.5,
                },
            },
        )

    def test_updates_patient_ai_triage_data(
        self,
        clinic,
        patient,
        db,
    ):
        provider_response = {
            "summary": "Possible viral infection",
            "risk_score": "medium",
            "recommendation": "Clinical review recommended",
        }

        assist_triage(
            clinic_id=clinic.id,
            patient_id=patient.id,
            symptoms="fever and headache",
            provider=MagicMock(
                return_value=provider_response
            ),
        )

        db.session.refresh(patient)

        assert patient.ai_triage_data == provider_response
        assert patient.ai_summary == (
            "Possible viral infection"
        )
        assert patient.ai_risk_score == "medium"

    def test_creates_triage_ai_log_for_patient(
        self,
        clinic,
        patient,
        db,
    ):
        provider_response = {
            "summary": "Stable",
            "risk_score": "low",
        }

        assist_triage(
            clinic_id=clinic.id,
            patient_id=patient.id,
            symptoms="mild headache",
            user_id=42,
            provider=MagicMock(
                return_value=provider_response
            ),
        )

        log = (
            AILog.query
            .filter_by(
                clinic_id=clinic.id,
                patient_id=patient.id,
            )
            .order_by(AILog.id.desc())
            .first()
        )

        assert log is not None
        assert log.feature_used == (
            AIFeature.TRIAGE_ASSISTANT
        )
        assert log.user_id == 42
        assert log.patient_id == patient.id
        assert log.credits_used == 1

    def test_rejects_patient_from_different_clinic(
        self,
        make_clinic,
        make_patient,
        clinic,
    ):
        other_clinic = make_clinic(name="Other Clinic")
        other_patient = make_patient(other_clinic)

        provider = MagicMock()

        with pytest.raises(
            ValidationError,
            match="Patient does not belong to the supplied clinic",
        ):
            assist_triage(
                clinic_id=clinic.id,
                patient_id=other_patient.id,
                symptoms="fever",
                provider=provider,
            )

        provider.assert_not_called()


# ============================================================================
# interpret_lab_results()
# ============================================================================

class TestInterpretLabResults:
    def test_rejects_missing_result_data(
        self,
        clinic,
    ):
        with pytest.raises(
            ValidationError,
            match="Result data is required",
        ):
            interpret_lab_results(
                clinic_id=clinic.id,
                result_data={},
            )

    @pytest.mark.parametrize(
        "result_data",
        [
            None,
            [],
            [],
            "positive",
            123,
            False,
        ],
    )
    def test_rejects_non_dict_result_data(
        self,
        clinic,
        result_data,
    ):
        with pytest.raises(
            ValidationError,
            match="Result data is required",
        ):
            interpret_lab_results(
                clinic_id=clinic.id,
                result_data=result_data,
            )

    def test_interprets_result_without_lab_order(
        self,
        clinic,
    ):
        provider = MagicMock(
            return_value={
                "summary": "Results reviewed",
            }
        )

        result = interpret_lab_results(
            clinic_id=clinic.id,
            result_data={
                "hemoglobin": 13.5,
                "wbc": 7000,
            },
            provider=provider,
        )

        assert result == {
            "summary": "Results reviewed",
        }

        provider.assert_called_once_with(
            AIFeature.LAB_RESULT_INTERPRETER,
            {
                "result_data": {
                    "hemoglobin": 13.5,
                    "wbc": 7000,
                },
                "lab_order_id": None,
            },
        )

    def test_rejects_missing_lab_order(
        self,
        clinic,
    ):
        provider = MagicMock()

        with pytest.raises(
            NotFoundError,
            match="Lab order 999999 not found",
        ):
            interpret_lab_results(
                clinic_id=clinic.id,
                result_data={
                    "hemoglobin": 13.5,
                },
                lab_order_id=999999,
                provider=provider,
            )

        provider.assert_not_called()

    def test_rejects_lab_order_from_different_clinic(
        self,
        clinic,
        db,
    ):
        """
        The service only needs db.session.get() for this branch, so use
        a mocked LabOrder rather than depending on the full LabOrder
        fixture/model construction.
        """
        order = MagicMock()
        order.id = 10
        order.clinic_id = 999
        order.patient_id = 1

        with patch(
            "app.modules.ai.services.ai_service.db.session.get",
            return_value=order,
        ):
            provider = MagicMock()

            with pytest.raises(
                ValidationError,
                match="Lab order does not belong to the supplied clinic",
            ):
                interpret_lab_results(
                    clinic_id=clinic.id,
                    result_data={
                        "hemoglobin": 13.5,
                    },
                    lab_order_id=10,
                    provider=provider,
                )

            provider.assert_not_called()

    def test_rejects_lab_order_for_different_patient(
        self,
        clinic,
        patient,
    ):
        order = MagicMock()
        order.id = 10
        order.clinic_id = clinic.id
        order.patient_id = 999

        with patch(
            "app.modules.ai.services.ai_service.db.session.get",
            return_value=order,
        ):
            provider = MagicMock()

            with pytest.raises(
                ValidationError,
                match="Lab order does not belong to the supplied patient",
            ):
                interpret_lab_results(
                    clinic_id=clinic.id,
                    result_data={
                        "hemoglobin": 13.5,
                    },
                    patient_id=patient.id,
                    lab_order_id=10,
                    provider=provider,
                )

            provider.assert_not_called()

    def test_lab_order_patient_becomes_authoritative_patient(
        self,
        clinic,
        patient,
    ):
        order = MagicMock()
        order.id = 10
        order.clinic_id = clinic.id
        order.patient_id = patient.id

        provider = MagicMock(
            return_value={
                "summary": "Normal",
            }
        )

        with patch(
            "app.modules.ai.services.ai_service.db.session.get",
            return_value=order,
        ):
            result = interpret_lab_results(
                clinic_id=clinic.id,
                result_data={
                    "hemoglobin": 13.5,
                },
                lab_order_id=10,
                provider=provider,
            )

        assert result == {
            "summary": "Normal",
        }

        provider.assert_called_once_with(
            AIFeature.LAB_RESULT_INTERPRETER,
            {
                "result_data": {
                    "hemoglobin": 13.5,
                },
                "lab_order_id": 10,
            },
        )

    def test_rejects_mismatched_patient_even_when_lab_order_exists(
        self,
        clinic,
        patient,
    ):
        order = MagicMock()
        order.id = 10
        order.clinic_id = clinic.id
        order.patient_id = patient.id + 999

        with patch(
            "app.modules.ai.services.ai_service.db.session.get",
            return_value=order,
        ):
            with pytest.raises(
                ValidationError,
                match="Lab order does not belong to the supplied patient",
            ):
                interpret_lab_results(
                    clinic_id=clinic.id,
                    result_data={
                        "hemoglobin": 13.5,
                    },
                    patient_id=patient.id,
                    lab_order_id=10,
                    provider=MagicMock(),
                )