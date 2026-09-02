import json
from typing import Any, Callable, Optional

from flask import current_app

from app.core.enums.ai_enums import AIFeature
from app.core.exceptions import NotFoundError, ValidationError
from app.extensions import db
from app.modules.ai.models.ai_model import AILog
from app.modules.clinic.models.clinic_model import Clinic
from app.modules.clinic.services.clinic_service import consume_ai_credit
from app.modules.lab.models.lab_model import LabOrder
from app.modules.patient.models.patient_model import Patient


AIProvider = Callable[[AIFeature, dict[str, Any]], dict[str, Any]]


def _get_clinic(clinic_id: int) -> Clinic:
	clinic = db.session.get(Clinic, clinic_id)
	if not clinic:
		raise NotFoundError(f"Clinic {clinic_id} not found")
	return clinic


def _get_patient(clinic_id: int, patient_id: Optional[int]) -> Optional[Patient]:
	if patient_id is None:
		return None
	patient = db.session.get(Patient, patient_id)
	if not patient or patient.clinic_id != clinic_id:
		raise ValidationError("Patient does not belong to the supplied clinic")
	return patient


def _call_openai(feature: AIFeature, payload: dict[str, Any]) -> dict[str, Any]:
	api_key = current_app.config.get("OPENAI_API_KEY")
	if not api_key:
		raise ValidationError("OPENAI_API_KEY is not configured")

	try:
		from openai import OpenAI
	except ImportError as exc:
		raise ValidationError("The OpenAI package is not installed") from exc

	client = OpenAI(api_key=api_key)
	response = client.chat.completions.create(
		model=current_app.config.get("OPENAI_MODEL", "gpt-4o-mini"),
		response_format={"type": "json_object"},
		messages=[
			{
				"role": "system",
				"content": (
					"You are a clinical decision-support assistant. Return JSON only. "
					"Your output supports clinicians and is not a diagnosis or a substitute "
					"for professional medical judgment."
				),
			},
			{
				"role": "user",
				"content": json.dumps({"feature": feature.value, "data": payload}),
			},
		],
	)
	content = response.choices[0].message.content
	if not content:
		raise ValidationError("AI provider returned an empty response")
	try:
		result = json.loads(content)
	except json.JSONDecodeError as exc:
		raise ValidationError("AI provider returned invalid JSON") from exc
	if not isinstance(result, dict):
		raise ValidationError("AI provider must return a JSON object")
	return result


def _run_feature(
	feature: AIFeature,
	clinic_id: int,
	payload: dict[str, Any],
	patient_id: Optional[int] = None,
	user_id: Optional[int] = None,
	provider: Optional[AIProvider] = None,
) -> dict[str, Any]:
	_get_clinic(clinic_id)
	patient = _get_patient(clinic_id, patient_id)
	consume_ai_credit(clinic_id)

	try:
		result = (provider or _call_openai)(feature, payload)
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
		db.session.commit()
		return result
	except Exception:
		db.session.rollback()
		clinic = db.session.get(Clinic, clinic_id)
		if clinic:
			clinic.ai_credits += 1
			clinic.ai_requests_this_month = max(0, clinic.ai_requests_this_month - 1)
			db.session.commit()
		raise


def check_drug_interactions(
	clinic_id: int,
	drug_names: list[str],
	patient_id: Optional[int] = None,
	user_id: Optional[int] = None,
	provider: Optional[AIProvider] = None,
) -> dict[str, Any]:
	if len(drug_names) < 2:
		raise ValidationError("At least two drug names are required")
	payload = {"drug_names": drug_names}
	return _run_feature(
		AIFeature.DRUG_INTERACTION_CHECK,
		clinic_id,
		payload,
		patient_id,
		user_id,
		provider,
	)


def assist_triage(
	clinic_id: int,
	patient_id: int,
	symptoms: str,
	vitals: Optional[dict[str, Any]] = None,
	user_id: Optional[int] = None,
	provider: Optional[AIProvider] = None,
) -> dict[str, Any]:
	if not symptoms.strip():
		raise ValidationError("Symptoms are required")
	payload = {"symptoms": symptoms, "vitals": vitals}
	return _run_feature(
		AIFeature.TRIAGE_ASSISTANT,
		clinic_id,
		payload,
		patient_id,
		user_id,
		provider,
	)


def interpret_lab_results(
	clinic_id: int,
	result_data: dict[str, Any],
	patient_id: Optional[int] = None,
	lab_order_id: Optional[int] = None,
	user_id: Optional[int] = None,
	provider: Optional[AIProvider] = None,
) -> dict[str, Any]:
	if not result_data:
		raise ValidationError("Result data is required")
	if lab_order_id is not None:
		order = db.session.get(LabOrder, lab_order_id)
		if not order or order.clinic_id != clinic_id:
			raise ValidationError("Lab order does not belong to the supplied clinic")
		if patient_id is not None and order.patient_id != patient_id:
			raise ValidationError("Lab order does not belong to the supplied patient")
		patient_id = order.patient_id
	payload = {"result_data": result_data, "lab_order_id": lab_order_id}
	return _run_feature(
		AIFeature.LAB_RESULT_INTERPRETER,
		clinic_id,
		payload,
		patient_id,
		user_id,
		provider,
	)
