from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.enums.appointment_enums import (
    AppointmentStatus,
    AppointmentType,
)
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.appointment.models.appointment_model import Appointment
from app.modules.appointment.services import appointment_service


def utcnow():
    return datetime.now(timezone.utc)


def db_datetime(dt):
    """
    SQLite returns DateTime values without timezone information.

    Normalize an aware datetime to the naive value returned by SQLite.
    """
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def create_test_appointment(
    db,
    clinic,
    patient,
    staff,
    *,
    start=None,
    end=None,
    status=AppointmentStatus.SCHEDULED,
    appointment_type=AppointmentType.IN_PERSON,
    reason="Routine consultation",
    notes=None,
    reminder_sent=False,
):
    start = start or (utcnow() + timedelta(days=1))
    end = end or (start + timedelta(minutes=30))

    appointment = Appointment(
        clinic_id=clinic.id,
        patient_id=patient.id,
        staff_id=staff.id,
        scheduled_start=start,
        scheduled_end=end,
        status=status,
        appointment_type=appointment_type,
        reason=reason,
        notes=notes,
        reminder_sent=reminder_sent,
    )

    db.session.add(appointment)
    db.session.commit()

    return appointment


# ---------------------------------------------------------------------------
# _get_appointment
# ---------------------------------------------------------------------------


def test_get_appointment_returns_existing_appointment(
    db,
    clinic,
    patient,
    staff,
):
    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
    )

    result = appointment_service._get_appointment(appointment.id)

    assert result.id == appointment.id
    assert result.clinic_id == clinic.id
    assert result.patient_id == patient.id
    assert result.staff_id == staff.id


def test_get_appointment_raises_not_found(
    db,
    clinic,
):
    with pytest.raises(
        NotFoundError,
        match=r"Appointment 999999 not found",
    ):
        appointment_service._get_appointment(999999)


# ---------------------------------------------------------------------------
# Schedule validation
# ---------------------------------------------------------------------------


def test_validate_schedule_times_requires_start_and_end():
    with pytest.raises(
        ValidationError,
        match="scheduled_start and scheduled_end are required",
    ):
        appointment_service._validate_schedule_times(None, None)


def test_validate_schedule_times_requires_end_after_start():
    start = utcnow()
    end = start

    with pytest.raises(
        ValidationError,
        match="scheduled_end must be later than scheduled_start",
    ):
        appointment_service._validate_schedule_times(start, end)


def test_validate_schedule_times_rejects_end_before_start():
    start = utcnow()
    end = start - timedelta(minutes=30)

    with pytest.raises(
        ValidationError,
        match="scheduled_end must be later than scheduled_start",
    ):
        appointment_service._validate_schedule_times(start, end)


def test_validate_schedule_times_accepts_valid_range():
    start = utcnow()
    end = start + timedelta(minutes=30)

    appointment_service._validate_schedule_times(start, end)


# ---------------------------------------------------------------------------
# Reschedule validation
# ---------------------------------------------------------------------------


def test_validate_reschedule_times_requires_start_and_end():
    with pytest.raises(
        ValidationError,
        match="new_start and new_end are required",
    ):
        appointment_service._validate_reschedule_times(None, None)


def test_validate_reschedule_times_requires_end_after_start():
    start = utcnow()
    end = start

    with pytest.raises(
        ValidationError,
        match="new_end must be later than new_start",
    ):
        appointment_service._validate_reschedule_times(start, end)


def test_validate_reschedule_times_rejects_end_before_start():
    start = utcnow()
    end = start - timedelta(minutes=30)

    with pytest.raises(
        ValidationError,
        match="new_end must be later than new_start",
    ):
        appointment_service._validate_reschedule_times(start, end)


def test_validate_reschedule_times_accepts_valid_range():
    start = utcnow()
    end = start + timedelta(minutes=30)

    appointment_service._validate_reschedule_times(start, end)


# ---------------------------------------------------------------------------
# Create appointment
# ---------------------------------------------------------------------------


