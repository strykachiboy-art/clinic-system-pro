from flask import Blueprint, jsonify, request
from pydantic import ValidationError as PydanticValidationError

from app.core.enums.role_enums import Role
from app.core.utils.decorators import role_required

from app.modules.appointment.schemas.appointment_schema import (
    AppointmentCancelSchema,
    AppointmentCompleteSchema,
    AppointmentCreateSchema,
    AppointmentRescheduleSchema,
    AppointmentStaffScheduleQuerySchema,
)

from app.modules.appointment.services.appointment_service import (
    cancel_appointment,
    complete_appointment,
    confirm_appointment,
    create_appointment,
    get_appointments_for_patient,
    get_appointments_for_staff,
    mark_no_show,
    reschedule_appointment,
)


# ---------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------


appointment_bp = Blueprint(
    "appointment",
    __name__,
    url_prefix="/api/appointments",
)


# ---------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------
#
# Appointment management is currently restricted to clinical and
# administrative staff.
#
# Clinic activity validation is intentionally NOT performed here.
# The appointment service owns that business rule.
# ---------------------------------------------------------------------


APPOINTMENT_ROLES = (
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
    Role.RECEPTIONIST,
)


def _serialize_appointment(appointment):
    return {
        "id": appointment.id,
        "clinic_id": appointment.clinic_id,
        "patient_id": appointment.patient_id,
        "staff_id": appointment.staff_id,
        "scheduled_start": appointment.scheduled_start.isoformat(),
        "scheduled_end": appointment.scheduled_end.isoformat(),
        "status": appointment.status.value,
        "appointment_type": appointment.appointment_type.value,
        "reason": appointment.reason,
        "notes": appointment.notes,
        "google_calendar_event_id": appointment.google_calendar_event_id,
        "reminder_sent": appointment.reminder_sent,
        "created_at": appointment.created_at.isoformat() if appointment.created_at else None,
        "updated_at": appointment.updated_at.isoformat() if appointment.updated_at else None,
        "cancelled_at": appointment.cancelled_at.isoformat() if appointment.cancelled_at else None,
        "cancellation_reason": appointment.cancellation_reason,
    }


# ---------------------------------------------------------------------
# Request validation helpers
# ---------------------------------------------------------------------


