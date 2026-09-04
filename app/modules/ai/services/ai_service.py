import json
from typing import Any, Callable, Optional

from flask import current_app

from app.core.enums.ai_enums import AIFeature
from app.core.exceptions import NotFoundError, ValidationError
from app.core.utils.decorators import transactional
from app.extensions import db
from app.modules.ai.models.ai_model import AILog
from app.modules.clinic.models.clinic_model import Clinic
from app.modules.clinic.services.clinic_service import consume_ai_credit
from app.modules.lab.models.lab_model import LabOrder
from app.modules.patient.models.patient_model import Patient


AIProvider = Callable[
    [AIFeature, dict[str, Any]],
    dict[str, Any],
]


def _get_clinic(clinic_id: int) -> Clinic:
    """
    Retrieve a clinic by ID.

    Raises:
        NotFoundError: If the clinic does not exist.
    """
    clinic = db.session.get(Clinic, clinic_id)

    if not clinic:
        raise NotFoundError(f"Clinic {clinic_id} not found")

    return clinic


def _get_patient(
    clinic_id: int,
    patient_id: Optional[int],
) -> Optional[Patient]:
    """
    Retrieve a patient and ensure the patient belongs to the clinic.

    A patient ID is optional for AI features that do not require
    patient-specific context.
    """
    if patient_id is None:
        return None

    patient = db.session.get(Patient, patient_id)

    if not patient:
        raise NotFoundError(f"Patient {patient_id} not found")

    if patient.clinic_id != clinic_id:
        raise ValidationError(
            "Patient does not belong to the supplied clinic"
        )

    return patient


def _call_openai(
    feature: AIFeature,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Call the configured OpenAI provider.

    The provider is expected to return a JSON object.
    """
    api_key = current_app.config.get("OPENAI_API_KEY")

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

    client = OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model=current_app.config.get(
            "OPENAI_MODEL",
            "gpt-4o-mini",
        ),
        response_format={"type": "json_object"},
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


@transactional
def _run_feature(
    feature: AIFeature,
    clinic_id: int,
    payload: dict[str, Any],
    patient_id: Optional[int] = None,
    user_id: Optional[int] = None,
    provider: Optional[AIProvider] = None,
) -> dict[str, Any]:
    """
    Execute an AI feature as one database transaction.

    The transaction includes:
    - clinic validation
    - patient validation
    - AI credit consumption
    - AI provider execution
    - AI audit logging
    - patient AI data updates where applicable

    If any operation raises an exception, the transaction decorator
    rolls back the credit consumption and all database changes.
    """
    _get_clinic(clinic_id)

    patient = _get_patient(
        clinic_id=clinic_id,
        patient_id=patient_id,
    )

    # This only mutates the current SQLAlchemy transaction.
    # It deliberately does not commit independently.
    consume_ai_credit(clinic_id)

    ai_provider = provider or _call_openai

    result = ai_provider(
        feature,
        payload,
    )

    if not isinstance(result, dict):
        raise ValidationError(
            "AI provider must return a JSON object"
        )

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

    if feature is AIFeature.TRIAGE_ASSISTANT and patient:
        patient.ai_triage_data = result
        patient.ai_summary = result.get("summary")
        patient.ai_risk_score = result.get("risk_score")

    return result


def check_drug_interactions(
    clinic_id: int,
    drug_names: list[str],
    patient_id: Optional[int] = None,
    user_id: Optional[int] = None,
    provider: Optional[AIProvider] = None,
) -> dict[str, Any]:
    """
    Check a list of medications for potential drug interactions.
    """
    if len(drug_names) < 2:
        raise ValidationError(
            "At least two drug names are required"
        )

    cleaned_drug_names = [
        drug.strip()
        for drug in drug_names
        if isinstance(drug, str) and drug.strip()
    ]

    if len(cleaned_drug_names) < 2:
        raise ValidationError(
            "At least two valid drug names are required"
        )

    payload = {
        "drug_names": cleaned_drug_names,
    }

    return _run_feature(
        feature=AIFeature.DRUG_INTERACTION_CHECK,
        clinic_id=clinic_id,
        payload=payload,
        patient_id=patient_id,
        user_id=user_id,
        provider=provider,
    )


def assist_triage(
    clinic_id: int,
    patient_id: int,
    symptoms: str,
    vitals: Optional[dict[str, Any]] = None,
    user_id: Optional[int] = None,
    provider: Optional[AIProvider] = None,
) -> dict[str, Any]:
    """
    Provide AI-assisted triage support for a patient.
    """
    if not isinstance(symptoms, str) or not symptoms.strip():
        raise ValidationError(
            "Symptoms are required"
        )

    if vitals is not None and not isinstance(vitals, dict):
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


def interpret_lab_results(
    clinic_id: int,
    result_data: dict[str, Any],
    patient_id: Optional[int] = None,
    lab_order_id: Optional[int] = None,
    user_id: Optional[int] = None,
    provider: Optional[AIProvider] = None,
) -> dict[str, Any]:
    """
    Interpret laboratory results using the configured AI provider.

    When a lab order is supplied, its patient becomes the authoritative
    patient for the AI request.
    """
    if not isinstance(result_data, dict) or not result_data:
        raise ValidationError(
            "Result data is required"
        )

    if lab_order_id is not None:
        order = db.session.get(
            LabOrder,
            lab_order_id,
        )

        if not order:
            raise NotFoundError(
                f"Lab order {lab_order_id} not found"
            )

        if order.clinic_id != clinic_id:
            raise ValidationError(
                "Lab order does not belong to the supplied clinic"
            )

        if (
            patient_id is not None
            and order.patient_id != patient_id
        ):
            raise ValidationError(
                "Lab order does not belong to the supplied patient"
            )

        patient_id = order.patient_id

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