def test_create_appointment_creates_scheduled_appointment(
    db,
    clinic,
    patient,
    staff,
):
    start = utcnow() + timedelta(days=2)
    end = start + timedelta(minutes=45)

    appointment = appointment_service.create_appointment(
        clinic_id=clinic.id,
        patient_id=patient.id,
        staff_id=staff.id,
        scheduled_start=start,
        scheduled_end=end,
        appointment_type=AppointmentType.IN_PERSON,
        reason="General consultation",
        notes="Initial assessment",
    )

    assert appointment.id is not None
    assert appointment.clinic_id == clinic.id
    assert appointment.patient_id == patient.id
    assert appointment.staff_id == staff.id

    # SQLite strips tzinfo from DateTime columns.
    assert appointment.scheduled_start == db_datetime(start)
    assert appointment.scheduled_end == db_datetime(end)

    assert appointment.status == AppointmentStatus.SCHEDULED
    assert appointment.appointment_type == AppointmentType.IN_PERSON
    assert appointment.reason == "General consultation"
    assert appointment.notes == "Initial assessment"
    assert appointment.reminder_sent is False


def test_create_appointment_defaults_to_in_person(
    db,
    clinic,
    patient,
    staff,
):
    start = utcnow() + timedelta(days=2)
    end = start + timedelta(minutes=30)

    appointment = appointment_service.create_appointment(
        clinic_id=clinic.id,
        patient_id=patient.id,
        staff_id=staff.id,
        scheduled_start=start,
        scheduled_end=end,
    )

    assert appointment.appointment_type == AppointmentType.IN_PERSON
    assert appointment.status == AppointmentStatus.SCHEDULED


def test_create_appointment_rejects_missing_schedule(
    clinic,
    patient,
    staff,
):
    with pytest.raises(
        ValidationError,
        match="scheduled_start and scheduled_end are required",
    ):
        appointment_service.create_appointment(
            clinic_id=clinic.id,
            patient_id=patient.id,
            staff_id=staff.id,
            scheduled_start=None,
            scheduled_end=None,
        )


def test_create_appointment_rejects_invalid_schedule(
    clinic,
    patient,
    staff,
):
    start = utcnow() + timedelta(days=2)
    end = start - timedelta(minutes=1)

    with pytest.raises(
        ValidationError,
        match="scheduled_end must be later than scheduled_start",
    ):
        appointment_service.create_appointment(
            clinic_id=clinic.id,
            patient_id=patient.id,
            staff_id=staff.id,
            scheduled_start=start,
            scheduled_end=end,
        )


def test_create_appointment_rejects_patient_from_different_clinic(
    db,
    clinic,
    patient,
    staff,
    make_clinic,
    make_patient,
):
    other_clinic = make_clinic(name="Other Clinic")
    other_patient = make_patient(other_clinic)

    start = utcnow() + timedelta(days=2)
    end = start + timedelta(minutes=30)

    with pytest.raises(
        ConflictError,
        match=rf"Patient {other_patient.id} does not belong to clinic {clinic.id}",
    ):
        appointment_service.create_appointment(
            clinic_id=clinic.id,
            patient_id=other_patient.id,
            staff_id=staff.id,
            scheduled_start=start,
            scheduled_end=end,
        )


def test_create_appointment_rejects_staff_from_different_clinic(
    db,
    clinic,
    patient,
    make_clinic,
    make_staff,
):
    other_clinic = make_clinic(name="Other Clinic")
    other_staff = make_staff(other_clinic)

    start = utcnow() + timedelta(days=2)
    end = start + timedelta(minutes=30)

    with pytest.raises(
        ConflictError,
        match=rf"Staff {other_staff.id} does not belong to clinic {clinic.id}",
    ):
        appointment_service.create_appointment(
            clinic_id=clinic.id,
            patient_id=patient.id,
            staff_id=other_staff.id,
            scheduled_start=start,
            scheduled_end=end,
        )


def test_create_appointment_rejects_suspended_clinic(
    suspended_clinic,
    make_patient,
    make_staff,
):
    patient = make_patient(suspended_clinic)
    staff = make_staff(suspended_clinic)

    start = utcnow() + timedelta(days=2)
    end = start + timedelta(minutes=30)

    with pytest.raises(
        ValidationError,
        match=rf"Clinic {suspended_clinic.id} is not active",
    ):
        appointment_service.create_appointment(
            clinic_id=suspended_clinic.id,
            patient_id=patient.id,
            staff_id=staff.id,
            scheduled_start=start,
            scheduled_end=end,
        )


