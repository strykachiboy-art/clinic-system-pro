from datetime import datetime, timezone

from sqlalchemy import or_

from app.extensions import db

from app.core.audit.services.audit_service import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.appointment_enums import AppointmentStatus
from app.core.enums.consultation_enums import (
    ConsultationStatus,
    ConsultationType,
)
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import transactional

from app.modules.clinic.services.clinic_service import (
    ensure_clinic_active,
)

from app.modules.consultation.models.consultation_model import (
    Consultation,
    ConsultationTemplate,
)

from app.modules.patient.services.patient_service import (
    get_patient,
)

from app.modules.staff.services.staff_service import (
    get_staff,
)


def _utcnow():
    return datetime.now(timezone.utc)


# ============================================================
# Retrieval helpers
# ============================================================

def get_consultation(
    consultation_id: int,
    clinic_id: int | None = None,
    *,
    for_update: bool = False,
) -> Consultation:
    """
    Retrieve a consultation.

    Historical consultations remain readable even when the clinic
    is inactive or suspended.

    When clinic_id is supplied, the consultation must belong to
    that clinic. This is the tenant-isolation boundary used by
    authenticated API operations.
    """
    if consultation_id <= 0:
        raise ValidationError(
            "Consultation ID must be greater than 0"
        )

    query = Consultation.query.filter(
        Consultation.id == consultation_id
    )

    if clinic_id is not None:
        if clinic_id <= 0:
            raise ValidationError(
                "Clinic ID must be greater than 0"
            )

        query = query.filter(
            Consultation.clinic_id == clinic_id
        )

    if for_update:
        query = query.with_for_update()

    consultation = query.first()

    if consultation is None:
        raise NotFoundError(
            f"Consultation {consultation_id} not found"
        )

    return consultation


def get_consultation_template(
    template_id: int,
) -> ConsultationTemplate:
    """
    Retrieve a consultation template regardless of whether
    it is currently active.

    Tenant authorization is handled by the caller/service
    operation that uses the template.
    """
    if template_id <= 0:
        raise ValidationError(
            "Consultation template ID must be greater than 0"
        )

    template = db.session.get(
        ConsultationTemplate,
        template_id,
    )

    if template is None:
        raise NotFoundError(
            f"Consultation template {template_id} not found"
        )

    return template


# ============================================================
# Validation helpers
# ============================================================

def _validate_consultation_participants(
    *,
    clinic_id: int,
    patient_id: int,
    staff_id: int,
):
    """
    Validate the clinic, patient, and attending staff member.

    Starting a consultation is an operational write, so the
    clinic must be ACTIVE.

    The patient and staff member must both belong to the
    specified clinic.
    """
    if clinic_id <= 0:
        raise ValidationError(
            "Clinic ID must be greater than 0"
        )

    if patient_id <= 0:
        raise ValidationError(
            "Patient ID must be greater than 0"
        )

    if staff_id <= 0:
        raise ValidationError(
            "Staff ID must be greater than 0"
        )

    clinic = ensure_clinic_active(clinic_id)

    patient = get_patient(patient_id)
    staff = get_staff(staff_id)

    if patient.clinic_id != clinic.id:
        raise ConflictError(
            f"Patient {patient_id} does not belong "
            f"to clinic {clinic_id}"
        )

    if staff.clinic_id != clinic.id:
        raise ConflictError(
            f"Staff {staff_id} does not belong "
            f"to clinic {clinic_id}"
        )

    return clinic, patient, staff


def _validate_template(
    *,
    clinic_id: int,
    template_id: int | None,
):
    """
    Validate an optional consultation template.

    A template may be:

    - global: clinic_id is None
    - clinic-specific: clinic_id matches the consultation clinic

    Only active templates may be used for new consultations.
    """
    if template_id is None:
        return None

    template = get_consultation_template(
        template_id
    )

    if not template.is_active:
        raise ValidationError(
            f"Consultation template {template_id} "
            "is not active"
        )

    if (
        template.clinic_id is not None
        and template.clinic_id != clinic_id
    ):
        raise ConflictError(
            f"Consultation template {template_id} "
            f"does not belong to clinic {clinic_id}"
        )

    return template


