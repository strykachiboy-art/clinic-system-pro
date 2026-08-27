from datetime import datetime, timezone
from app.extensions import db
from app.modules.consultation.models.consultation_model import Consultation, ConsultationTemplate
from app.core.enums.consultation_enums import ConsultationStatus, ConsultationType
from app.core.audit.services.audit_services import create_audit_log
from app.core.enums.audit_enums import AuditAction


def _utcnow():
    return datetime.now(timezone.utc)


def start_consultation(clinic_id, patient_id, staff_id, appointment_id=None,
                        consultation_type=ConsultationType.GENERAL, template_id=None,
                        chief_complaint=None, symptoms=None):
    consultation = Consultation(
        clinic_id=clinic_id,
        patient_id=patient_id,
        staff_id=staff_id,
        appointment_id=appointment_id,
        consultation_type=consultation_type,
        template_id=template_id,
        chief_complaint=chief_complaint,
        symptoms=symptoms,
        status=ConsultationStatus.IN_PROGRESS,
        started_at=_utcnow(),
    )
    db.session.add(consultation)
    db.session.flush()  # ensure consultation.id is available for the log

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Consultation",
        entity_id=consultation.id,
        description=f"Consultation started for patient {patient_id} with staff {staff_id}",
        new_value={"status": consultation.status.value, "consultation_type": consultation_type.value},
    )

    db.session.commit()
    return consultation


def update_consultation_note(consultation_id, **fields):
    consultation = db.get_or_404(Consultation, consultation_id)

    updatable = {
        "chief_complaint", "symptoms", "diagnosis", "treatment_plan",
        "notes", "voice_note_url", "transcribed_text",
    }
    old_value = {}
    new_value = {}

    for key, value in fields.items():
        if key in updatable and value is not None:
            old_value[key] = getattr(consultation, key)
            setattr(consultation, key, value)
            new_value[key] = value

    if new_value:
        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="Consultation",
            entity_id=consultation.id,
            description="Consultation note updated",
            old_value=old_value,
            new_value=new_value,
        )
        db.session.commit()

    return consultation


def complete_consultation(consultation_id, diagnosis, treatment_plan=None, notes=None):
    consultation = Consultation.query.get_or_404(consultation_id)
    old_status = consultation.status.value

    consultation.diagnosis = diagnosis
    if treatment_plan:
        consultation.treatment_plan = treatment_plan
    if notes:
        consultation.notes = notes

    consultation.status = ConsultationStatus.COMPLETED
    consultation.ended_at = _utcnow()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Consultation",
        entity_id=consultation.id,
        description="Consultation completed",
        old_value={"status": old_status},
        new_value={"status": consultation.status.value, "diagnosis": diagnosis},
    )

    db.session.commit()
    return consultation


def cancel_consultation(consultation_id, reason=None):
    consultation = Consultation.query.get_or_404(consultation_id)
    old_status = consultation.status.value

    consultation.status = ConsultationStatus.CANCELLED
    consultation.ended_at = _utcnow()
    if reason:
        consultation.notes = f"{consultation.notes or ''}\n[Cancelled: {reason}]".strip()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Consultation",
        entity_id=consultation.id,
        description="Consultation cancelled",
        old_value={"status": old_status},
        new_value={"status": consultation.status.value, "reason": reason},
    )

    db.session.commit()
    return consultation


def get_consultations_for_patient(patient_id):
    return Consultation.query.filter_by(patient_id=patient_id).order_by(Consultation.started_at.desc()).all()


def get_consultations_for_staff(staff_id, status=None):
    query = Consultation.query.filter_by(staff_id=staff_id)
    if status:
        query = query.filter_by(status=status)
    return query.order_by(Consultation.started_at.desc()).all()


def create_consultation_template(name, structure: dict, clinic_id=None, specialty=None, is_active=True):
    template = ConsultationTemplate(
        clinic_id=clinic_id,
        name=name,
        specialty=specialty,
        structure=structure,
        is_active=is_active,
    )
    db.session.add(template)
    db.session.commit()
    return template


def get_active_templates(clinic_id=None):
    query = ConsultationTemplate.query.filter_by(is_active=True)
    if clinic_id:
        query = query.filter_by(clinic_id=clinic_id)
    return query.all()