# ---------------------------------------------------------------------------
# Appointment overlap
# ---------------------------------------------------------------------------


def test_create_appointment_rejects_patient_overlap(
    db,
    clinic,
    patient,
    staff,
):
    start = utcnow() + timedelta(days=3)
    end = start + timedelta(hours=1)

    existing = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        start=start,
        end=end,
    )

    with pytest.raises(
        ConflictError,
        match=rf"Patient {patient.id} already has an appointment overlapping this time period \(appointment {existing.id}\)",
    ):
        appointment_service.create_appointment(
            clinic_id=clinic.id,
            patient_id=patient.id,
            staff_id=staff.id,
            scheduled_start=start + timedelta(minutes=30),
            scheduled_end=end + timedelta(minutes=30),
        )


def test_create_appointment_rejects_staff_overlap(
    db,
    clinic,
    patient,
    staff,
    make_patient,
):
    existing_patient = patient

    start = utcnow() + timedelta(days=3)
    end = start + timedelta(hours=1)

    existing = create_test_appointment(
        db,
        clinic,
        existing_patient,
        staff,
        start=start,
        end=end,
    )

    other_patient = make_patient(clinic)

    with pytest.raises(
        ConflictError,
        match=rf"Staff {staff.id} already has an appointment overlapping this time period \(appointment {existing.id}\)",
    ):
        appointment_service.create_appointment(
            clinic_id=clinic.id,
            patient_id=other_patient.id,
            staff_id=staff.id,
            scheduled_start=start + timedelta(minutes=30),
            scheduled_end=end + timedelta(minutes=30),
        )


def test_create_appointment_allows_adjacent_patient_appointments(
    db,
    clinic,
    patient,
    staff,
):
    start = utcnow() + timedelta(days=3)
    end = start + timedelta(minutes=30)

    create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        start=start,
        end=end,
    )

    next_start = end
    next_end = next_start + timedelta(minutes=30)

    appointment = appointment_service.create_appointment(
        clinic_id=clinic.id,
        patient_id=patient.id,
        staff_id=staff.id,
        scheduled_start=next_start,
        scheduled_end=next_end,
    )

    assert appointment.id is not None


def test_create_appointment_allows_cancelled_appointment_overlap(
    db,
    clinic,
    patient,
    staff,
):
    start = utcnow() + timedelta(days=3)
    end = start + timedelta(minutes=30)

    create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        start=start,
        end=end,
        status=AppointmentStatus.CANCELLED,
    )

    appointment = appointment_service.create_appointment(
        clinic_id=clinic.id,
        patient_id=patient.id,
        staff_id=staff.id,
        scheduled_start=start,
        scheduled_end=end,
    )

    assert appointment.id is not None


def test_create_appointment_allows_completed_appointment_overlap(
    db,
    clinic,
    patient,
    staff,
):
    start = utcnow() + timedelta(days=3)
    end = start + timedelta(minutes=30)

    create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        start=start,
        end=end,
        status=AppointmentStatus.COMPLETED,
    )

    appointment = appointment_service.create_appointment(
        clinic_id=clinic.id,
        patient_id=patient.id,
        staff_id=staff.id,
        scheduled_start=start,
        scheduled_end=end,
    )

    assert appointment.id is not None


# ---------------------------------------------------------------------------
# Reschedule
# ---------------------------------------------------------------------------


def test_reschedule_appointment_updates_schedule(
    db,
    clinic,
    patient,
    staff,
):
    original_start = utcnow() + timedelta(days=3)
    original_end = original_start + timedelta(minutes=30)

    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        start=original_start,
        end=original_end,
    )

    new_start = original_start + timedelta(hours=2)
    new_end = new_start + timedelta(minutes=45)

    result = appointment_service.reschedule_appointment(
        appointment.id,
        new_start,
        new_end,
    )

    assert result.id == appointment.id
    assert result.scheduled_start == db_datetime(new_start)
    assert result.scheduled_end == db_datetime(new_end)
    assert result.reminder_sent is False


