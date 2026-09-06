from datetime import datetime, timedelta, timezone

from app.extensions import db, celery

from app.core.audit.services.audit_service import create_audit_log
from app.core.enums.appointment_enums import (
    AppointmentStatus,
    AppointmentType,
)
from app.core.enums.audit_enums import AuditAction
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import transactional

from app.modules.appointment.models.appointment_model import Appointment
from app.modules.patient.services.patient_service import get_patient
from app.modules.staff.services.staff_service import get_staff
from app.modules.clinic.services.clinic_service import get_clinic


# ---------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------


def _utcnow():
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def _get_appointment(
    appointment_id: int,
    clinic_id: int | None = None,
) -> Appointment:
    """
    Fetch an appointment.

    When clinic_id is supplied, the appointment MUST belong to
    that clinic. This prevents cross-clinic access through a known
    appointment ID.
    """
    query = Appointment.query.filter(
        Appointment.id == appointment_id
    )

    if clinic_id is not None:
        query = query.filter(
            Appointment.clinic_id == clinic_id
        )

    appointment = query.first()

    if appointment is None:
        raise NotFoundError(
            f"Appointment {appointment_id} not found"
        )

    return appointment


def _validate_schedule_times(
    scheduled_start,
    scheduled_end,
):
    """Validate appointment start/end times."""
    if scheduled_start is None or scheduled_end is None:
        raise ValidationError(
            "scheduled_start and scheduled_end are required"
        )

    if scheduled_end <= scheduled_start:
        raise ValidationError(
            "scheduled_end must be later than scheduled_start"
        )


def _validate_reschedule_times(
    new_start,
    new_end,
):
    """Validate new appointment start/end times."""
    if new_start is None or new_end is None:
        raise ValidationError(
            "new_start and new_end are required"
        )

    if new_end <= new_start:
        raise ValidationError(
            "new_end must be later than new_start"
        )


def _ensure_status(
    appointment: Appointment,
    *allowed_statuses,
):
    """
    Ensure an appointment is currently in one of the allowed states.
    """
    if appointment.status not in allowed_statuses:
        allowed = ", ".join(
            status.value
            for status in allowed_statuses
        )

        raise ConflictError(
            f"Appointment {appointment.id} is currently "
            f"'{appointment.status.value}' and cannot perform "
            f"this action. Allowed status: {allowed}"
        )


def _validate_appointment_participants(
    clinic_id: int,
    patient_id: int,
    staff_id: int,
):
    """
    Validate that the clinic, patient, and staff exist and that
    both participants belong to the authenticated clinic.

    Returns:
        tuple: clinic, patient, staff
    """
    clinic = get_clinic(clinic_id)
    patient = get_patient(patient_id)
    staff = get_staff(staff_id)

    if patient.clinic_id != clinic.id:
        raise ConflictError(
            f"Patient {patient_id} does not belong to "
            f"clinic {clinic_id}"
        )

    if staff.clinic_id != clinic.id:
        raise ConflictError(
            f"Staff {staff_id} does not belong to "
            f"clinic {clinic_id}"
        )

    return clinic, patient, staff


# ---------------------------------------------------------------------
# Schedule conflict helpers
# ---------------------------------------------------------------------


def _find_patient_overlap(
    patient_id: int,
    scheduled_start,
    scheduled_end,
    clinic_id: int | None = None,
    exclude_appointment_id: int | None = None,
):
    """
    Find an active appointment belonging to the patient that overlaps
    the requested period.

    Only SCHEDULED and CONFIRMED appointments block availability.
    """
    query = Appointment.query.filter(
        Appointment.patient_id == patient_id,
        Appointment.status.in_(
            [
                AppointmentStatus.SCHEDULED,
                AppointmentStatus.CONFIRMED,
            ]
        ),
        Appointment.scheduled_start < scheduled_end,
        Appointment.scheduled_end > scheduled_start,
    )

    if clinic_id is not None:
        query = query.filter(
            Appointment.clinic_id == clinic_id
        )

    if exclude_appointment_id is not None:
        query = query.filter(
            Appointment.id != exclude_appointment_id
        )

    return query.first()


def _find_staff_overlap(
    staff_id: int,
    scheduled_start,
    scheduled_end,
    clinic_id: int | None = None,
    exclude_appointment_id: int | None = None,
):
    """
    Find an active appointment belonging to the staff member that
    overlaps the requested period.

    Only SCHEDULED and CONFIRMED appointments block availability.
    """
    query = Appointment.query.filter(
        Appointment.staff_id == staff_id,
        Appointment.status.in_(
            [
                AppointmentStatus.SCHEDULED,
                AppointmentStatus.CONFIRMED,
            ]
        ),
        Appointment.scheduled_start < scheduled_end,
        Appointment.scheduled_end > scheduled_start,
    )

    if clinic_id is not None:
        query = query.filter(
            Appointment.clinic_id == clinic_id
        )

    if exclude_appointment_id is not None:
        query = query.filter(
            Appointment.id != exclude_appointment_id
        )

    return query.first()


