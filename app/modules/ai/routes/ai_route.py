from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity
from pydantic import ValidationError as PydanticValidationError

from app.core.enums.role_enums import Role
from app.core.utils.decorators import role_required
from app.modules.ai.schemas.ai_schema import (
	DrugInteractionCheckSchema,
	LabResultInterpreterSchema,
	TriageAssistantSchema,
)
from app.modules.ai.services.ai_service import (
	assist_triage,
	check_drug_interactions,
	interpret_lab_results,
)

ai_bp = Blueprint("ai", __name__, url_prefix="/api/ai")
AI_ROLES = (Role.ADMIN, Role.DOCTOR, Role.NURSE, Role.PHARMACIST, Role.LAB_TECHNICIAN)


def _user_id():
	identity = get_jwt_identity()
	return int(identity) if identity is not None else None


def _payload(schema):
	try:
		return schema.model_validate(request.get_json(silent=True) or {})
	except PydanticValidationError as exc:
		return jsonify({"success": False, "error": exc.errors()}), 422


@ai_bp.post("/drug-interactions")
@role_required(*AI_ROLES)
def drug_interactions():
	payload = _payload(DrugInteractionCheckSchema)
	if isinstance(payload, tuple):
		return payload
	result = check_drug_interactions(**payload.model_dump(), user_id=_user_id())
	return jsonify({"success": True, "data": result}), 200


@ai_bp.post("/triage")
@role_required(*AI_ROLES)
def triage():
	payload = _payload(TriageAssistantSchema)
	if isinstance(payload, tuple):
		return payload
	result = assist_triage(**payload.model_dump(), user_id=_user_id())
	return jsonify({"success": True, "data": result}), 200


@ai_bp.post("/lab-results/interpret")
@role_required(*AI_ROLES)
def lab_results():
	payload = _payload(LabResultInterpreterSchema)
	if isinstance(payload, tuple):
		return payload
	result = interpret_lab_results(**payload.model_dump(), user_id=_user_id())
	return jsonify({"success": True, "data": result}), 200
