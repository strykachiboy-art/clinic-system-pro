from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

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


ai_bp = Blueprint(
    "ai",
    __name__,
    url_prefix="/api/ai",
)


AI_ROLES = (
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
    Role.PHARMACIST,
    Role.LAB_TECHNICIAN,
)


def _current_user_id() -> int:
    """
    Return the authenticated User ID from the JWT.
    """
    return int(get_jwt_identity())


@ai_bp.post("/drug-interactions")
@role_required(*AI_ROLES)
def drug_interactions():
    payload = DrugInteractionCheckSchema.model_validate(
        request.get_json(silent=True) or {}
    )

    result = check_drug_interactions(
        clinic_id=payload.clinic_id,
        drug_names=payload.drug_names,
        patient_id=payload.patient_id,
        user_id=_current_user_id(),
    )

    return jsonify(
        {
            "success": True,
            "data": result,
        }
    ), 200


@ai_bp.post("/triage")
@role_required(*AI_ROLES)
def triage():
    payload = TriageAssistantSchema.model_validate(
        request.get_json(silent=True) or {}
    )

    result = assist_triage(
        clinic_id=payload.clinic_id,
        patient_id=payload.patient_id,
        symptoms=payload.symptoms,
        vitals=payload.vitals,
        user_id=_current_user_id(),
    )

    return jsonify(
        {
            "success": True,
            "data": result,
        }
    ), 200


@ai_bp.post("/lab-results/interpret")
@role_required(*AI_ROLES)
def lab_results():
    payload = LabResultInterpreterSchema.model_validate(
        request.get_json(silent=True) or {}
    )

    result = interpret_lab_results(
        clinic_id=payload.clinic_id,
        patient_id=payload.patient_id,
        lab_order_id=payload.lab_order_id,
        result_data=payload.result_data,
        user_id=_current_user_id(),
    )

    return jsonify(
        {
            "success": True,
            "data": result,
        }
    ), 200