def test_reschedule_allows_same_appointment_without_self_conflict(
    db,
    clinic,
    patient,
    staff,
):
    start = utcnow() + timedelta(days=3)
    end = start + timedelta(minutes=30)

    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        start=start,
        end=end,
    )

    result = appointment_service.reschedule_appointment(
        appointment.id,
        start + timedelta(minutes=5),
        end + timedelta(minutes=5),
    )

    assert result.id == appointment.id
    assert result.scheduled_start == db_datetime(
        start + timedelta(minutes=5)
    )
    assert result.scheduled_end == db_datetime(
        end + timedelta(minutes=5)
    )


def test_reschedule_rejects_patient_overlap(
    db,
    clinic,
    patient,
    staff,
    make_patient,
):
    first_start = utcnow() + timedelta(days=3)
    first_end = first_start + timedelta(minutes=30)

    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        start=first_start,
        end=first_end,
    )

    other_patient = make_patient(clinic)

    blocking_start = first_start + timedelta(hours=2)
    blocking_end = blocking_start + timedelta(minutes=30)

    create_test_appointment(
        db,
        clinic,
        other_patient,
        staff,
        start=blocking_start,
        end=blocking_end,
    )

    with pytest.raises(ConflictError):
        appointment_service.reschedule_appointment(
            appointment.id,
            blocking_start,
            blocking_end,
        )


def test_reschedule_rejects_invalid_times(
    db,
    clinic,
    patient,
    staff,
):
    start = utcnow() + timedelta(days=3)
    end = start + timedelta(minutes=30)

    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        start=start,
        end=end,
    )

    with pytest.raises(
        ValidationError,
        match="new_end must be later than new_start",
    ):
        appointment_service.reschedule_appointment(
            appointment.id,
            end,
            start,
        )


def test_reschedule_rejects_cancelled_appointment(
    db,
    clinic,
    patient,
    staff,
):
    start = utcnow() + timedelta(days=3)
    end = start + timedelta(minutes=30)

    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        start=start,
        end=end,
        status=AppointmentStatus.CANCELLED,
    )

    with pytest.raises(ConflictError):
        appointment_service.reschedule_appointment(
            appointment.id,
            start + timedelta(hours=1),
            end + timedelta(hours=1),
        )


# ---------------------------------------------------------------------------
# Confirm
# ---------------------------------------------------------------------------


def test_confirm_appointment_changes_status_to_confirmed(
    db,
    clinic,
    patient,
    staff,
):
    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        status=AppointmentStatus.SCHEDULED,
    )

    result = appointment_service.confirm_appointment(appointment.id)

    assert result.status == AppointmentStatus.CONFIRMED


def test_confirm_appointment_rejects_non_scheduled_appointment(
    db,
    clinic,
    patient,
    staff,
):
    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        status=AppointmentStatus.CONFIRMED,
    )

    with pytest.raises(ConflictError):
        appointment_service.confirm_appointment(appointment.id)


def test_confirm_appointment_rejects_cancelled_appointment(
    db,
    clinic,
    patient,
    staff,
):
    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        status=AppointmentStatus.CANCELLED,
    )

    with pytest.raises(ConflictError):
        appointment_service.confirm_appointment(appointment.id)


def test_confirm_appointment_rejects_suspended_clinic(
    db,
    suspended_clinic,
    make_patient,
    make_staff,
):
    patient = make_patient(suspended_clinic)
    staff = make_staff(suspended_clinic)

    appointment = create_test_appointment(
        db,
        suspended_clinic,
        patient,
        staff,
        status=AppointmentStatus.SCHEDULED,
    )

    with pytest.raises(
        ValidationError,
        match=rf"Clinic {suspended_clinic.id} is not active",
    ):
        appointment_service.confirm_appointment(appointment.id)


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


def test_cancel_appointment_changes_status_and_records_reason(
    db,
    clinic,
    patient,
    staff,
):
    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        status=AppointmentStatus.SCHEDULED,
    )

    result = appointment_service.cancel_appointment(
        appointment.id,
        reason="Patient requested cancellation",
    )

    assert result.status == AppointmentStatus.CANCELLED
    assert result.cancellation_reason == "Patient requested cancellation"
    assert result.cancelled_at is not None


