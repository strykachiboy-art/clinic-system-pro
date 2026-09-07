from flask import Blueprint, jsonify, request, g
from flask_jwt_extended import get_jwt_identity
from pydantic import ValidationError as PydanticValidationError

from app.core.enums.consultation_enums import (
    ConsultationStatus,
    ConsultationType,
)
from app.core.enums.role_enums import Role
from app.core.utils.decorators import role_required
from app.core.auth.user.models.user_model import User

from app.modules.consultation.schemas.consultation_schema import (
    ConsultationCancelSchema,
    ConsultationCompleteSchema,
    ConsultationStartSchema,
    ConsultationTemplateCreateSchema,
    ConsultationUpdateSchema,
)

from app.modules.consultation.services.consultation_service import (
    cancel_consultation,
    complete_consultation,
    create_consultation_template,
    get_active_templates,
    get_consultation,
    get_consultations_for_patient,
    get_consultations_for_staff,
    start_consultation,
    update_consultation_note,
)


consultation_bp = Blueprint(
    "consultation",
    __name__,
    url_prefix="/api/consultations",
)


# ---------------------------------------------------------------------------
# Role groups
# ---------------------------------------------------------------------------

CONSULTATION_READ_ROLES = (
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
)

CONSULTATION_WRITE_ROLES = (
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
)

