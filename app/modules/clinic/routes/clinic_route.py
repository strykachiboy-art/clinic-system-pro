from flask import Blueprint, jsonify, request
from pydantic import ValidationError as PydanticValidationError

from app.core.enums.clinic_enums import ClinicStatus
from app.core.enums.role_enums import Role
from app.core.utils.decorators import role_required

from app.modules.clinic.schemas.clinic_schema import (
    ClinicAICreditsUpdateSchema,
    ClinicBranchConfigurationSchema,
    ClinicBranchCreateSchema,
    ClinicCreateSchema,
    ClinicStatusUpdateSchema,
    ClinicUpdateSchema,
)

from app.modules.clinic.services.clinic_service import (
    add_ai_credits,
    change_status,
    create_branch,
    create_clinic,
    get_clinic,
    list_branches,
    list_clinics,
    regenerate_api_token,
    update_branch_configuration,
    update_clinic,
)


# ============================================================
# BLUEPRINT
# ============================================================

clinic_bp = Blueprint(
    "clinic",
    __name__,
    url_prefix="/api/clinics",
)


# ============================================================
# ROLE GROUPS
# ============================================================

CLINIC_READ_ROLES = (
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
    Role.PHARMACIST,
    Role.LAB_TECHNICIAN,
    Role.RECEPTIONIST,
    Role.PARAMEDIC,
    Role.EMT,
    Role.DRIVER,
    Role.AMBULANCE_DISPATCHER,
    Role.AMBULANCE_COORDINATOR,
)

CLINIC_ADMIN_ROLES = (
    Role.ADMIN,
)


# ============================================================
# VALIDATION HELPERS
# ============================================================

def _payload(schema):
    """
    Validate JSON request body using a Pydantic schema.

    Returns:
        Pydantic model on success.
        Flask JSON response on validation failure.
    """
    try:
        return schema.model_validate(
            request.get_json(silent=True) or {}
        )
    except PydanticValidationError as exc:
        return jsonify({
            "success": False,
            "error": exc.errors(),
        }), 422


def _query_status():
    """
    Parse optional clinic status query parameter.

    Example:

        GET /api/clinics?status=active
    """
    raw_status = request.args.get("status")

    if raw_status is None:
        return None

    try:
        return ClinicStatus(raw_status)
    except ValueError:
        return jsonify({
            "success": False,
            "error": (
                "Invalid clinic status. "
                "Allowed values: active, inactive, suspended"
            ),
        }), 422


# ============================================================
# CREATE CLINIC
# ============================================================

@clinic_bp.post("/")
@role_required(*CLINIC_ADMIN_ROLES)
def create():
    payload = _payload(ClinicCreateSchema)

    if isinstance(payload, tuple):
        return payload

    clinic = create_clinic(
        **payload.model_dump()
    )

    return jsonify({
        "success": True,
        "data": clinic,
    }), 201


# ============================================================
# LIST CLINICS
# ============================================================

@clinic_bp.get("/")
@role_required(*CLINIC_READ_ROLES)
def list_all():
    status = _query_status()

    if isinstance(status, tuple):
        return status

    clinics = list_clinics(
        status=status
    )

    return jsonify({
        "success": True,
        "data": clinics,
    }), 200


# ============================================================
# GET CLINIC
# ============================================================

@clinic_bp.get("/<int:clinic_id>")
@role_required(*CLINIC_READ_ROLES)
def get(clinic_id: int):
    clinic = get_clinic(
        clinic_id=clinic_id
    )

    return jsonify({
        "success": True,
        "data": clinic,
    }), 200


# ============================================================
# LIST BRANCHES
# ============================================================

@clinic_bp.get("/<int:clinic_id>/branches")
@role_required(*CLINIC_READ_ROLES)
def branches(clinic_id: int):
    clinics = list_branches(
        clinic_id=clinic_id
    )

    return jsonify({
        "success": True,
        "data": clinics,
    }), 200


# ============================================================
# CREATE BRANCH
# ============================================================

@clinic_bp.post("/<int:clinic_id>/branches")
@role_required(*CLINIC_ADMIN_ROLES)
def create_clinic_branch(clinic_id: int):
    payload = _payload(
        ClinicBranchCreateSchema
    )

    if isinstance(payload, tuple):
        return payload

    clinic = create_branch(
        parent_clinic_id=clinic_id,
        **payload.model_dump(),
    )

    return jsonify({
        "success": True,
        "data": clinic,
    }), 201


# ============================================================
# UPDATE CLINIC PROFILE
# ============================================================

@clinic_bp.patch("/<int:clinic_id>")
@role_required(*CLINIC_ADMIN_ROLES)
def update(clinic_id: int):
    payload = _payload(
        ClinicUpdateSchema
    )

    if isinstance(payload, tuple):
        return payload

    fields = payload.model_dump(
        exclude_unset=True
    )

    clinic = update_clinic(
        clinic_id=clinic_id,
        **fields,
    )

    return jsonify({
        "success": True,
        "data": clinic,
    }), 200


# ============================================================
# UPDATE BRANCH CONFIGURATION
# ============================================================

@clinic_bp.patch(
    "/<int:clinic_id>/branch-configuration"
)
@role_required(*CLINIC_ADMIN_ROLES)
def update_branch(clinic_id: int):
    payload = _payload(
        ClinicBranchConfigurationSchema
    )

    if isinstance(payload, tuple):
        return payload

    fields = payload.model_dump(
        exclude_unset=True
    )

    clinic = update_branch_configuration(
        clinic_id=clinic_id,
        **fields,
    )

    return jsonify({
        "success": True,
        "data": clinic,
    }), 200


# ============================================================
# CHANGE CLINIC STATUS
# ============================================================

@clinic_bp.patch(
    "/<int:clinic_id>/status"
)
@role_required(*CLINIC_ADMIN_ROLES)
def status(clinic_id: int):
    payload = _payload(
        ClinicStatusUpdateSchema
    )

    if isinstance(payload, tuple):
        return payload

    clinic = change_status(
        clinic_id=clinic_id,
        new_status=payload.status,
    )

    return jsonify({
        "success": True,
        "data": clinic,
    }), 200


# ============================================================
# ADD AI CREDITS
# ============================================================

@clinic_bp.patch(
    "/<int:clinic_id>/ai-credits"
)
@role_required(*CLINIC_ADMIN_ROLES)
def ai_credits(clinic_id: int):
    payload = _payload(
        ClinicAICreditsUpdateSchema
    )

    if isinstance(payload, tuple):
        return payload

    clinic = add_ai_credits(
        clinic_id=clinic_id,
        amount=payload.amount,
    )

    return jsonify({
        "success": True,
        "data": clinic,
    }), 200


# ============================================================
# REGENERATE API TOKEN
# ============================================================

@clinic_bp.post(
    "/<int:clinic_id>/api-token/regenerate"
)
@role_required(*CLINIC_ADMIN_ROLES)
def regenerate_token(clinic_id: int):
    token = regenerate_api_token(
        clinic_id=clinic_id
    )

    return jsonify({
        "success": True,
        "data": {
            "api_token": token,
        },
    }), 200