def _validate_appointment(
    *,
    clinic_id: int,
    patient_id: int,
    staff_id: int,
    appointment_id: int | None,
):
    """
    Validate an optional appointment associated with a
    consultation.

    The appointment must:

    - exist
    - belong to the same clinic
    - belong to the same patient
    - belong to the same staff member
    - be SCHEDULED or CONFIRMED

    The appointment row is locked to prevent concurrent
    consultation creation from racing against appointment state.
    """
    if appointment_id is None:
        return None

    if appointment_id <= 0:
        raise ValidationError(
            "Appointment ID must be greater than 0"
        )

    from app.modules.appointment.models.appointment_model import (
        Appointment,
    )

    appointment = (
        Appointment.query
        .filter(Appointment.id == appointment_id)
        .with_for_update()
        .first()
    )

    if appointment is None:
        raise NotFoundError(
            f"Appointment {appointment_id} not found"
        )

    if appointment.clinic_id != clinic_id:
        raise ConflictError(
            f"Appointment {appointment_id} does not belong "
            f"to clinic {clinic_id}"
        )

    if appointment.patient_id != patient_id:
        raise ConflictError(
            f"Appointment {appointment_id} does not belong "
            f"to patient {patient_id}"
        )

    if appointment.staff_id != staff_id:
        raise ConflictError(
            f"Appointment {appointment_id} does not belong "
            f"to staff member {staff_id}"
        )

    if appointment.status not in (
        AppointmentStatus.SCHEDULED,
        AppointmentStatus.CONFIRMED,
    ):
        raise ConflictError(
            f"Appointment {appointment_id} is currently "
            f"'{appointment.status.value}' and cannot start "
            "a consultation"
        )

    return appointment


def _validate_consultation_can_be_completed(
    consultation: Consultation,
):
    """
    Only IN_PROGRESS consultations can be completed.
    """
    if consultation.status == ConsultationStatus.COMPLETED:
        raise ConflictError(
            f"Consultation {consultation.id} "
            "is already completed"
        )

    if consultation.status == ConsultationStatus.CANCELLED:
        raise ConflictError(
            f"Consultation {consultation.id} is cancelled "
            "and cannot be completed"
        )

    if consultation.status != ConsultationStatus.IN_PROGRESS:
        raise ConflictError(
            f"Consultation {consultation.id} is currently "
            f"'{consultation.status.value}' and cannot be completed"
        )


def _validate_consultation_can_be_cancelled(
    consultation: Consultation,
):
    """
    Only IN_PROGRESS consultations can be cancelled.
    """
    if consultation.status == ConsultationStatus.COMPLETED:
        raise ConflictError(
            f"Consultation {consultation.id} is already "
            "completed and cannot be cancelled"
        )

    if consultation.status == ConsultationStatus.CANCELLED:
        raise ConflictError(
            f"Consultation {consultation.id} "
            "is already cancelled"
        )

    if consultation.status != ConsultationStatus.IN_PROGRESS:
        raise ConflictError(
            f"Consultation {consultation.id} is currently "
            f"'{consultation.status.value}' and cannot be cancelled"
        )


# ============================================================
# Start consultation
# ============================================================

@transactional
def start_consultation(
    clinic_id: int,
    patient_id: int,
    staff_id: int,
    appointment_id: int | None = None,
    consultation_type: ConsultationType = ConsultationType.GENERAL,
    template_id: int | None = None,
    chief_complaint: str | None = None,
    symptoms: str | None = None,
) -> Consultation:
    """
    Start a new consultation.

    Operational rules:

    - Clinic must be ACTIVE.
    - Patient must belong to the clinic.
    - Staff must belong to the clinic.
    - Appointment, if supplied, must belong to the same
      clinic/patient/staff and be SCHEDULED or CONFIRMED.
    - Template, if supplied, must be active and either global
      or belong to the same clinic.
    """
    clinic, patient, staff = (
        _validate_consultation_participants(
            clinic_id=clinic_id,
            patient_id=patient_id,
            staff_id=staff_id,
        )
    )

    _validate_template(
        clinic_id=clinic.id,
        template_id=template_id,
    )

    _validate_appointment(
        clinic_id=clinic.id,
        patient_id=patient.id,
        staff_id=staff.id,
        appointment_id=appointment_id,
    )

    consultation = Consultation(
        clinic_id=clinic.id,
        patient_id=patient.id,
        staff_id=staff.id,
        appointment_id=appointment_id,
        consultation_type=consultation_type,
        template_id=template_id,
        chief_complaint=chief_complaint,
        symptoms=symptoms,
        status=ConsultationStatus.IN_PROGRESS,
        started_at=_utcnow(),
    )

    db.session.add(consultation)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Consultation",
        entity_id=consultation.id,
        description=(
            f"Consultation started for patient "
            f"{patient.id} with staff {staff.id}"
        ),
        new_value={
            "clinic_id": clinic.id,
            "patient_id": patient.id,
            "staff_id": staff.id,
            "appointment_id": appointment_id,
            "template_id": template_id,
            "status": consultation.status.value,
            "consultation_type": (
                consultation.consultation_type.value
            ),
        },
    )

    return consultation


