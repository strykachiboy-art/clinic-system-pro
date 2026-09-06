from flask import Blueprint, jsonify, request, g
from pydantic import ValidationError as PydanticValidationError

from app.core.auth.user.models.user_model import User
from app.core.enums.role_enums import Role
from app.core.exceptions import DomainError
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


# ============================================================================
# Blueprint
# ============================================================================


appointment_bp = Blueprint(
    "appointment",
    __name__,
    url_prefix="/api/appointments",
)


# ============================================================================
# Permissions
# ============================================================================


APPOINTMENT_ROLES = (
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
    Role.RECEPTIONIST,
)


# ============================================================================
# Authentication / Clinic Helpers
# ============================================================================


def _current_user() -> User:
    """
    Return the authenticated user.

    The authentication decorator populates g.current_user_id
    from the verified JWT.
    """

    user = db_user = User.query.get(
        g.current_user_id
    )

    if user is None:
        raise DomainError("Authenticated user not found")

    return user


def _current_clinic_id() -> int:
    """
    Return the authenticated user's clinic ID.

    Clinic ownership is derived server-side and is never
    accepted from the request payload.
    """

    user = _current_user()

    if user.clinic_id is None:
        raise DomainError(
            "Authenticated user is not assigned to a clinic"
        )

    return user.clinic_id


# ============================================================================
# Serialization
# ============================================================================


def _serialize_appointment(appointment):
    return {
        "id": appointment.id,
        "clinic_id": appointment.clinic_id,
        "patient_id": appointment.patient_id,
        "staff_id": appointment.staff_id,
        "scheduled_start": (
            appointment.scheduled_start.isoformat()
        ),
        "scheduled_end": (
            appointment.scheduled_end.isoformat()
        ),
        "status": appointment.status.value,
        "appointment_type": appointment.appointment_type.value,
        "reason": appointment.reason,
        "notes": appointment.notes,
        "google_calendar_event_id": (
            appointment.google_calendar_event_id
        ),
        "reminder_sent": appointment.reminder_sent,
        "created_at": (
            appointment.created_at.isoformat()
            if appointment.created_at
            else None
        ),
        "updated_at": (
            appointment.updated_at.isoformat()
            if appointment.updated_at
            else None
        ),
        "cancelled_at": (
            appointment.cancelled_at.isoformat()
            if appointment.cancelled_at
            else None
        ),
        "cancellation_reason": (
            appointment.cancellation_reason
        ),
    }


# ============================================================================
# Request Validation Helpers
# ============================================================================


def _payload(schema):
    """
    Validate a JSON request body using the supplied Pydantic schema.

    Returns:
        Pydantic model on success.
        Flask response tuple on validation failure.
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


# ============================================================================
# Create Appointment
# ============================================================================


@appointment_bp.post("/")
@role_required(*APPOINTMENT_ROLES)
def create():
    """
    Create a new appointment.

    Clinic ID is derived from the authenticated user.

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

    try:
        clinic_id = _current_clinic_id()

        appointment = create_appointment(
            clinic_id=clinic_id,
            patient_id=payload.patient_id,
            staff_id=payload.staff_id,
            scheduled_start=payload.scheduled_start,
            scheduled_end=payload.scheduled_end,
            appointment_type=payload.appointment_type,
            reason=payload.reason,
        )

        return jsonify({
            "success": True,
            "data": _serialize_appointment(
                appointment
            ),
        }), 201

    except DomainError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), exc.status_code


# ============================================================================
# Reschedule Appointment
# ============================================================================


@appointment_bp.post(
    "/<int:appointment_id>/reschedule"
)
@role_required(*APPOINTMENT_ROLES)
def reschedule(appointment_id: int):
    """
    Reschedule an existing appointment.

    The service validates:
        - appointment existence
        - clinic ownership
        - valid appointment status
        - clinic ACTIVE status
        - new schedule
        - schedule conflicts
    """

    payload = _payload(
        AppointmentRescheduleSchema
    )

    if isinstance(payload, tuple):
        return payload

    try:
        clinic_id = _current_clinic_id()

        appointment = reschedule_appointment(
            appointment_id=appointment_id,
            clinic_id=clinic_id,
            new_start=payload.scheduled_start,
            new_end=payload.scheduled_end,
        )

        return jsonify({
            "success": True,
            "data": _serialize_appointment(
                appointment
            ),
        }), 200

    except DomainError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), exc.status_code


