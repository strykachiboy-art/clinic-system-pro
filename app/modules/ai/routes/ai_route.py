from flask import Blueprint, jsonify, request, g
from flask_jwt_extended import get_jwt_identity
from pydantic import ValidationError as PydanticValidationError

from app.extensions import db, limiter

from app.core.auth.user.models.user_model import User
from app.core.enums.role_enums import Role
from app.core.exceptions import DomainError, ValidationError
from app.core.utils.decorators import role_required

from app.modules.ai.schemas.ai_schema import (
    DrugInteractionCheckSchema,
    LabResultInterpreterSchema,
    TriageAssistantSchema,
)

from app.modules.ai.schemas.ai_response_schema import (
    DrugInteractionResponseSchema,
    LabResultInterpreterResponseSchema,
    TriageAssistantResponseSchema,
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


AI_RATE_LIMIT = "10 per minute"


def _pydantic_error_details(
    exc: PydanticValidationError,
):
    """
    Return JSON-serializable Pydantic validation details.
    """

    details = exc.errors()

    for error in details:
        ctx = error.get("ctx")

        if isinstance(ctx, dict):
            error["ctx"] = {
                key: str(value)
                for key, value in ctx.items()
            }

    return details


def _request_json() -> dict:
    """
    Return the request JSON object.

    AI endpoints require a JSON object as their request body.
    """

    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        raise ValidationError(
            "Request body must be a JSON object"
        )

    return payload


def _current_user():
    """
    Return the authenticated active user.
    """

    identity = get_jwt_identity()

    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        raise ValidationError(
            "Invalid authentication identity"
        )

    if user_id <= 0:
        raise ValidationError(
            "Invalid authentication identity"
        )

    user = db.session.get(
        User,
        user_id,
    )

    if user is None:
        raise ValidationError(
            "Authenticated user could not be resolved"
        )

    if not user.is_active:
        raise ValidationError(
            "User account is inactive"
        )

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

    if user.clinic_id <= 0:
        raise ValidationError(
            "Authenticated user has an invalid clinic"
        )

    return user.clinic_id


def _client_ip_address() -> str | None:
    """
    Return the request IP address.

    The service is responsible for final normalization and
    persistence validation.
    """

    return request.remote_addr


def _serialize_ai_response(
    schema,
    result,
):
    """
    Validate and serialize an AI service response.

    This provides a second response boundary at the HTTP layer
    in addition to service-level provider validation.
    """

    return (
        schema
        .model_validate(result)
        .model_dump(mode="json")
    )


@ai_bp.post("/drug-interactions")
@limiter.limit(AI_RATE_LIMIT)
@role_required(*AI_ROLES)
def drug_interactions():
    try:
        payload = DrugInteractionCheckSchema.model_validate(
            _request_json()
        )

        result = check_drug_interactions(
            clinic_id=_current_clinic_id(),
            drug_names=payload.drug_names,
            patient_id=payload.patient_id,
            user_id=g.current_user_id,
            ip_address=_client_ip_address(),
        )

        response_data = _serialize_ai_response(
            DrugInteractionResponseSchema,
            result,
        )

        return jsonify(
            {
                "success": True,
                "data": response_data,
            }
        ), 200

    except PydanticValidationError as exc:
        return jsonify(
            {
                "success": False,
                "error": "Invalid request payload",
                "details": _pydantic_error_details(exc),
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
@limiter.limit(AI_RATE_LIMIT)
@role_required(*AI_ROLES)
def triage():
    try:
        payload = TriageAssistantSchema.model_validate(
            _request_json()
        )

        result = assist_triage(
            clinic_id=_current_clinic_id(),
            patient_id=payload.patient_id,
            symptoms=payload.symptoms,
            vitals=payload.vitals,
            user_id=g.current_user_id,
            ip_address=_client_ip_address(),
        )

        response_data = _serialize_ai_response(
            TriageAssistantResponseSchema,
            result,
        )

        return jsonify(
            {
                "success": True,
                "data": response_data,
            }
        ), 200

    except PydanticValidationError as exc:
        return jsonify(
            {
                "success": False,
                "error": "Invalid request payload",
                "details": _pydantic_error_details(exc),
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
@limiter.limit(AI_RATE_LIMIT)
@role_required(*AI_ROLES)
def lab_results():
    try:
        payload = LabResultInterpreterSchema.model_validate(
            _request_json()
        )

        result = interpret_lab_results(
            clinic_id=_current_clinic_id(),
            patient_id=payload.patient_id,
            lab_order_id=payload.lab_order_id,
            result_data=payload.result_data,
            user_id=g.current_user_id,
            ip_address=_client_ip_address(),
        )

        response_data = _serialize_ai_response(
            LabResultInterpreterResponseSchema,
            result,
        )

        return jsonify(
            {
                "success": True,
                "data": response_data,
            }
        ), 200

    except PydanticValidationError as exc:
        return jsonify(
            {
                "success": False,
                "error": "Invalid request payload",
                "details": _pydantic_error_details(exc),
            }
        ), 422

    except DomainError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), exc.status_code