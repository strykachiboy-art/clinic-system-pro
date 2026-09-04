from flask import Blueprint, jsonify, request
from pydantic import ValidationError as PydanticValidationError

from app.core.enums.consultation_enums import ConsultationStatus, ConsultationType
from app.core.enums.role_enums import Role
from app.core.utils.decorators import role_required

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
        "started_at": consultation.started_at.isoformat() if consultation.started_at else None,
        "ended_at": consultation.ended_at.isoformat() if consultation.ended_at else None,
        "created_at": consultation.created_at.isoformat() if consultation.created_at else None,
        "updated_at": consultation.updated_at.isoformat() if consultation.updated_at else None,
    }


def _serialize_template(template):
    return {
        "id": template.id,
        "clinic_id": template.clinic_id,
        "name": template.name,
        "specialty": template.specialty,
        "structure": template.structure,
        "is_active": template.is_active,
        "created_at": template.created_at.isoformat() if template.created_at else None,
    }


# ---------------------------------------------------------------------------
# Consultation lifecycle
# ---------------------------------------------------------------------------

@consultation_bp.post("/")
@role_required(*CONSULTATION_WRITE_ROLES)
def start():
    """
    Start a new consultation.

    POST /api/consultations/
    """
    payload = _payload(ConsultationStartSchema)

    if isinstance(payload, tuple):
        return payload

    consultation = start_consultation(
        **payload.model_dump()
    )

    return jsonify({
        "success": True,
        "data": _serialize_consultation(consultation),
    }), 201


@consultation_bp.get("/<int:consultation_id>")
@role_required(*CONSULTATION_READ_ROLES)
def get(consultation_id: int):
    """
    Get a consultation.

    Historical consultations remain accessible even if the
    clinic is inactive or suspended.

    GET /api/consultations/<consultation_id>
    """
    consultation = get_consultation(
        consultation_id=consultation_id
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

    fields = payload.model_dump(
        exclude_unset=True
    )

    consultation = update_consultation_note(
        consultation_id=consultation_id,
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

    consultation = complete_consultation(
        consultation_id=consultation_id,
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

    consultation = cancel_consultation(
        consultation_id=consultation_id,
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
    Get all consultations for a patient.

    GET /api/consultations/patient/<patient_id>
    """
    consultations = get_consultations_for_patient(
        patient_id=patient_id
    )

    return jsonify({
        "success": True,
        "data": [_serialize_consultation(item) for item in consultations],
    }), 200


# ---------------------------------------------------------------------------
# Staff consultation history
# ---------------------------------------------------------------------------

@consultation_bp.get("/staff/<int:staff_id>")
@role_required(*CONSULTATION_READ_ROLES)
def staff_consultations(staff_id: int):
    """
    Get consultations belonging to a staff member.

    Optional query parameter:

        ?status=in_progress
        ?status=completed
        ?status=cancelled

    GET /api/consultations/staff/<staff_id>
    """
    status = _query_status()

    if isinstance(status, tuple):
        return status

    consultations = get_consultations_for_staff(
        staff_id=staff_id,
        status=status,
    )

    return jsonify({
        "success": True,
        "data": [_serialize_consultation(item) for item in consultations],
    }), 200


# ---------------------------------------------------------------------------
# Consultation templates
# ---------------------------------------------------------------------------

@consultation_bp.post("/templates")
@role_required(*CONSULTATION_TEMPLATE_ROLES)
def create_template():
    """
    Create a consultation template.

    clinic_id may be null for a global template.

    POST /api/consultations/templates
    """
    payload = _payload(ConsultationTemplateCreateSchema)

    if isinstance(payload, tuple):
        return payload

    template = create_consultation_template(
        **payload.model_dump()
    )

    return jsonify({
        "success": True,
        "data": _serialize_template(template),
    }), 201


@consultation_bp.get("/templates")
@role_required(*CONSULTATION_READ_ROLES)
def active_templates():
    raw_clinic_id = request.args.get("clinic_id")

    clinic_id = None

    if raw_clinic_id is not None:
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

    templates = get_active_templates(
        clinic_id=clinic_id
    )

    return jsonify({
        "success": True,
        "data": [_serialize_template(item) for item in templates],
    }), 200