def _ensure_no_schedule_conflict(
    patient_id: int,
    staff_id: int,
    scheduled_start,
    scheduled_end,
    clinic_id: int | None = None,
    exclude_appointment_id: int | None = None,
):
    """
    Ensure neither the patient nor staff member already has an
    overlapping active appointment.
    """
    patient_conflict = _find_patient_overlap(
        patient_id=patient_id,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        clinic_id=clinic_id,
        exclude_appointment_id=exclude_appointment_id,
    )

    if patient_conflict is not None:
        raise ConflictError(
            f"Patient {patient_id} already has an appointment "
            f"overlapping this time period "
            f"(appointment {patient_conflict.id})"
        )

    staff_conflict = _find_staff_overlap(
        staff_id=staff_id,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        clinic_id=clinic_id,
        exclude_appointment_id=exclude_appointment_id,
    )

    if staff_conflict is not None:
        raise ConflictError(
            f"Staff {staff_id} already has an appointment "
            f"overlapping this time period "
            f"(appointment {staff_conflict.id})"
        )


# ---------------------------------------------------------------------
# Appointment creation
# ---------------------------------------------------------------------


@transactional
def create_appointment(
    clinic_id: int,
    patient_id: int,
    staff_id: int,
    scheduled_start,
    scheduled_end,
    appointment_type=AppointmentType.IN_PERSON,
    reason=None,
    notes=None,
):
    _validate_schedule_times(
        scheduled_start,
        scheduled_end,
    )

    _validate_appointment_participants(
        clinic_id=clinic_id,
        patient_id=patient_id,
        staff_id=staff_id,
    )

    _ensure_no_schedule_conflict(
        patient_id=patient_id,
        staff_id=staff_id,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        clinic_id=clinic_id,
    )

    appointment = Appointment(
        clinic_id=clinic_id,
        patient_id=patient_id,
        staff_id=staff_id,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        appointment_type=appointment_type,
        status=AppointmentStatus.SCHEDULED,
        reason=reason,
        notes=notes,
    )

    db.session.add(appointment)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Appointment",
        entity_id=appointment.id,
        description=(
            f"Appointment created for patient {patient_id} "
            f"with staff {staff_id}"
        ),
        new_value={
            "clinic_id": clinic_id,
            "patient_id": patient_id,
            "staff_id": staff_id,
            "scheduled_start": scheduled_start.isoformat(),
            "scheduled_end": scheduled_end.isoformat(),
            "appointment_type": (
                appointment.appointment_type.value
            ),
            "status": appointment.status.value,
            "reason": reason,
            "notes": notes,
        },
    )

    return appointment


# ---------------------------------------------------------------------
# Rescheduling
# ---------------------------------------------------------------------


@transactional
def reschedule_appointment(
    appointment_id: int,
    clinic_id: int,
    new_start,
    new_end,
):
    """
    Reschedule an existing appointment.

    Only SCHEDULED or CONFIRMED appointments can be rescheduled.

    The appointment must belong to clinic_id.
    """
    appointment = _get_appointment(
        appointment_id,
        clinic_id=clinic_id,
    )

    _ensure_status(
        appointment,
        AppointmentStatus.SCHEDULED,
        AppointmentStatus.CONFIRMED,
    )

    _validate_reschedule_times(
        new_start,
        new_end,
    )

    _ensure_no_schedule_conflict(
        patient_id=appointment.patient_id,
        staff_id=appointment.staff_id,
        scheduled_start=new_start,
        scheduled_end=new_end,
        clinic_id=clinic_id,
        exclude_appointment_id=appointment.id,
    )

    old_value = {
        "scheduled_start": (
            appointment.scheduled_start.isoformat()
        ),
        "scheduled_end": (
            appointment.scheduled_end.isoformat()
        ),
    }

    appointment.scheduled_start = new_start
    appointment.scheduled_end = new_end

    # The old reminder is no longer valid.
    appointment.reminder_sent = False

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

    return appointment


# ---------------------------------------------------------------------
# Appointment status transitions
# ---------------------------------------------------------------------


@transactional
def confirm_appointment(
    appointment_id: int,
    clinic_id: int,
):
    """
    Confirm a scheduled appointment.

    The appointment must belong to clinic_id.
    """
    appointment = _get_appointment(
        appointment_id,
        clinic_id=clinic_id,
    )

    _ensure_status(
        appointment,
        AppointmentStatus.SCHEDULED,
    )

    old_status = appointment.status.value

    appointment.status = AppointmentStatus.CONFIRMED

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Appointment",
        entity_id=appointment.id,
        description="Appointment confirmed",
        old_value={
            "status": old_status,
        },
        new_value={
            "status": appointment.status.value,
        },
    )

    return appointment