# ============================================================
# Update consultation notes
# ============================================================

@transactional
def update_consultation_note(
    consultation_id: int,
    clinic_id: int,
    **fields,
) -> Consultation:
    """
    Update clinical documentation.

    The consultation must belong to the authenticated clinic.

    The clinic must be ACTIVE because documentation changes are
    operational writes.

    Cancelled consultations cannot be edited.

    Completed consultations remain editable to preserve the
    existing application's documentation-correction workflow.
    Every actual change is recorded in the audit log.
    """
    consultation = get_consultation(
        consultation_id=consultation_id,
        clinic_id=clinic_id,
        for_update=True,
    )

    ensure_clinic_active(
        consultation.clinic_id
    )

    if consultation.status == ConsultationStatus.CANCELLED:
        raise ConflictError(
            f"Consultation {consultation.id} is cancelled "
            "and cannot be updated"
        )

    updatable = {
        "icd10_code",
        "chief_complaint",
        "symptoms",
        "diagnosis",
        "treatment_plan",
        "notes",
        "voice_note_url",
        "transcribed_text",
    }

    unknown = set(fields) - updatable

    if unknown:
        raise ValidationError(
            "Unknown consultation field(s): "
            + ", ".join(sorted(unknown))
        )

    old_value = {}
    new_value = {}

    for key, value in fields.items():
        if value is None:
            continue

        if isinstance(value, str):
            value = value.strip()

        current_value = getattr(
            consultation,
            key,
        )

        if current_value == value:
            continue

        old_value[key] = current_value
        new_value[key] = value

        setattr(
            consultation,
            key,
            value,
        )

    if not new_value:
        return consultation

    audit_action = AuditAction.UPDATE

    if consultation.status == ConsultationStatus.COMPLETED:
        description = "Completed consultation documentation amended"
    else:
        description = "Consultation note updated"

    create_audit_log(
        action=audit_action,
        entity_type="Consultation",
        entity_id=consultation.id,
        description=description,
        old_value=old_value,
        new_value=new_value,
    )

    return consultation


# ============================================================
# Complete consultation
# ============================================================

@transactional
def complete_consultation(
    consultation_id: int,
    clinic_id: int,
    diagnosis: str,
    treatment_plan: str | None = None,
    notes: str | None = None,
) -> Consultation:
    """
    Complete an in-progress consultation.

    Diagnosis is mandatory.

    The consultation must belong to the authenticated clinic.
    """
    consultation = get_consultation(
        consultation_id=consultation_id,
        clinic_id=clinic_id,
        for_update=True,
    )

    ensure_clinic_active(
        consultation.clinic_id
    )

    _validate_consultation_can_be_completed(
        consultation
    )

    if not diagnosis or not diagnosis.strip():
        raise ValidationError(
            "Diagnosis is required to complete "
            "a consultation"
        )

    old_status = consultation.status.value

    consultation.diagnosis = diagnosis.strip()

    if treatment_plan is not None:
        consultation.treatment_plan = treatment_plan.strip()

    if notes is not None:
        consultation.notes = notes.strip()

    consultation.status = ConsultationStatus.COMPLETED
    consultation.ended_at = _utcnow()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Consultation",
        entity_id=consultation.id,
        description="Consultation completed",
        old_value={
            "status": old_status,
        },
        new_value={
            "status": consultation.status.value,
            "diagnosis": consultation.diagnosis,
        },
    )

    return consultation


# ============================================================
# Cancel consultation
# ============================================================

@transactional
def cancel_consultation(
    consultation_id: int,
    clinic_id: int,
    reason: str | None = None,
) -> Consultation:
    """
    Cancel an in-progress consultation.

    The consultation must belong to the authenticated clinic.
    """
    consultation = get_consultation(
        consultation_id=consultation_id,
        clinic_id=clinic_id,
        for_update=True,
    )

    ensure_clinic_active(
        consultation.clinic_id
    )

    _validate_consultation_can_be_cancelled(
        consultation
    )

    old_status = consultation.status.value

    consultation.status = ConsultationStatus.CANCELLED
    consultation.ended_at = _utcnow()

    cleaned_reason = None

    if reason is not None:
        cleaned_reason = reason.strip()

        if cleaned_reason:
            existing_notes = (
                consultation.notes or ""
            ).strip()

            cancellation_note = (
                f"[Cancelled: {cleaned_reason}]"
            )

            consultation.notes = (
                f"{existing_notes}\n{cancellation_note}"
                if existing_notes
                else cancellation_note
            )

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Consultation",
        entity_id=consultation.id,
        description="Consultation cancelled",
        old_value={
            "status": old_status,
        },
        new_value={
            "status": consultation.status.value,
            "reason": cleaned_reason,
        },
    )

    return consultation