CONSULTATION_TEMPLATE_ROLES = (
    Role.ADMIN,
    Role.DOCTOR,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _payload(schema):
    """
    Validate the incoming JSON body using the supplied Pydantic schema.
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
    Parse the optional consultation status query parameter.
    """
    raw_status = request.args.get("status")

    if raw_status is None:
        return None

    try:
        return ConsultationStatus(raw_status)
    except ValueError:
        return jsonify({
            "success": False,
            "error": (
                "Invalid consultation status. "
                "Allowed values: in_progress, completed, cancelled"
            ),
        }), 422


def _query_consultation_type():
    """
    Parse the optional consultation type query parameter.
    """
    raw_type = request.args.get("consultation_type")

    if raw_type is None:
        return None

    try:
        return ConsultationType(raw_type)
    except ValueError:
        return jsonify({
            "success": False,
            "error": (
                "Invalid consultation type. "
                "Allowed values: general, follow_up, specialist, emergency"
            ),
        }), 422


def _is_admin():
    role = getattr(g, "current_user_role", None)

    if isinstance(role, Role):
        return role == Role.ADMIN

    return role == Role.ADMIN.value


def _get_current_user():
    """
    Return the authenticated user.
    """
    user_id = getattr(g, "current_user_id", None)

    if user_id is None:
        try:
            user_id = int(get_jwt_identity())
        except (TypeError, ValueError):
            return None

    return User.query.get(user_id)


def _get_authenticated_clinic_id():
    """
    Resolve the authenticated user's clinic.

    Consultation operations are clinic-scoped. The client must
    never be trusted to provide the tenant clinic_id.
    """
    user = _get_current_user()

    if user is None:
        return None, (
            jsonify({
                "success": False,
                "error": "Authenticated user not found",
            }),
            401,
        )

    clinic_id = getattr(user, "clinic_id", None)

    if clinic_id is None:
        return None, (
            jsonify({
                "success": False,
                "error": "Authenticated user is not assigned to a clinic",
            }),
            403,
        )

    return clinic_id, None


def _resolve_template_clinic_id():
    """
    Resolve the clinic used when creating a consultation template.

    ADMIN may create a global template.
    Non-admin users are always restricted to their own clinic.
    """
    clinic_id, error = _get_authenticated_clinic_id()

    if error is not None:
        if _is_admin():
            return None, None
        return None, error

    return clinic_id, None


def _serialize_consultation(consultation):
    return {
        "id": consultation.id,
        "clinic_id": consultation.clinic_id,
        "patient_id": consultation.patient_id,
        "staff_id": consultation.staff_id,
        "appointment_id": consultation.appointment_id,
        "icd10_code": consultation.icd10_code,
        "consultation_type": consultation.consultation_type.value,
        "status": consultation.status.value,
        "chief_complaint": consultation.chief_complaint,
        "symptoms": consultation.symptoms,
        "diagnosis": consultation.diagnosis,
        "treatment_plan": consultation.treatment_plan,
        "notes": consultation.notes,
        "voice_note_url": consultation.voice_note_url,
        "transcribed_text": consultation.transcribed_text,
        "template_id": consultation.template_id,
        "started_at": (
            consultation.started_at.isoformat()
            if consultation.started_at
            else None
        ),
        "ended_at": (
            consultation.ended_at.isoformat()
            if consultation.ended_at
            else None
        ),
        "created_at": (
            consultation.created_at.isoformat()
            if consultation.created_at
            else None
        ),
        "updated_at": (
            consultation.updated_at.isoformat()
            if consultation.updated_at
            else None
        ),
    }


def _serialize_template(template):
    return {
        "id": template.id,
        "clinic_id": template.clinic_id,
        "name": template.name,
        "specialty": template.specialty,
        "structure": template.structure,
        "is_active": template.is_active,
        "created_at": (
            template.created_at.isoformat()
            if template.created_at
            else None
        ),
    }


# ---------------------------------------------------------------------------
# Consultation lifecycle
# ---------------------------------------------------------------------------

@consultation_bp.post("/")
@role_required(*CONSULTATION_WRITE_ROLES)
def start():
    """
    Start a new consultation for the authenticated user's clinic.

    clinic_id is derived from authentication and cannot be supplied
    by the client.

    POST /api/consultations/
    """
    payload = _payload(ConsultationStartSchema)

    if isinstance(payload, tuple):
        return payload

    clinic_id, error = _get_authenticated_clinic_id()

    if error is not None:
        return error

    consultation = start_consultation(
        clinic_id=clinic_id,
        **payload.model_dump(),
    )

    return jsonify({
        "success": True,
        "data": _serialize_consultation(consultation),
    }), 201


@consultation_bp.get("/<int:consultation_id>")
@role_required(*CONSULTATION_READ_ROLES)
def get(consultation_id: int):
    """
    Get a consultation belonging to the authenticated user's clinic.

    Historical consultations remain accessible even if the clinic
    is inactive or suspended.

    GET /api/consultations/<consultation_id>
    """
    clinic_id, error = _get_authenticated_clinic_id()

    if error is not None:
        return error

    consultation = get_consultation(
        consultation_id=consultation_id,
        clinic_id=clinic_id,
    )

    return jsonify({
        "success": True,
        "data": _serialize_consultation(consultation),
    }), 200


@consultation_bp.patch("/<int:consultation_id>")
@role_required(*CONSULTATION_WRITE_ROLES)
def update(consultation_id: int):
    """
    Update clinical documentation for a consultation.

    PATCH /api/consultations/<consultation_id>
    """
    payload = _payload(ConsultationUpdateSchema)

    if isinstance(payload, tuple):
        return payload

    clinic_id, error = _get_authenticated_clinic_id()

    if error is not None:
        return error

    fields = payload.model_dump(
        exclude_unset=True
    )

    consultation = update_consultation_note(
        consultation_id=consultation_id,
        clinic_id=clinic_id,
        **fields,
    )

    return jsonify({
        "success": True,
        "data": _serialize_consultation(consultation),
    }), 200


@consultation_bp.post("/<int:consultation_id>/complete")
@role_required(*CONSULTATION_WRITE_ROLES)
def complete(consultation_id: int):
    """
    Complete a consultation.

    Diagnosis is required to complete the consultation.

    POST /api/consultations/<consultation_id>/complete
    """
    payload = _payload(ConsultationCompleteSchema)

    if isinstance(payload, tuple):
        return payload

    clinic_id, error = _get_authenticated_clinic_id()

    if error is not None:
        return error

    consultation = complete_consultation(
        consultation_id=consultation_id,
        clinic_id=clinic_id,
        **payload.model_dump(
            exclude_unset=True
        ),
    )

    return jsonify({
        "success": True,
        "data": _serialize_consultation(consultation),
    }), 200


@consultation_bp.post("/<int:consultation_id>/cancel")
@role_required(*CONSULTATION_WRITE_ROLES)
def cancel(consultation_id: int):
    """
    Cancel a consultation.

    POST /api/consultations/<consultation_id>/cancel
    """
    payload = _payload(ConsultationCancelSchema)

    if isinstance(payload, tuple):
        return payload

    clinic_id, error = _get_authenticated_clinic_id()

    if error is not None:
        return error

    consultation = cancel_consultation(
        consultation_id=consultation_id,
        clinic_id=clinic_id,
        **payload.model_dump(
            exclude_unset=True
        ),
    )

    return jsonify({
        "success": True,
        "data": _serialize_consultation(consultation),
    }), 200


# ---------------------------------------------------------------------------
# Patient consultation history
# ---------------------------------------------------------------------------

@consultation_bp.get("/patient/<int:patient_id>")
@role_required(*CONSULTATION_READ_ROLES)
def patient_consultations(patient_id: int):
    """
    Get consultations for a patient belonging to the authenticated clinic.

    GET /api/consultations/patient/<patient_id>
    """
    clinic_id, error = _get_authenticated_clinic_id()

    if error is not None:
        return error

    consultations = get_consultations_for_patient(
        patient_id=patient_id,
        clinic_id=clinic_id,
    )

    return jsonify({
        "success": True,
        "data": [
            _serialize_consultation(item)
            for item in consultations
        ],
    }), 200


# ---------------------------------------------------------------------------
# Staff consultation history
# ---------------------------------------------------------------------------

@consultation_bp.get("/staff/<int:staff_id>")
@role_required(*CONSULTATION_READ_ROLES)
def staff_consultations(staff_id: int):
    """
    Get consultations belonging to a staff member in the
    authenticated user's clinic.

    Optional query parameter:

        ?status=in_progress
        ?status=completed
        ?status=cancelled

    GET /api/consultations/staff/<staff_id>
    """
    status = _query_status()

    if isinstance(status, tuple):
        return status

    clinic_id, error = _get_authenticated_clinic_id()

    if error is not None:
        return error

    consultations = get_consultations_for_staff(
        staff_id=staff_id,
        clinic_id=clinic_id,
        status=status,
    )

    return jsonify({
        "success": True,
        "data": [
            _serialize_consultation(item)
            for item in consultations
        ],
    }), 200


# ---------------------------------------------------------------------------
# Consultation templates
# ---------------------------------------------------------------------------

@consultation_bp.post("/templates")
@role_required(*CONSULTATION_TEMPLATE_ROLES)
def create_template():
    """
    Create a consultation template.

    Non-admin users create templates for their authenticated clinic.

    ADMIN may create a global template by explicitly using the
    global-template service operation.

    POST /api/consultations/templates
    """
    payload = _payload(ConsultationTemplateCreateSchema)

    if isinstance(payload, tuple):
        return payload

    clinic_id, error = _resolve_template_clinic_id()

    if error is not None:
        return error

    template = create_consultation_template(
        clinic_id=clinic_id,
        **payload.model_dump(),
    )

    return jsonify({
        "success": True,
        "data": _serialize_template(template),
    }), 201


@consultation_bp.get("/templates")
@role_required(*CONSULTATION_READ_ROLES)
def active_templates():
    """
    Get active templates available to the authenticated clinic.

    Global templates may be included by the service for the clinic.

    ADMIN may optionally query a specific clinic.
    Non-admin users cannot query another clinic.
    """
    raw_clinic_id = request.args.get("clinic_id")

    authenticated_clinic_id, error = _get_authenticated_clinic_id()

    if _is_admin():
        if raw_clinic_id is None:
            clinic_id = None
        else:
            try:
                clinic_id = int(raw_clinic_id)
            except ValueError:
                return jsonify({
                    "success": False,
                    "error": "clinic_id must be an integer",
                }), 422

            if clinic_id <= 0:
                return jsonify({
                    "success": False,
                    "error": "clinic_id must be greater than 0",
                }), 422
    else:
        if error is not None:
            return error

        if raw_clinic_id is not None:
            try:
                requested_clinic_id = int(raw_clinic_id)
            except ValueError:
                return jsonify({
                    "success": False,
                    "error": "clinic_id must be an integer",
                }), 422

            if requested_clinic_id <= 0:
                return jsonify({
                    "success": False,
                    "error": "clinic_id must be greater than 0",
                }), 422

            if requested_clinic_id != authenticated_clinic_id:
                return jsonify({
                    "success": False,
                    "error": "Access denied",
                }), 403

        clinic_id = authenticated_clinic_id

    templates = get_active_templates(
        clinic_id=clinic_id
    )

    return jsonify({
        "success": True,
        "data": [
            _serialize_template(item)
            for item in templates
        ],
    }), 200