@transactional
def cancel_appointment(
    appointment_id: int,
    clinic_id: int,
    reason=None,
):
    """
    Cancel an appointment.

    Scheduled and confirmed appointments may be cancelled.

    The appointment must belong to clinic_id.
    """
    appointment = _get_appointment(
        appointment_id,
        clinic_id=clinic_id,
    )

    _ensure_status(
        appointment,
        AppointmentStatus.SCHEDULED,
        AppointmentStatus.CONFIRMED,
    )

    old_status = appointment.status.value

    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancelled_at = _utcnow()
    appointment.cancellation_reason = reason

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Appointment",
        entity_id=appointment.id,
        description="Appointment cancelled",
        old_value={
            "status": old_status,
        },
        new_value={
            "status": appointment.status.value,
            "reason": reason,
        },
    )

    return appointment


@transactional
def complete_appointment(
    appointment_id: int,
    clinic_id: int,
    notes=None,
):
    """
    Mark a confirmed appointment as completed.

    The appointment must belong to clinic_id.
    """
    appointment = _get_appointment(
        appointment_id,
        clinic_id=clinic_id,
    )

    _ensure_status(
        appointment,
        AppointmentStatus.CONFIRMED,
    )

    old_status = appointment.status.value

    appointment.status = AppointmentStatus.COMPLETED

    if notes is not None:
        appointment.notes = notes

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Appointment",
        entity_id=appointment.id,
        description="Appointment marked completed",
        old_value={
            "status": old_status,
        },
        new_value={
            "status": appointment.status.value,
        },
    )

    return appointment


@transactional
def mark_no_show(
    appointment_id: int,
    clinic_id: int,
):
    """
    Mark a confirmed appointment as a no-show.

    The appointment must belong to clinic_id.
    """
    appointment = _get_appointment(
        appointment_id,
        clinic_id=clinic_id,
    )

    _ensure_status(
        appointment,
        AppointmentStatus.CONFIRMED,
    )

    old_status = appointment.status.value

    appointment.status = AppointmentStatus.NO_SHOW

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Appointment",
        entity_id=appointment.id,
        description="Appointment marked as no-show",
        old_value={
            "status": old_status,
        },
        new_value={
            "status": appointment.status.value,
        },
    )

    return appointment


# ---------------------------------------------------------------------
# Appointment queries
# ---------------------------------------------------------------------


def get_appointments_for_patient(
    clinic_id: int,
    patient_id: int,
):
    """
    Return all appointments belonging to a patient within the
    authenticated clinic.

    This prevents a user from retrieving another clinic's
    appointment history by supplying a patient ID.
    """
    patient = get_patient(patient_id)

    if patient.clinic_id != clinic_id:
        raise NotFoundError(
            f"Patient {patient_id} not found"
        )

    return (
        Appointment.query
        .filter(
            Appointment.clinic_id == clinic_id,
            Appointment.patient_id == patient_id,
        )
        .order_by(
            Appointment.scheduled_start.desc()
        )
        .all()
    )


def get_appointments_for_staff(
    clinic_id: int,
    staff_id: int,
    date_=None,
):
    """
    Return staff appointments within the authenticated clinic.

    If date_ is provided, only appointments on that date are
    returned.
    """
    staff = get_staff(staff_id)

    if staff.clinic_id != clinic_id:
        raise NotFoundError(
            f"Staff member {staff_id} not found"
        )

    query = Appointment.query.filter(
        Appointment.clinic_id == clinic_id,
        Appointment.staff_id == staff_id,
    )

    if date_ is not None:
        query = query.filter(
            db.func.date(
                Appointment.scheduled_start
            ) == date_
        )

    return (
        query
        .order_by(
            Appointment.scheduled_start.asc()
        )
        .all()
    )


# ---------------------------------------------------------------------
# Celery reminders
# ---------------------------------------------------------------------


@celery.task(name="send_appointment_reminder")
def send_appointment_reminder(
    appointment_id: int,
):
    """
    Send an appointment reminder.

    This is a background task and therefore does not use authenticated
    clinic context.

    Notification integration is intentionally left as a stub until
    the notifications module is implemented.
    """
    appointment = db.session.get(
        Appointment,
        appointment_id,
    )

    if appointment is None:
        return

    if appointment.reminder_sent:
        return

    # Notification integration will be added here later.
    #
    # Example:
    #
    # notify_patient(
    #     appointment.patient_id,
    #     "Reminder: your appointment is tomorrow",
    # )

    appointment.reminder_sent = True

    db.session.commit()


@celery.task(name="check_upcoming_appointments")
def check_upcoming_appointments():
    """
    Find appointments occurring approximately 24 hours from now
    and queue reminder tasks for them.

    This task can be scheduled periodically through Celery Beat.
    """
    now = _utcnow()

    tomorrow = now + timedelta(days=1)
    reminder_window_end = tomorrow + timedelta(hours=1)

    upcoming = (
        Appointment.query
        .filter(
            Appointment.scheduled_start.between(
                tomorrow,
                reminder_window_end,
            ),
            Appointment.reminder_sent.is_(False),
            Appointment.status.in_(
                [
                    AppointmentStatus.SCHEDULED,
                    AppointmentStatus.CONFIRMED,
                ]
            ),
        )
        .all()
    )

    for appointment in upcoming:
        send_appointment_reminder.delay(
            appointment.id
        )