def test_cancel_confirmed_appointment(
    db,
    clinic,
    patient,
    staff,
):
    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        status=AppointmentStatus.CONFIRMED,
    )

    result = appointment_service.cancel_appointment(
        appointment.id,
        reason="Schedule conflict",
    )

    assert result.status == AppointmentStatus.CANCELLED
    assert result.cancellation_reason == "Schedule conflict"
    assert result.cancelled_at is not None


def test_cancel_appointment_allows_no_reason(
    db,
    clinic,
    patient,
    staff,
):
    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
    )

    result = appointment_service.cancel_appointment(appointment.id)

    assert result.status == AppointmentStatus.CANCELLED
    assert result.cancellation_reason is None
    assert result.cancelled_at is not None


def test_cancel_appointment_rejects_completed_appointment(
    db,
    clinic,
    patient,
    staff,
):
    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        status=AppointmentStatus.COMPLETED,
    )

    with pytest.raises(ConflictError):
        appointment_service.cancel_appointment(appointment.id)


def test_cancel_appointment_rejects_no_show_appointment(
    db,
    clinic,
    patient,
    staff,
):
    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        status=AppointmentStatus.NO_SHOW,
    )

    with pytest.raises(ConflictError):
        appointment_service.cancel_appointment(appointment.id)


# ---------------------------------------------------------------------------
# Complete
# ---------------------------------------------------------------------------


def test_complete_appointment_changes_status_to_completed(
    db,
    clinic,
    patient,
    staff,
):
    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        status=AppointmentStatus.CONFIRMED,
    )

    result = appointment_service.complete_appointment(
        appointment.id,
        notes="Consultation completed successfully.",
    )

    assert result.status == AppointmentStatus.COMPLETED
    assert result.notes == "Consultation completed successfully."


def test_complete_appointment_keeps_existing_notes_when_none_provided(
    db,
    clinic,
    patient,
    staff,
):
    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        status=AppointmentStatus.CONFIRMED,
        notes="Existing notes",
    )

    result = appointment_service.complete_appointment(
        appointment.id,
        notes=None,
    )

    assert result.status == AppointmentStatus.COMPLETED
    assert result.notes == "Existing notes"


def test_complete_appointment_rejects_scheduled_appointment(
    db,
    clinic,
    patient,
    staff,
):
    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        status=AppointmentStatus.SCHEDULED,
    )

    with pytest.raises(ConflictError):
        appointment_service.complete_appointment(appointment.id)


def test_complete_appointment_rejects_cancelled_appointment(
    db,
    clinic,
    patient,
    staff,
):
    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        status=AppointmentStatus.CANCELLED,
    )

    with pytest.raises(ConflictError):
        appointment_service.complete_appointment(appointment.id)


# ---------------------------------------------------------------------------
# No-show
# ---------------------------------------------------------------------------


def test_mark_no_show_changes_status(
    db,
    clinic,
    patient,
    staff,
):
    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        status=AppointmentStatus.CONFIRMED,
    )

    result = appointment_service.mark_no_show(appointment.id)

    assert result.status == AppointmentStatus.NO_SHOW


def test_mark_no_show_rejects_scheduled_appointment(
    db,
    clinic,
    patient,
    staff,
):
    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        status=AppointmentStatus.SCHEDULED,
    )

    with pytest.raises(ConflictError):
        appointment_service.mark_no_show(appointment.id)


def test_mark_no_show_rejects_cancelled_appointment(
    db,
    clinic,
    patient,
    staff,
):
    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        status=AppointmentStatus.CANCELLED,
    )

    with pytest.raises(ConflictError):
        appointment_service.mark_no_show(appointment.id)


# ---------------------------------------------------------------------------
# Patient appointment queries
# ---------------------------------------------------------------------------


def test_get_appointments_for_patient_returns_patient_appointments(
    db,
    clinic,
    patient,
    staff,
):
    first_start = utcnow() + timedelta(days=2)
    second_start = utcnow() + timedelta(days=4)

    first = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        start=first_start,
        end=first_start + timedelta(minutes=30),
    )

    second = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        start=second_start,
        end=second_start + timedelta(minutes=30),
    )

    result = appointment_service.get_appointments_for_patient(patient.id)

    assert [appointment.id for appointment in result] == [
        second.id,
        first.id,
    ]


