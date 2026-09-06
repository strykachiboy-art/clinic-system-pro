from flask import Blueprint, jsonify, request, g
from pydantic import ValidationError as PydanticValidationError

from app.core.auth.user.models.user_model import User
from app.core.enums.role_enums import Role
from app.core.exceptions import DomainError, ValidationError
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


def _current_user() -> User:
    """
    Return the authenticated User from the decorator-provided
    authentication context.
    """
    user = User.query.get(g.current_user_id)

    if user is None:
        raise ValidationError("Authenticated user was not found")

    if not user.is_active:
        raise ValidationError("User account is inactive")

    return user


def _current_clinic_id() -> int:
    """
    Return the authenticated user's clinic ID.

    AI routes must never trust a client-supplied clinic_id.
    """
    user = _current_user()

    if user.clinic_id is None:
        raise ValidationError(
            "Authenticated user is not associated with a clinic"
        )

    return user.clinic_id


@ai_bp.post("/drug-interactions")
@role_required(*AI_ROLES)
def drug_interactions():
    try:
        payload = DrugInteractionCheckSchema.model_validate(
            request.get_json(silent=True) or {}
        )

        result = check_drug_interactions(
            clinic_id=_current_clinic_id(),
            drug_names=payload.drug_names,
            patient_id=payload.patient_id,
            user_id=g.current_user_id,
        )

        return jsonify(
            {
                "success": True,
                "data": result,
            }
        ), 200

    except PydanticValidationError as exc:
        return jsonify(
            {
                "success": False,
                "error": "Invalid request payload",
                "details": exc.errors(),
            }
        ), 422

    except DomainError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), exc.status_code


@ai_bp.post("/triage")
@role_required(*AI_ROLES)
def triage():
    try:
        payload = TriageAssistantSchema.model_validate(
            request.get_json(silent=True) or {}
        )

        result = assist_triage(
            clinic_id=_current_clinic_id(),
            patient_id=payload.patient_id,
            symptoms=payload.symptoms,
            vitals=payload.vitals,
            user_id=g.current_user_id,
        )

        return jsonify(
            {
                "success": True,
                "data": result,
            }
        ), 200

    except PydanticValidationError as exc:
        return jsonify(
            {
                "success": False,
                "error": "Invalid request payload",
                "details": exc.errors(),
            }
        ), 422

    except DomainError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), exc.status_code


@ai_bp.post("/lab-results/interpret")
@role_required(*AI_ROLES)
def lab_results():
    try:
        payload = LabResultInterpreterSchema.model_validate(
            request.get_json(silent=True) or {}
        )

        result = interpret_lab_results(
            clinic_id=_current_clinic_id(),
            patient_id=payload.patient_id,
            lab_order_id=payload.lab_order_id,
            result_data=payload.result_data,
            user_id=g.current_user_id,
        )

        return jsonify(
            {
                "success": True,
                "data": result,
            }
        ), 200

    except PydanticValidationError as exc:
        return jsonify(
            {
                "success": False,
                "error": "Invalid request payload",
                "details": exc.errors(),
            }
        ), 422

    except DomainError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), exc.status_code