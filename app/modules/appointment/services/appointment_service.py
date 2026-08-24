from datetime import datetime, timedelta
from app.extensions import db, celery
from app.modules.appointment.models.appointment_model import Appointment
from app.core.enums.appointment_enums import AppointmentStatus, AppointmentType
from app.core.audit.services.audit_services import create_audit_log
from app.core.enums.audit_enums import AuditAction


def create_appointment(clinic_id, patient_id, staff_id, scheduled_start, scheduled_end, appointment_type=AppointmentType.IN_PERSON, reason=None):
    appointment = Appointment(
        clinic_id=clinic_id,
        patient_id=patient_id,
        staff_id=staff_id,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        appointment_type=appointment_type,
        status=AppointmentStatus.SCHEDULED,
        reason=reason,
    )
    db.session.add(appointment)
    db.session.flush()  # ensure appointment.id is available for the log

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Appointment",
        entity_id=appointment.id,
        description=f"Appointment created for patient {patient_id} with staff {staff_id}",
        new_value={
            "scheduled_start": scheduled_start.isoformat(),
            "scheduled_end": scheduled_end.isoformat(),
            "status": appointment.status.value,
        },
    )

    db.session.commit()
    return appointment


def reschedule_appointment(appointment_id, new_start, new_end):
    appointment = Appointment.query.get_or_404(appointment_id)

    old_value = {
        "scheduled_start": appointment.scheduled_start.isoformat(),
        "scheduled_end": appointment.scheduled_end.isoformat(),
    }

    appointment.scheduled_start = new_start
    appointment.scheduled_end = new_end
    appointment.reminder_sent = False  # reset so a fresh reminder goes out

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Appointment",
        entity_id=appointment.id,
        description="Appointment rescheduled",
        old_value=old_value,
        new_value={
            "scheduled_start": new_start.isoformat(),
            "scheduled_end": new_end.isoformat(),
        },
    )

    db.session.commit()
    return appointment


def confirm_appointment(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    old_status = appointment.status.value

    appointment.status = AppointmentStatus.CONFIRMED

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Appointment",
        entity_id=appointment.id,
        description="Appointment confirmed",
        old_value={"status": old_status},
        new_value={"status": appointment.status.value},
    )

    db.session.commit()
    return appointment


def cancel_appointment(appointment_id, reason=None):
    appointment = Appointment.query.get_or_404(appointment_id)
    old_status = appointment.status.value

    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancelled_at = datetime.utcnow()
    appointment.cancellation_reason = reason

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Appointment",
        entity_id=appointment.id,
        description="Appointment cancelled",
        old_value={"status": old_status},
        new_value={"status": appointment.status.value, "reason": reason},
    )

    db.session.commit()
    return appointment


def complete_appointment(appointment_id, notes=None):
    appointment = Appointment.query.get_or_404(appointment_id)
    old_status = appointment.status.value

    appointment.status = AppointmentStatus.COMPLETED
    if notes:
        appointment.notes = notes

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Appointment",
        entity_id=appointment.id,
        description="Appointment marked completed",
        old_value={"status": old_status},
        new_value={"status": appointment.status.value},
    )

    db.session.commit()
    return appointment


def mark_no_show(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    old_status = appointment.status.value

    appointment.status = AppointmentStatus.NO_SHOW

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Appointment",
        entity_id=appointment.id,
        description="Appointment marked as no-show",
        old_value={"status": old_status},
        new_value={"status": appointment.status.value},
    )

    db.session.commit()
    return appointment


def get_appointments_for_patient(patient_id):
    return Appointment.query.filter_by(patient_id=patient_id).order_by(Appointment.scheduled_start.desc()).all()


def get_appointments_for_staff(staff_id, date_=None):
    query = Appointment.query.filter_by(staff_id=staff_id)
    if date_:
        query = query.filter(db.func.date(Appointment.scheduled_start) == date_)
    return query.order_by(Appointment.scheduled_start.asc()).all()


@celery.task(name="send_appointment_reminder")
def send_appointment_reminder(appointment_id: int):
    appointment = Appointment.query.get(appointment_id)
    if not appointment or appointment.reminder_sent:
        return

    # call notification service here once notifications module exists
    # notify_patient(appointment.patient_id, "Reminder: your appointment is tomorrow")

    appointment.reminder_sent = True
    db.session.commit()


@celery.task(name="check_upcoming_appointments")
def check_upcoming_appointments():
    """Run periodically (e.g. every hour via celery beat) to queue reminders."""
    tomorrow = datetime.utcnow() + timedelta(days=1)
    upcoming = Appointment.query.filter(
        Appointment.scheduled_start.between(tomorrow, tomorrow + timedelta(hours=1)),
        Appointment.reminder_sent == False,
    ).all()

    for appt in upcoming:
        send_appointment_reminder.delay(appt.id)