def test_get_appointments_for_patient_returns_empty_list_when_none_exist(
    patient,
):
    result = appointment_service.get_appointments_for_patient(patient.id)

    assert result == []


def test_get_appointments_for_patient_includes_historical_appointments(
    db,
    clinic,
    patient,
    staff,
):
    old_start = utcnow() - timedelta(days=10)
    old_end = old_start + timedelta(minutes=30)

    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        start=old_start,
        end=old_end,
        status=AppointmentStatus.COMPLETED,
    )

    result = appointment_service.get_appointments_for_patient(patient.id)

    assert len(result) == 1
    assert result[0].id == appointment.id


# ---------------------------------------------------------------------------
# Staff appointment queries
# ---------------------------------------------------------------------------


def test_get_appointments_for_staff_returns_staff_appointments(
    db,
    clinic,
    patient,
    staff,
    make_patient,
):
    first_start = utcnow() + timedelta(days=2)
    second_start = utcnow() + timedelta(days=2, hours=2)

    first = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        start=first_start,
        end=first_start + timedelta(minutes=30),
    )

    second_patient = make_patient(clinic)

    second = create_test_appointment(
        db,
        clinic,
        second_patient,
        staff,
        start=second_start,
        end=second_start + timedelta(minutes=30),
    )

    result = appointment_service.get_appointments_for_staff(staff.id)

    assert [appointment.id for appointment in result] == [
        first.id,
        second.id,
    ]


def test_get_appointments_for_staff_filters_by_date(
    db,
    clinic,
    patient,
    staff,
):
    first_start = utcnow() + timedelta(days=2)
    second_start = utcnow() + timedelta(days=3)

    first = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        start=first_start,
        end=first_start + timedelta(minutes=30),
    )

    second = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        start=second_start,
        end=second_start + timedelta(minutes=30),
    )

    result = appointment_service.get_appointments_for_staff(
        staff.id,
        date_=first_start.date(),
    )

    assert [appointment.id for appointment in result] == [first.id]
    assert second.id not in [appointment.id for appointment in result]


def test_get_appointments_for_staff_returns_empty_for_date_without_appointments(
    staff,
):
    result = appointment_service.get_appointments_for_staff(
        staff.id,
        date_=date(2099, 1, 1),
    )

    assert result == []


def test_get_appointments_for_staff_includes_historical_appointments(
    db,
    clinic,
    patient,
    staff,
):
    old_start = utcnow() - timedelta(days=10)
    old_end = old_start + timedelta(minutes=30)

    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        start=old_start,
        end=old_end,
        status=AppointmentStatus.COMPLETED,
    )

    result = appointment_service.get_appointments_for_staff(
        staff.id,
        date_=old_start.date(),
    )

    assert len(result) == 1
    assert result[0].id == appointment.id


# ---------------------------------------------------------------------------
# Reminder task
# ---------------------------------------------------------------------------


def test_send_appointment_reminder_marks_reminder_sent(
    db,
    clinic,
    patient,
    staff,
):
    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        reminder_sent=False,
    )

    result = appointment_service.send_appointment_reminder(
        appointment.id
    )

    db.session.refresh(appointment)

    assert result is None
    assert appointment.reminder_sent is True


def test_send_appointment_reminder_does_nothing_if_already_sent(
    db,
    clinic,
    patient,
    staff,
):
    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        reminder_sent=True,
    )

    result = appointment_service.send_appointment_reminder(
        appointment.id
    )

    db.session.refresh(appointment)

    assert result is None
    assert appointment.reminder_sent is True


def test_send_appointment_reminder_returns_none_for_missing_appointment():
    result = appointment_service.send_appointment_reminder(999999)

    assert result is None


# ---------------------------------------------------------------------------
# Upcoming appointment reminders
# ---------------------------------------------------------------------------