def _payload(schema):
    """
    Validate a JSON request body using the supplied Pydantic schema.

    Returns:
        - validated Pydantic model on success
        - Flask response tuple on validation failure
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


def _query_payload(schema):
    """
    Validate query parameters using the supplied Pydantic schema.

    Flask's MultiDict is converted to a normal dictionary before
    Pydantic validation.
    """
    try:
        return schema.model_validate(
            request.args.to_dict()
        )

    except PydanticValidationError as exc:
        return jsonify({
            "success": False,
            "error": exc.errors(),
        }), 422


# ---------------------------------------------------------------------
# Create appointment
# ---------------------------------------------------------------------


@appointment_bp.post("/")
@role_required(*APPOINTMENT_ROLES)
def create():
    """
    Create a new appointment.

    The service validates:
        - clinic existence
        - clinic ACTIVE status
        - patient existence
        - staff existence
        - patient/clinic relationship
        - staff/clinic relationship
        - schedule conflicts
        - appointment times
    """
    payload = _payload(
        AppointmentCreateSchema
    )

    if isinstance(payload, tuple):
        return payload

    appointment = create_appointment(
        **payload.model_dump()
    )

    return jsonify({
        "success": True,
        "data": _serialize_appointment(appointment),
    }), 201


# ---------------------------------------------------------------------
# Reschedule appointment
# ---------------------------------------------------------------------


@appointment_bp.post(
    "/<int:appointment_id>/reschedule"
)
@role_required(*APPOINTMENT_ROLES)
def reschedule(appointment_id: int):
    """
    Reschedule an existing appointment.

    The service validates that:
        - the appointment exists
        - the appointment is SCHEDULED or CONFIRMED
        - the clinic is ACTIVE
        - the new schedule does not conflict
    """
    payload = _payload(
        AppointmentRescheduleSchema
    )

    if isinstance(payload, tuple):
        return payload

    appointment = reschedule_appointment(
        appointment_id=appointment_id,
        new_start=payload.scheduled_start,
        new_end=payload.scheduled_end,
    )

    return jsonify({
        "success": True,
        "data": _serialize_appointment(appointment),
    }), 200


# ---------------------------------------------------------------------
# Confirm appointment
# ---------------------------------------------------------------------


@appointment_bp.post(
    "/<int:appointment_id>/confirm"
)
@role_required(*APPOINTMENT_ROLES)
def confirm(appointment_id: int):
    """
    Confirm a scheduled appointment.

    Clinic activity validation is handled by the service.
    """
    appointment = confirm_appointment(
        appointment_id=appointment_id,
    )

    return jsonify({
        "success": True,
        "data": _serialize_appointment(appointment),
    }), 200


# ---------------------------------------------------------------------
# Cancel appointment
# ---------------------------------------------------------------------


@appointment_bp.post(
    "/<int:appointment_id>/cancel"
)
@role_required(*APPOINTMENT_ROLES)
def cancel(appointment_id: int):
    """
    Cancel a scheduled or confirmed appointment.
    """
    payload = _payload(
        AppointmentCancelSchema
    )

    if isinstance(payload, tuple):
        return payload

    appointment = cancel_appointment(
        appointment_id=appointment_id,
        reason=payload.cancellation_reason,
    )

    return jsonify({
        "success": True,
        "data": _serialize_appointment(appointment),
    }), 200


# ---------------------------------------------------------------------
# Complete appointment
# ---------------------------------------------------------------------


@appointment_bp.post(
    "/<int:appointment_id>/complete"
)
@role_required(*APPOINTMENT_ROLES)
def complete(appointment_id: int):
    """
    Mark a confirmed appointment as completed.
    """
    payload = _payload(
        AppointmentCompleteSchema
    )

    if isinstance(payload, tuple):
        return payload

    appointment = complete_appointment(
        appointment_id=appointment_id,
        notes=payload.notes,
    )

    return jsonify({
        "success": True,
        "data": _serialize_appointment(appointment),
    }), 200


# ---------------------------------------------------------------------
# Mark appointment as no-show
# ---------------------------------------------------------------------


@appointment_bp.post(
    "/<int:appointment_id>/no-show"
)
@role_required(*APPOINTMENT_ROLES)
def no_show(appointment_id: int):
    """
    Mark a confirmed appointment as a no-show.
    """
    appointment = mark_no_show(
        appointment_id=appointment_id,
    )

    return jsonify({
        "success": True,
        "data": _serialize_appointment(appointment),
    }), 200


# ---------------------------------------------------------------------
# Patient appointment history
# ---------------------------------------------------------------------


@appointment_bp.get(
    "/patient/<int:patient_id>"
)
@role_required(*APPOINTMENT_ROLES)
def patient_appointments(patient_id: int):
    """
    Retrieve all appointments for a patient.

    This endpoint intentionally works even when the patient's clinic
    is INACTIVE or SUSPENDED.

    Historical records must remain accessible.
    """
    appointments = get_appointments_for_patient(
        patient_id=patient_id,
    )

    return jsonify({
        "success": True,
        "data": [_serialize_appointment(item) for item in appointments],
    }), 200


# ---------------------------------------------------------------------
# Staff appointment schedule
# ---------------------------------------------------------------------


@appointment_bp.get(
    "/staff/<int:staff_id>"
)
@role_required(*APPOINTMENT_ROLES)
def staff_appointments(staff_id: int):
    """
    Retrieve appointments assigned to a staff member.

    An optional date query parameter may be supplied.

    Historical appointments remain retrievable regardless of clinic
    status.
    """
    payload = _query_payload(
        AppointmentStaffScheduleQuerySchema
    )

    if isinstance(payload, tuple):
        return payload

    appointments = get_appointments_for_staff(
        staff_id=staff_id,
        date_=payload.date_,
    )

    return jsonify({
        "success": True,
        "data": [_serialize_appointment(item) for item in appointments],
    }), 200