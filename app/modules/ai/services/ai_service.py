import json
from typing import Any, Callable, Optional, Type

from flask import current_app
from pydantic import ValidationError as PydanticValidationError

from app.core.enums.ai_enums import AIFeature
from app.core.exceptions import NotFoundError, ValidationError
from app.core.utils.decorators import transactional
from app.extensions import db

from app.modules.ai.models.ai_model import AILog

from app.modules.ai.schemas.ai_response_schema import (
    DrugInteractionResponseSchema,
    LabResultInterpreterResponseSchema,
    TriageAssistantResponseSchema,
)

from app.modules.clinic.models.clinic_model import Clinic
from app.modules.clinic.services.clinic_service import (
    consume_ai_credit,
)
from app.modules.lab.models.lab_model import LabOrder
from app.modules.patient.models.patient_model import Patient


AIProvider = Callable[
    [AIFeature, dict[str, Any]],
    dict[str, Any],
]


# ============================================================================
# HELPERS
# ============================================================================


def _get_clinic(clinic_id: int) -> Clinic:
    clinic = db.session.get(
        Clinic,
        clinic_id,
    )

    if clinic is None:
        raise NotFoundError(
            f"Clinic {clinic_id} not found"
        )

    return clinic


def _get_patient(
    clinic_id: int,
    patient_id: Optional[int],
) -> Optional[Patient]:
    if patient_id is None:
        return None

    patient = db.session.get(
        Patient,
        patient_id,
    )

    if patient is None:
        raise NotFoundError(
            f"Patient {patient_id} not found"
        )

    if patient.clinic_id != clinic_id:
        raise ValidationError(
            "Patient does not belong to the authenticated clinic"
        )

    return patient


def _get_lab_order(
    clinic_id: int,
    lab_order_id: int,
) -> LabOrder:
    lab_order = db.session.get(
        LabOrder,
        lab_order_id,
    )

    if lab_order is None:
        raise NotFoundError(
            f"Lab order {lab_order_id} not found"
        )

    if lab_order.clinic_id != clinic_id:
        raise ValidationError(
            "Lab order does not belong to the authenticated clinic"
        )

    return lab_order


def _call_openai(
    feature: AIFeature,
    payload: dict[str, Any],
) -> dict[str, Any]:
    api_key = current_app.config.get(
        "OPENAI_API_KEY"
    )

    if not api_key:
        raise ValidationError(
            "OPENAI_API_KEY is not configured"
        )

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ValidationError(
            "The OpenAI package is not installed"
        ) from exc

    try:
        client = OpenAI(
            api_key=api_key,
        )

        response = client.chat.completions.create(
            model=current_app.config.get(
                "OPENAI_MODEL",
                "gpt-4o-mini",
            ),
            response_format={
                "type": "json_object",
            },
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a clinical decision-support assistant. "
                        "Return JSON only. "
                        "Your output supports clinicians and is not a "
                        "diagnosis or a substitute for professional "
                        "medical judgment."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "feature": feature.value,
                            "data": payload,
                        }
                    ),
                },
            ],
        )

    except Exception as exc:
        raise ValidationError(
            "AI provider request failed"
        ) from exc

    if not response.choices:
        raise ValidationError(
            "AI provider returned no choices"
        )

    content = response.choices[0].message.content

    if not content:
        raise ValidationError(
            "AI provider returned an empty response"
        )

    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "AI provider returned invalid JSON"
        ) from exc

    if not isinstance(result, dict):
        raise ValidationError(
            "AI provider must return a JSON object"
        )

    return result


def _validate_provider_result(
    feature: AIFeature,
    result: dict[str, Any],
) -> dict[str, Any]:
    """
    Validate the raw AI provider response against
    the response schema for the selected AI feature.
    """

    schema_map: dict[
        AIFeature,
        Type[Any],
    ] = {
        AIFeature.DRUG_INTERACTION_CHECK:
            DrugInteractionResponseSchema,

        AIFeature.TRIAGE_ASSISTANT:
            TriageAssistantResponseSchema,

        AIFeature.LAB_RESULT_INTERPRETER:
            LabResultInterpreterResponseSchema,
    }

    schema = schema_map.get(feature)

    if schema is None:
        raise ValidationError(
            f"Unsupported AI feature '{feature.value}'"
        )

    try:
        validated = schema.model_validate(
            result
        )
    except PydanticValidationError as exc:
        raise ValidationError(
            f"AI provider returned invalid "
            f"{feature.value} response"
        ) from exc

    return validated.model_dump(
        mode="json"
    )


# ============================================================================
# CORE FEATURE EXECUTION
# ============================================================================