def test_check_upcoming_appointments_sends_reminders(
    db,
    clinic,
    patient,
    staff,
    monkeypatch,
):
    now = appointment_service._utcnow()

    upcoming_start = now + timedelta(days=1, minutes=30)
    upcoming_end = upcoming_start + timedelta(minutes=30)

    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        start=upcoming_start,
        end=upcoming_end,
        status=AppointmentStatus.SCHEDULED,
        reminder_sent=False,
    )

    calls = []

    def fake_delay(appointment_id):
        calls.append(appointment_id)

    monkeypatch.setattr(
        appointment_service.send_appointment_reminder,
        "delay",
        fake_delay,
    )

    result = appointment_service.check_upcoming_appointments()

    assert result == 1
    assert calls == [appointment.id]


def test_check_upcoming_appointments_includes_confirmed_appointments(
    db,
    clinic,
    patient,
    staff,
    monkeypatch,
):
    now = appointment_service._utcnow()

    upcoming_start = now + timedelta(days=1, minutes=30)
    upcoming_end = upcoming_start + timedelta(minutes=30)

    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        start=upcoming_start,
        end=upcoming_end,
        status=AppointmentStatus.CONFIRMED,
        reminder_sent=False,
    )

    calls = []

    def fake_delay(appointment_id):
        calls.append(appointment_id)

    monkeypatch.setattr(
        appointment_service.send_appointment_reminder,
        "delay",
        fake_delay,
    )

    result = appointment_service.check_upcoming_appointments()

    assert result == 1
    assert calls == [appointment.id]


def test_check_upcoming_appointments_ignores_already_sent_reminders(
    db,
    clinic,
    patient,
    staff,
    monkeypatch,
):
    now = appointment_service._utcnow()

    upcoming_start = now + timedelta(days=1, minutes=30)
    upcoming_end = upcoming_start + timedelta(minutes=30)

    appointment = create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        start=upcoming_start,
        end=upcoming_end,
        status=AppointmentStatus.SCHEDULED,
        reminder_sent=True,
    )

    calls = []

    def fake_delay(appointment_id):
        calls.append(appointment_id)

    monkeypatch.setattr(
        appointment_service.send_appointment_reminder,
        "delay",
        fake_delay,
    )

    result = appointment_service.check_upcoming_appointments()

    assert result == 0
    assert calls == []


def test_check_upcoming_appointments_ignores_cancelled_appointments(
    db,
    clinic,
    patient,
    staff,
    monkeypatch,
):
    now = appointment_service._utcnow()

    upcoming_start = now + timedelta(days=1, minutes=30)
    upcoming_end = upcoming_start + timedelta(minutes=30)

    create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        start=upcoming_start,
        end=upcoming_end,
        status=AppointmentStatus.CANCELLED,
        reminder_sent=False,
    )

    calls = []

    def fake_delay(appointment_id):
        calls.append(appointment_id)

    monkeypatch.setattr(
        appointment_service.send_appointment_reminder,
        "delay",
        fake_delay,
    )

    result = appointment_service.check_upcoming_appointments()

    assert result == 0
    assert calls == []


def test_check_upcoming_appointments_ignores_completed_appointments(
    db,
    clinic,
    patient,
    staff,
    monkeypatch,
):
    now = appointment_service._utcnow()

    upcoming_start = now + timedelta(days=1, minutes=30)
    upcoming_end = upcoming_start + timedelta(minutes=30)

    create_test_appointment(
        db,
        clinic,
        patient,
        staff,
        start=upcoming_start,
        end=upcoming_end,
        status=AppointmentStatus.COMPLETED,
        reminder_sent=False,
    )

    calls = []

    def fake_delay(appointment_id):
        calls.append(appointment_id)

    monkeypatch.setattr(
        appointment_service.send_appointment_reminder,
        "delay",
        fake_delay,
    )

    result = appointment_service.check_upcoming_appointments()

    assert result == 0
    assert calls == []


def test_check_upcoming_appointments_returns_zero_when_none_are_upcoming(
    db,
    clinic,
    patient,
    staff,
    monkeypatch,
):
    calls = []

    def fake_delay(appointment_id):
        calls.append(appointment_id)

    monkeypatch.setattr(
        appointment_service.send_appointment_reminder,
        "delay",
        fake_delay,
    )

    result = appointment_service.check_upcoming_appointments()

    assert result == 0
    assert calls == []