# ============================================================
# Patient consultation history
# ============================================================

def get_consultations_for_patient(
    patient_id: int,
    clinic_id: int,
) -> list[Consultation]:
    """
    Return consultation history for a patient within the
    authenticated clinic.

    Historical consultations remain accessible regardless of
    clinic status.
    """
    if patient_id <= 0:
        raise ValidationError(
            "Patient ID must be greater than 0"
        )

    if clinic_id <= 0:
        raise ValidationError(
            "Clinic ID must be greater than 0"
        )

    patient = get_patient(patient_id)

    if patient.clinic_id != clinic_id:
        raise NotFoundError(
            f"Patient {patient_id} not found"
        )

    return (
        Consultation.query
        .filter(
            Consultation.clinic_id == clinic_id,
            Consultation.patient_id == patient_id,
        )
        .order_by(
            Consultation.started_at.desc()
        )
        .all()
    )


# ============================================================
# Staff consultation history
# ============================================================

def get_consultations_for_staff(
    staff_id: int,
    clinic_id: int,
    status: ConsultationStatus | None = None,
) -> list[Consultation]:
    """
    Return consultation history associated with a staff member
    within the authenticated clinic.

    Historical consultations remain accessible regardless of
    clinic status.
    """
    if staff_id <= 0:
        raise ValidationError(
            "Staff ID must be greater than 0"
        )

    if clinic_id <= 0:
        raise ValidationError(
            "Clinic ID must be greater than 0"
        )

    staff = get_staff(staff_id)

    if staff.clinic_id != clinic_id:
        raise NotFoundError(
            f"Staff member {staff_id} not found"
        )

    query = Consultation.query.filter(
        Consultation.clinic_id == clinic_id,
        Consultation.staff_id == staff_id,
    )

    if status is not None:
        query = query.filter(
            Consultation.status == status
        )

    return (
        query
        .order_by(
            Consultation.started_at.desc()
        )
        .all()
    )


# ============================================================
# Consultation templates
# ============================================================

@transactional
def create_consultation_template(
    name: str,
    structure: dict,
    clinic_id: int | None = None,
    specialty: str | None = None,
    is_active: bool = True,
) -> ConsultationTemplate:
    """
    Create a consultation template.

    If clinic_id is supplied, the clinic must be ACTIVE.

    If clinic_id is None, the template is global.

    Authorization for creating a global template belongs to the
    route/authentication layer. The service only persists the
    already-resolved clinic scope.
    """
    if not name or not name.strip():
        raise ValidationError(
            "Template name is required"
        )

    if not isinstance(structure, dict):
        raise ValidationError(
            "Template structure must be an object"
        )

    if not structure:
        raise ValidationError(
            "Template structure cannot be empty"
        )

    if clinic_id is not None:
        if clinic_id <= 0:
            raise ValidationError(
                "Clinic ID must be greater than 0"
            )

        ensure_clinic_active(
            clinic_id
        )

    cleaned_specialty = (
        specialty.strip()
        if isinstance(specialty, str)
        else specialty
    )

    template = ConsultationTemplate(
        clinic_id=clinic_id,
        name=name.strip(),
        specialty=cleaned_specialty,
        structure=structure,
        is_active=is_active,
    )

    db.session.add(template)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="ConsultationTemplate",
        entity_id=template.id,
        description=(
            f"Consultation template "
            f"'{template.name}' created"
        ),
        new_value={
            "clinic_id": clinic_id,
            "name": template.name,
            "specialty": cleaned_specialty,
            "is_active": is_active,
        },
    )

    return template


def get_active_templates(
    clinic_id: int | None = None,
) -> list[ConsultationTemplate]:
    """
    Return active consultation templates.

    When clinic_id is supplied:

    - global templates are included
    - clinic-specific templates for that clinic are included

    When clinic_id is omitted:

    - all active templates are returned

    The route controls whether omitting clinic_id is authorized.
    """
    if clinic_id is not None and clinic_id <= 0:
        raise ValidationError(
            "Clinic ID must be greater than 0"
        )

    query = ConsultationTemplate.query.filter(
        ConsultationTemplate.is_active.is_(True)
    )

    if clinic_id is not None:
        query = query.filter(
            or_(
                ConsultationTemplate.clinic_id.is_(None),
                ConsultationTemplate.clinic_id == clinic_id,
            )
        )

    return (
        query
        .order_by(
            ConsultationTemplate.name.asc()
        )
        .all()
    )