@transactional
def _run_feature(
    feature: AIFeature,
    clinic_id: int,
    payload: dict[str, Any],
    patient_id: Optional[int] = None,
    user_id: Optional[int] = None,
    provider: Optional[AIProvider] = None,
) -> dict[str, Any]:

    # ------------------------------------------------------------------------
    # Clinic isolation
    # ------------------------------------------------------------------------

    _get_clinic(
        clinic_id
    )

    # ------------------------------------------------------------------------
    # Patient isolation
    # ------------------------------------------------------------------------

    patient = _get_patient(
        clinic_id=clinic_id,
        patient_id=patient_id,
    )

    # ------------------------------------------------------------------------
    # Consume one AI credit.
    #
    # Because this function is transactional, a provider failure or
    # validation failure will roll this change back.
    # ------------------------------------------------------------------------

    consume_ai_credit(
        clinic_id
    )

    # ------------------------------------------------------------------------
    # Execute AI provider
    # ------------------------------------------------------------------------

    ai_provider = (
        provider
        or _call_openai
    )

    result = ai_provider(
        feature,
        payload,
    )

    if not isinstance(result, dict):
        raise ValidationError(
            "AI provider must return a JSON object"
        )

    # ------------------------------------------------------------------------
    # Validate AI output before storing it
    # ------------------------------------------------------------------------

    result = _validate_provider_result(
        feature=feature,
        result=result,
    )

    # ------------------------------------------------------------------------
    # Persist AI audit/log record
    # ------------------------------------------------------------------------

    log = AILog(
        clinic_id=clinic_id,
        patient_id=patient.id if patient else None,
        user_id=user_id,
        feature_used=feature,
        input_data=payload,
        output_data=result,
        credits_used=1,
    )

    db.session.add(log)

    # ------------------------------------------------------------------------
    # Persist triage information to patient
    # ------------------------------------------------------------------------

    if (
        feature is AIFeature.TRIAGE_ASSISTANT
        and patient is not None
    ):
        patient.ai_triage_data = result

        patient.ai_summary = result.get(
            "summary"
        )

        patient.ai_risk_score = result.get(
            "risk_score"
        )

    return result


# ============================================================================
# DRUG INTERACTION CHECK
# ============================================================================


def check_drug_interactions(
    clinic_id: int,
    drug_names: list[str],
    patient_id: Optional[int] = None,
    user_id: Optional[int] = None,
    provider: Optional[AIProvider] = None,
) -> dict[str, Any]:

    if (
        not isinstance(drug_names, list)
        or len(drug_names) < 2
    ):
        raise ValidationError(
            "At least two drug names are required"
        )

    cleaned_drugs = [
        drug.strip()
        for drug in drug_names
        if isinstance(drug, str)
        and drug.strip()
    ]

    if len(cleaned_drugs) < 2:
        raise ValidationError(
            "At least two valid drug names are required"
        )

    payload = {
        "drug_names": cleaned_drugs,
    }

    return _run_feature(
        feature=AIFeature.DRUG_INTERACTION_CHECK,
        clinic_id=clinic_id,
        payload=payload,
        patient_id=patient_id,
        user_id=user_id,
        provider=provider,
    )


# ============================================================================
# TRIAGE ASSISTANT
# ============================================================================


def assist_triage(
    clinic_id: int,
    patient_id: int,
    symptoms: str,
    vitals: Optional[dict[str, Any]] = None,
    user_id: Optional[int] = None,
    provider: Optional[AIProvider] = None,
) -> dict[str, Any]:

    if (
        not isinstance(symptoms, str)
        or not symptoms.strip()
    ):
        raise ValidationError(
            "Symptoms are required"
        )

    if (
        vitals is not None
        and not isinstance(vitals, dict)
    ):
        raise ValidationError(
            "Vitals must be provided as an object"
        )

    payload = {
        "symptoms": symptoms.strip(),
        "vitals": vitals,
    }

    return _run_feature(
        feature=AIFeature.TRIAGE_ASSISTANT,
        clinic_id=clinic_id,
        payload=payload,
        patient_id=patient_id,
        user_id=user_id,
        provider=provider,
    )


# ============================================================================
# LAB RESULT INTERPRETER
# ============================================================================


def interpret_lab_results(
    clinic_id: int,
    result_data: dict[str, Any],
    patient_id: Optional[int] = None,
    lab_order_id: Optional[int] = None,
    user_id: Optional[int] = None,
    provider: Optional[AIProvider] = None,
) -> dict[str, Any]:

    if (
        not isinstance(result_data, dict)
        or not result_data
    ):
        raise ValidationError(
            "Result data is required"
        )

    if lab_order_id is not None:
        lab_order = _get_lab_order(
            clinic_id=clinic_id,
            lab_order_id=lab_order_id,
        )

        if (
            patient_id is not None
            and lab_order.patient_id != patient_id
        ):
            raise ValidationError(
                "Lab order does not belong to the supplied patient"
            )

        # The lab order is authoritative for the patient.
        patient_id = lab_order.patient_id

    payload = {
        "result_data": result_data,
        "lab_order_id": lab_order_id,
    }

    return _run_feature(
        feature=AIFeature.LAB_RESULT_INTERPRETER,
        clinic_id=clinic_id,
        payload=payload,
        patient_id=patient_id,
        user_id=user_id,
        provider=provider,
    )