# ============================================================================
# Confirm Appointment
# ============================================================================


@appointment_bp.post(
    "/<int:appointment_id>/confirm"
)
@role_required(*APPOINTMENT_ROLES)
def confirm(appointment_id: int):
    """
    Confirm a scheduled appointment.
    """

    try:
        clinic_id = _current_clinic_id()

        appointment = confirm_appointment(
            appointment_id=appointment_id,
            clinic_id=clinic_id,
        )

        return jsonify({
            "success": True,
            "data": _serialize_appointment(
                appointment
            ),
        }), 200

    except DomainError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), exc.status_code


# ============================================================================
# Cancel Appointment
# ============================================================================


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

    try:
        clinic_id = _current_clinic_id()

        appointment = cancel_appointment(
            appointment_id=appointment_id,
            clinic_id=clinic_id,
            reason=payload.cancellation_reason,
        )

        return jsonify({
            "success": True,
            "data": _serialize_appointment(
                appointment
            ),
        }), 200

    except DomainError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), exc.status_code


# ============================================================================
# Complete Appointment
# ============================================================================


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

    try:
        clinic_id = _current_clinic_id()

        appointment = complete_appointment(
            appointment_id=appointment_id,
            clinic_id=clinic_id,
            notes=payload.notes,
        )

        return jsonify({
            "success": True,
            "data": _serialize_appointment(
                appointment
            ),
        }), 200

    except DomainError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), exc.status_code


# ============================================================================
# Mark Appointment as No-Show
# ============================================================================


@appointment_bp.post(
    "/<int:appointment_id>/no-show"
)
@role_required(*APPOINTMENT_ROLES)
def no_show(appointment_id: int):
    """
    Mark a confirmed appointment as a no-show.
    """

    try:
        clinic_id = _current_clinic_id()

        appointment = mark_no_show(
            appointment_id=appointment_id,
            clinic_id=clinic_id,
        )

        return jsonify({
            "success": True,
            "data": _serialize_appointment(
                appointment
            ),
        }), 200

    except DomainError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), exc.status_code


# ============================================================================
# Patient Appointment History
# ============================================================================


@appointment_bp.get(
    "/patient/<int:patient_id>"
)
@role_required(*APPOINTMENT_ROLES)
def patient_appointments(patient_id: int):
    """
    Retrieve all appointments for a patient.

    Historical appointments remain accessible even if
    the clinic is inactive or suspended.

    Results are always restricted to the authenticated
    user's clinic.
    """

    try:
        clinic_id = _current_clinic_id()

        appointments = get_appointments_for_patient(
            patient_id=patient_id,
            clinic_id=clinic_id,
        )

        return jsonify({
            "success": True,
            "data": [
                _serialize_appointment(item)
                for item in appointments
            ],
        }), 200

    except DomainError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), exc.status_code


# ============================================================================
# Staff Appointment Schedule
# ============================================================================


@appointment_bp.get(
    "/staff/<int:staff_id>"
)
@role_required(*APPOINTMENT_ROLES)
def staff_appointments(staff_id: int):
    """
    Retrieve appointments assigned to a staff member.

    An optional date query parameter may be supplied.

    Historical appointments remain retrievable regardless
    of clinic status.

    Results are always restricted to the authenticated
    user's clinic.
    """

    payload = _query_payload(
        AppointmentStaffScheduleQuerySchema
    )

    if isinstance(payload, tuple):
        return payload

    try:
        clinic_id = _current_clinic_id()

        appointments = get_appointments_for_staff(
            staff_id=staff_id,
            clinic_id=clinic_id,
            date_=payload.date_,
        )

        return jsonify({
            "success": True,
            "data": [
                _serialize_appointment(item)
                for item in appointments
            ],
        }), 200

    except DomainError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), exc.status_code