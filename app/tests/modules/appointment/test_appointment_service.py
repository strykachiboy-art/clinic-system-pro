from datetime import date, datetime, timedelta

import pytest

from app.core.enums.appointment_enums import (
    AppointmentStatus,
    AppointmentType,
)

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

from app.modules.appointment.services import (
    appointment_service,
)


# ============================================================================
# Helpers
# ============================================================================


def make_appointment(
    appointment_id=1,
    clinic_id=10,
    patient_id=20,
    staff_id=30,
    scheduled_start=None,
    scheduled_end=None,
    status=AppointmentStatus.SCHEDULED,
    appointment_type=AppointmentType.IN_PERSON,
    reason="Routine consultation",
    notes=None,
    reminder_sent=False,
    cancelled_at=None,
    cancellation_reason=None,
):
    class Appointment:
        pass

    appointment = Appointment()

    appointment.id = appointment_id
    appointment.clinic_id = clinic_id
    appointment.patient_id = patient_id
    appointment.staff_id = staff_id

    appointment.scheduled_start = (
        scheduled_start
        or datetime(
            2026,
            9,
            8,
            10,
            0,
        )
    )

    appointment.scheduled_end = (
        scheduled_end
        or datetime(
            2026,
            9,
            8,
            10,
            30,
        )
    )

    appointment.status = status
    appointment.appointment_type = appointment_type
    appointment.reason = reason
    appointment.notes = notes
    appointment.reminder_sent = reminder_sent
    appointment.cancelled_at = cancelled_at
    appointment.cancellation_reason = (
        cancellation_reason
    )

    return appointment


# ============================================================================
# _utcnow
# ============================================================================


def test_utcnow_returns_timezone_aware_utc_datetime():
    result = appointment_service._utcnow()

    assert isinstance(result, datetime)
    assert result.tzinfo is not None
    assert result.utcoffset() == timedelta(0)


# ============================================================================
# _validate_schedule_times
# ============================================================================


def test_validate_schedule_times_accepts_valid_times():
    start = datetime(
        2026,
        9,
        8,
        10,
        0,
    )

    end = datetime(
        2026,
        9,
        8,
        10,
        30,
    )

    result = appointment_service._validate_schedule_times(
        start,
        end,
    )

    assert result is None


@pytest.mark.parametrize(
    "scheduled_start,scheduled_end",
    [
        (None, datetime(2026, 9, 8, 10, 30)),
        (datetime(2026, 9, 8, 10, 0), None),
        (None, None),
    ],
)
def test_validate_schedule_times_requires_both_values(
    scheduled_start,
    scheduled_end,
):
    with pytest.raises(
        ValidationError,
        match="scheduled_start and scheduled_end are required",
    ):
        appointment_service._validate_schedule_times(
            scheduled_start,
            scheduled_end,
        )


def test_validate_schedule_times_rejects_equal_times():
    start = datetime(
        2026,
        9,
        8,
        10,
        0,
    )

    with pytest.raises(
        ValidationError,
        match="scheduled_end must be later than scheduled_start",
    ):
        appointment_service._validate_schedule_times(
            start,
            start,
        )


def test_validate_schedule_times_rejects_end_before_start():
    start = datetime(
        2026,
        9,
        8,
        11,
        0,
    )

    end = datetime(
        2026,
        9,
        8,
        10,
        0,
    )

    with pytest.raises(
        ValidationError,
        match="scheduled_end must be later than scheduled_start",
    ):
        appointment_service._validate_schedule_times(
            start,
            end,
        )


# ============================================================================
# _validate_reschedule_times
# ============================================================================


def test_validate_reschedule_times_accepts_valid_times():
    start = datetime(
        2026,
        9,
        9,
        11,
        0,
    )

    end = datetime(
        2026,
        9,
        9,
        11,
        30,
    )

    result = appointment_service._validate_reschedule_times(
        start,
        end,
    )

    assert result is None


@pytest.mark.parametrize(
    "new_start,new_end",
    [
        (None, datetime(2026, 9, 9, 11, 30)),
        (datetime(2026, 9, 9, 11, 0), None),
        (None, None),
    ],
)
def test_validate_reschedule_times_requires_both_values(
    new_start,
    new_end,
):
    with pytest.raises(
        ValidationError,
        match="new_start and new_end are required",
    ):
        appointment_service._validate_reschedule_times(
            new_start,
            new_end,
        )


def test_validate_reschedule_times_rejects_equal_times():
    start = datetime(
        2026,
        9,
        9,
        11,
        0,
    )

    with pytest.raises(
        ValidationError,
        match="new_end must be later than new_start",
    ):
        appointment_service._validate_reschedule_times(
            start,
            start,
        )


def test_validate_reschedule_times_rejects_end_before_start():
    start = datetime(
        2026,
        9,
        9,
        12,
        0,
    )

    end = datetime(
        2026,
        9,
        9,
        11,
        0,
    )

    with pytest.raises(
        ValidationError,
        match="new_end must be later than new_start",
    ):
        appointment_service._validate_reschedule_times(
            start,
            end,
        )


# ============================================================================
# _ensure_status
# ============================================================================


def test_ensure_status_accepts_allowed_status():
    appointment = make_appointment(
        status=AppointmentStatus.SCHEDULED,
    )

    result = appointment_service._ensure_status(
        appointment,
        AppointmentStatus.SCHEDULED,
        AppointmentStatus.CONFIRMED,
    )

    assert result is None


def test_ensure_status_rejects_disallowed_status():
    appointment = make_appointment(
        appointment_id=7,
        status=AppointmentStatus.CANCELLED,
    )

    with pytest.raises(
        ConflictError,
        match="cannot perform this action",
    ):
        appointment_service._ensure_status(
            appointment,
            AppointmentStatus.SCHEDULED,
            AppointmentStatus.CONFIRMED,
        )


# ============================================================================
# _get_appointment
# ============================================================================


def test_get_appointment_returns_appointment(
    app,
    monkeypatch,
):
    appointment = make_appointment(
        appointment_id=7,
    )

    class FakeQuery:
        def filter(self, *args):
            return self

        def first(self):
            return appointment

    monkeypatch.setattr(
        appointment_service.Appointment,
        "query",
        FakeQuery(),
    )

    result = appointment_service._get_appointment(
        appointment_id=7,
    )

    assert result is appointment


def test_get_appointment_raises_not_found(
    app,
    monkeypatch,
):
    class FakeQuery:
        def filter(self, *args):
            return self

        def first(self):
            return None

    monkeypatch.setattr(
        appointment_service.Appointment,
        "query",
        FakeQuery(),
    )

    with pytest.raises(
        NotFoundError,
        match="Appointment 999 not found",
    ):
        appointment_service._get_appointment(
            appointment_id=999,
        )


def test_get_appointment_supports_clinic_filter(
    app,
    monkeypatch,
):
    appointment = make_appointment(
        appointment_id=7,
        clinic_id=10,
    )

    filters = []

    class FakeQuery:
        def filter(self, *args):
            filters.extend(args)
            return self

        def first(self):
            return appointment

    monkeypatch.setattr(
        appointment_service.Appointment,
        "query",
        FakeQuery(),
    )

    result = appointment_service._get_appointment(
        appointment_id=7,
        clinic_id=10,
    )

    assert result is appointment
    assert len(filters) == 2


# ============================================================================
# _find_patient_overlap
# ============================================================================


def test_find_patient_overlap_returns_matching_appointment(
    app,
    monkeypatch,
):
    appointment = make_appointment(
        appointment_id=7,
        patient_id=20,
    )

    class FakeQuery:
        def filter(self, *args):
            return self

        def first(self):
            return appointment

    monkeypatch.setattr(
        appointment_service.Appointment,
        "query",
        FakeQuery(),
    )

    result = appointment_service._find_patient_overlap(
        patient_id=20,
        scheduled_start=datetime(
            2026,
            9,
            8,
            10,
            0,
        ),
        scheduled_end=datetime(
            2026,
            9,
            8,
            10,
            30,
        ),
    )

    assert result is appointment


def test_find_patient_overlap_returns_none_when_no_match(
    app,
    monkeypatch,
):
    class FakeQuery:
        def filter(self, *args):
            return self

        def first(self):
            return None

    monkeypatch.setattr(
        appointment_service.Appointment,
        "query",
        FakeQuery(),
    )

    result = appointment_service._find_patient_overlap(
        patient_id=20,
        scheduled_start=datetime(
            2026,
            9,
            8,
            10,
            0,
        ),
        scheduled_end=datetime(
            2026,
            9,
            8,
            10,
            30,
        ),
    )

    assert result is None


# ============================================================================
# _find_staff_overlap
# ============================================================================


def test_find_staff_overlap_returns_matching_appointment(
    app,
    monkeypatch,
):
    appointment = make_appointment(
        appointment_id=8,
        staff_id=30,
    )

    class FakeQuery:
        def filter(self, *args):
            return self

        def first(self):
            return appointment

    monkeypatch.setattr(
        appointment_service.Appointment,
        "query",
        FakeQuery(),
    )

    result = appointment_service._find_staff_overlap(
        staff_id=30,
        scheduled_start=datetime(
            2026,
            9,
            8,
            10,
            0,
        ),
        scheduled_end=datetime(
            2026,
            9,
            8,
            10,
            30,
        ),
    )

    assert result is appointment


def test_find_staff_overlap_returns_none_when_no_match(
    app,
    monkeypatch,
):
    class FakeQuery:
        def filter(self, *args):
            return self

        def first(self):
            return None

    monkeypatch.setattr(
        appointment_service.Appointment,
        "query",
        FakeQuery(),
    )

    result = appointment_service._find_staff_overlap(
        staff_id=30,
        scheduled_start=datetime(
            2026,
            9,
            8,
            10,
            0,
        ),
        scheduled_end=datetime(
            2026,
            9,
            8,
            10,
            30,
        ),
    )

    assert result is None


# ============================================================================
# _ensure_no_schedule_conflict
# ============================================================================


def test_ensure_no_schedule_conflict_accepts_available_period(
    monkeypatch,
):
    monkeypatch.setattr(
        appointment_service,
        "_find_patient_overlap",
        lambda **kwargs: None,
    )

    monkeypatch.setattr(
        appointment_service,
        "_find_staff_overlap",
        lambda **kwargs: None,
    )

    result = appointment_service._ensure_no_schedule_conflict(
        patient_id=20,
        staff_id=30,
        scheduled_start=datetime(
            2026,
            9,
            8,
            10,
            0,
        ),
        scheduled_end=datetime(
            2026,
            9,
            8,
            10,
            30,
        ),
    )

    assert result is None


def test_ensure_no_schedule_conflict_rejects_patient_conflict(
    monkeypatch,
):
    conflict = make_appointment(
        appointment_id=55,
        patient_id=20,
    )

    monkeypatch.setattr(
        appointment_service,
        "_find_patient_overlap",
        lambda **kwargs: conflict,
    )

    with pytest.raises(
        ConflictError,
        match="Patient 20 already has an appointment",
    ):
        appointment_service._ensure_no_schedule_conflict(
            patient_id=20,
            staff_id=30,
            scheduled_start=datetime(
                2026,
                9,
                8,
                10,
                0,
            ),
            scheduled_end=datetime(
                2026,
                9,
                8,
                10,
                30,
            ),
        )


def test_ensure_no_schedule_conflict_rejects_staff_conflict(
    monkeypatch,
):
    conflict = make_appointment(
        appointment_id=56,
        staff_id=30,
    )

    monkeypatch.setattr(
        appointment_service,
        "_find_patient_overlap",
        lambda **kwargs: None,
    )

    monkeypatch.setattr(
        appointment_service,
        "_find_staff_overlap",
        lambda **kwargs: conflict,
    )

    with pytest.raises(
        ConflictError,
        match="Staff 30 already has an appointment",
    ):
        appointment_service._ensure_no_schedule_conflict(
            patient_id=20,
            staff_id=30,
            scheduled_start=datetime(
                2026,
                9,
                8,
                10,
                0,
            ),
            scheduled_end=datetime(
                2026,
                9,
                8,
                10,
                30,
            ),
        )


# ============================================================================
# create_appointment
# ============================================================================


def test_create_appointment_success(
    app,
    monkeypatch,
):
    clinic = type(
        "Clinic",
        (),
        {"id": 10},
    )()

    patient = type(
        "Patient",
        (),
        {"clinic_id": 10},
    )()

    staff = type(
        "Staff",
        (),
        {"id": 30},
    )()

    monkeypatch.setattr(
        appointment_service,
        "get_clinic",
        lambda clinic_id: clinic,
    )

    monkeypatch.setattr(
        appointment_service,
        "get_patient",
        lambda patient_id: patient,
    )

    monkeypatch.setattr(
        appointment_service,
        "get_staff",
        lambda staff_id, clinic_id: staff,
    )

    monkeypatch.setattr(
        appointment_service,
        "_ensure_no_schedule_conflict",
        lambda **kwargs: None,
    )

    monkeypatch.setattr(
        appointment_service,
        "create_audit_log",
        lambda **kwargs: None,
    )

    created = {}

    real_session = appointment_service.db.session

    def fake_add(appointment):
        created["appointment"] = appointment

    def fake_flush():
        created["appointment"].id = 101

    monkeypatch.setattr(
        real_session,
        "add",
        fake_add,
    )

    monkeypatch.setattr(
        real_session,
        "flush",
        fake_flush,
    )

    start = datetime(
        2026,
        9,
        8,
        10,
        0,
    )

    end = datetime(
        2026,
        9,
        8,
        10,
        30,
    )

    result = appointment_service.create_appointment(
        clinic_id=10,
        patient_id=20,
        staff_id=30,
        scheduled_start=start,
        scheduled_end=end,
        appointment_type=AppointmentType.IN_PERSON,
        reason="Routine consultation",
    )

    assert result.id == 101
    assert result.clinic_id == 10
    assert result.patient_id == 20
    assert result.staff_id == 30
    assert result.scheduled_start == start
    assert result.scheduled_end == end
    assert result.appointment_type == (
        AppointmentType.IN_PERSON
    )
    assert result.status == AppointmentStatus.SCHEDULED
    assert result.reason == "Routine consultation"


def test_create_appointment_rejects_invalid_schedule(
    app,
    monkeypatch,
):
    with pytest.raises(
        ValidationError,
        match="scheduled_end must be later than scheduled_start",
    ):
        appointment_service.create_appointment(
            clinic_id=10,
            patient_id=20,
            staff_id=30,
            scheduled_start=datetime(
                2026,
                9,
                8,
                11,
                0,
            ),
            scheduled_end=datetime(
                2026,
                9,
                8,
                10,
                0,
            ),
        )


def test_create_appointment_rejects_patient_clinic_mismatch(
    app,
    monkeypatch,
):
    clinic = type(
        "Clinic",
        (),
        {"id": 10},
    )()

    patient = type(
        "Patient",
        (),
        {"clinic_id": 99},
    )()

    staff = type(
        "Staff",
        (),
        {"id": 30},
    )()

    monkeypatch.setattr(
        appointment_service,
        "get_clinic",
        lambda clinic_id: clinic,
    )

    monkeypatch.setattr(
        appointment_service,
        "get_patient",
        lambda patient_id: patient,
    )

    monkeypatch.setattr(
        appointment_service,
        "get_staff",
        lambda staff_id, clinic_id: staff,
    )

    with pytest.raises(
        ConflictError,
        match="does not belong to clinic 10",
    ):
        appointment_service.create_appointment(
            clinic_id=10,
            patient_id=20,
            staff_id=30,
            scheduled_start=datetime(
                2026,
                9,
                8,
                10,
                0,
            ),
            scheduled_end=datetime(
                2026,
                9,
                8,
                10,
                30,
            ),
        )


def test_create_appointment_rejects_patient_schedule_conflict(
    app,
    monkeypatch,
):
    monkeypatch.setattr(
        appointment_service,
        "_validate_appointment_participants",
        lambda **kwargs: (
            type("Clinic", (), {"id": 10})(),
            type("Patient", (), {"clinic_id": 10})(),
            type("Staff", (), {})(),
        ),
    )

    conflict = make_appointment(
        appointment_id=88,
    )

    monkeypatch.setattr(
        appointment_service,
        "_find_patient_overlap",
        lambda **kwargs: conflict,
    )

    with pytest.raises(
        ConflictError,
        match="Patient 20 already has an appointment",
    ):
        appointment_service.create_appointment(
            clinic_id=10,
            patient_id=20,
            staff_id=30,
            scheduled_start=datetime(
                2026,
                9,
                8,
                10,
                0,
            ),
            scheduled_end=datetime(
                2026,
                9,
                8,
                10,
                30,
            ),
        )


# ============================================================================
# Reschedule
# ============================================================================


def test_reschedule_appointment_success(
    app,
    monkeypatch,
):
    appointment = make_appointment(
        appointment_id=5,
        status=AppointmentStatus.SCHEDULED,
    )

    monkeypatch.setattr(
        appointment_service,
        "_get_appointment",
        lambda **kwargs: appointment,
    )

    monkeypatch.setattr(
        appointment_service,
        "_ensure_no_schedule_conflict",
        lambda **kwargs: None,
    )

    monkeypatch.setattr(
        appointment_service,
        "create_audit_log",
        lambda **kwargs: None,
    )

    new_start = datetime(
        2026,
        9,
        9,
        11,
        0,
    )

    new_end = datetime(
        2026,
        9,
        9,
        11,
        30,
    )

    appointment.reminder_sent = True

    result = appointment_service.reschedule_appointment(
        appointment_id=5,
        new_start=new_start,
        new_end=new_end,
        clinic_id=10,
    )

    assert result is appointment
    assert result.scheduled_start == new_start
    assert result.scheduled_end == new_end
    assert result.reminder_sent is False


def test_reschedule_appointment_rejects_invalid_status(
    app,
    monkeypatch,
):
    appointment = make_appointment(
        appointment_id=5,
        status=AppointmentStatus.CANCELLED,
    )

    monkeypatch.setattr(
        appointment_service,
        "_get_appointment",
        lambda **kwargs: appointment,
    )

    with pytest.raises(
        ConflictError,
        match="cannot perform this action",
    ):
        appointment_service.reschedule_appointment(
            appointment_id=5,
            new_start=datetime(
                2026,
                9,
                9,
                11,
                0,
            ),
            new_end=datetime(
                2026,
                9,
                9,
                11,
                30,
            ),
            clinic_id=10,
        )


def test_reschedule_appointment_rejects_invalid_times(
    app,
    monkeypatch,
):
    appointment = make_appointment(
        appointment_id=5,
        status=AppointmentStatus.SCHEDULED,
    )

    monkeypatch.setattr(
        appointment_service,
        "_get_appointment",
        lambda **kwargs: appointment,
    )

    with pytest.raises(
        ValidationError,
        match="new_end must be later than new_start",
    ):
        appointment_service.reschedule_appointment(
            appointment_id=5,
            new_start=datetime(
                2026,
                9,
                9,
                12,
                0,
            ),
            new_end=datetime(
                2026,
                9,
                9,
                11,
                0,
            ),
            clinic_id=10,
        )


# ============================================================================
# Confirm
# ============================================================================


def test_confirm_appointment_success(
    app,
    monkeypatch,
):
    appointment = make_appointment(
        appointment_id=6,
        status=AppointmentStatus.SCHEDULED,
    )

    monkeypatch.setattr(
        appointment_service,
        "_get_appointment",
        lambda **kwargs: appointment,
    )

    monkeypatch.setattr(
        appointment_service,
        "create_audit_log",
        lambda **kwargs: None,
    )

    result = appointment_service.confirm_appointment(
        appointment_id=6,
        clinic_id=10,
    )

    assert result is appointment
    assert result.status == AppointmentStatus.CONFIRMED


def test_confirm_appointment_rejects_non_scheduled_status(
    app,
    monkeypatch,
):
    appointment = make_appointment(
        appointment_id=6,
        status=AppointmentStatus.COMPLETED,
    )

    monkeypatch.setattr(
        appointment_service,
        "_get_appointment",
        lambda **kwargs: appointment,
    )

    with pytest.raises(
        ConflictError,
        match="cannot perform this action",
    ):
        appointment_service.confirm_appointment(
            appointment_id=6,
            clinic_id=10,
        )


# ============================================================================
# Cancel
# ============================================================================


def test_cancel_appointment_success(
    app,
    monkeypatch,
):
    appointment = make_appointment(
        appointment_id=7,
        status=AppointmentStatus.SCHEDULED,
    )

    monkeypatch.setattr(
        appointment_service,
        "_get_appointment",
        lambda **kwargs: appointment,
    )

    monkeypatch.setattr(
        appointment_service,
        "create_audit_log",
        lambda **kwargs: None,
    )

    result = appointment_service.cancel_appointment(
        appointment_id=7,
        reason="Patient unavailable",
        clinic_id=10,
    )

    assert result is appointment
    assert result.status == AppointmentStatus.CANCELLED
    assert result.cancellation_reason == (
        "Patient unavailable"
    )
    assert result.cancelled_at is not None
    assert result.cancelled_at.tzinfo is not None


def test_cancel_appointment_accepts_no_reason(
    app,
    monkeypatch,
):
    appointment = make_appointment(
        appointment_id=8,
        status=AppointmentStatus.CONFIRMED,
    )

    monkeypatch.setattr(
        appointment_service,
        "_get_appointment",
        lambda **kwargs: appointment,
    )

    monkeypatch.setattr(
        appointment_service,
        "create_audit_log",
        lambda **kwargs: None,
    )

    result = appointment_service.cancel_appointment(
        appointment_id=8,
        clinic_id=10,
    )

    assert result.status == AppointmentStatus.CANCELLED
    assert result.cancellation_reason is None


def test_cancel_appointment_rejects_completed_status(
    app,
    monkeypatch,
):
    appointment = make_appointment(
        appointment_id=8,
        status=AppointmentStatus.COMPLETED,
    )

    monkeypatch.setattr(
        appointment_service,
        "_get_appointment",
        lambda **kwargs: appointment,
    )

    with pytest.raises(
        ConflictError,
        match="cannot perform this action",
    ):
        appointment_service.cancel_appointment(
            appointment_id=8,
            clinic_id=10,
        )


# ============================================================================
# Complete
# ============================================================================


def test_complete_appointment_success(
    app,
    monkeypatch,
):
    appointment = make_appointment(
        appointment_id=9,
        status=AppointmentStatus.CONFIRMED,
    )

    monkeypatch.setattr(
        appointment_service,
        "_get_appointment",
        lambda **kwargs: appointment,
    )

    monkeypatch.setattr(
        appointment_service,
        "create_audit_log",
        lambda **kwargs: None,
    )

    result = appointment_service.complete_appointment(
        appointment_id=9,
        notes="Consultation completed",
        clinic_id=10,
    )

    assert result is appointment
    assert result.status == AppointmentStatus.COMPLETED
    assert result.notes == (
        "Consultation completed"
    )


def test_complete_appointment_without_notes_preserves_existing_notes(
    app,
    monkeypatch,
):
    appointment = make_appointment(
        appointment_id=10,
        status=AppointmentStatus.CONFIRMED,
        notes="Existing notes",
    )

    monkeypatch.setattr(
        appointment_service,
        "_get_appointment",
        lambda **kwargs: appointment,
    )

    monkeypatch.setattr(
        appointment_service,
        "create_audit_log",
        lambda **kwargs: None,
    )

    result = appointment_service.complete_appointment(
        appointment_id=10,
        notes=None,
        clinic_id=10,
    )

    assert result.status == AppointmentStatus.COMPLETED
    assert result.notes == "Existing notes"


def test_complete_appointment_rejects_scheduled_status(
    app,
    monkeypatch,
):
    appointment = make_appointment(
        appointment_id=10,
        status=AppointmentStatus.SCHEDULED,
    )

    monkeypatch.setattr(
        appointment_service,
        "_get_appointment",
        lambda **kwargs: appointment,
    )

    with pytest.raises(
        ConflictError,
        match="cannot perform this action",
    ):
        appointment_service.complete_appointment(
            appointment_id=10,
            clinic_id=10,
        )


# ============================================================================
# No-show
# ============================================================================


def test_mark_no_show_success(
    app,
    monkeypatch,
):
    appointment = make_appointment(
        appointment_id=11,
        status=AppointmentStatus.CONFIRMED,
    )

    monkeypatch.setattr(
        appointment_service,
        "_get_appointment",
        lambda **kwargs: appointment,
    )

    monkeypatch.setattr(
        appointment_service,
        "create_audit_log",
        lambda **kwargs: None,
    )

    result = appointment_service.mark_no_show(
        appointment_id=11,
        clinic_id=10,
    )

    assert result is appointment
    assert result.status == AppointmentStatus.NO_SHOW


def test_mark_no_show_rejects_scheduled_status(
    app,
    monkeypatch,
):
    appointment = make_appointment(
        appointment_id=11,
        status=AppointmentStatus.SCHEDULED,
    )

    monkeypatch.setattr(
        appointment_service,
        "_get_appointment",
        lambda **kwargs: appointment,
    )

    with pytest.raises(
        ConflictError,
        match="cannot perform this action",
    ):
        appointment_service.mark_no_show(
            appointment_id=11,
            clinic_id=10,
        )


# ============================================================================
# Patient appointments
# ============================================================================


def test_get_appointments_for_patient_success(
    app,
    monkeypatch,
):
    patient = type(
        "Patient",
        (),
        {"clinic_id": 10},
    )()

    appointments = [
        make_appointment(
            appointment_id=1,
            patient_id=20,
        ),
        make_appointment(
            appointment_id=2,
            patient_id=20,
        ),
    ]

    monkeypatch.setattr(
        appointment_service,
        "get_patient",
        lambda patient_id: patient,
    )

    class FakeQuery:
        def filter(self, *args):
            return self

        def order_by(self, *args):
            return self

        def all(self):
            return appointments

    monkeypatch.setattr(
        appointment_service.Appointment,
        "query",
        FakeQuery(),
    )

    result = appointment_service.get_appointments_for_patient(
        patient_id=20,
        clinic_id=10,
    )

    assert result == appointments


def test_get_appointments_for_patient_rejects_wrong_clinic(
    monkeypatch,
):
    patient = type(
        "Patient",
        (),
        {"clinic_id": 99},
    )()

    monkeypatch.setattr(
        appointment_service,
        "get_patient",
        lambda patient_id: patient,
    )

    with pytest.raises(
        NotFoundError,
        match="Patient 20 not found",
    ):
        appointment_service.get_appointments_for_patient(
            patient_id=20,
            clinic_id=10,
        )


# ============================================================================
# Staff appointments
# ============================================================================


def test_get_appointments_for_staff_success(
    app,
    monkeypatch,
):
    appointments = [
        make_appointment(
            appointment_id=1,
            clinic_id=10,
            staff_id=30,
        ),
        make_appointment(
            appointment_id=2,
            clinic_id=10,
            staff_id=30,
        ),
    ]

    monkeypatch.setattr(
        appointment_service,
        "get_staff",
        lambda staff_id, clinic_id: object(),
    )

    class FakeQuery:
        def filter(self, *args):
            return self

        def order_by(self, *args):
            return self

        def all(self):
            return appointments

    monkeypatch.setattr(
        appointment_service.Appointment,
        "query",
        FakeQuery(),
    )

    result = appointment_service.get_appointments_for_staff(
        clinic_id=10,
        staff_id=30,
    )

    assert result == appointments


def test_get_appointments_for_staff_with_date_filter(
    app,
    monkeypatch,
):
    target_date = date(
        2026,
        9,
        8,
    )

    appointments = [
        make_appointment(
            appointment_id=1,
            clinic_id=10,
            staff_id=30,
        ),
    ]

    monkeypatch.setattr(
        appointment_service,
        "get_staff",
        lambda staff_id, clinic_id: object(),
    )

    class FakeQuery:
        def filter(self, *args):
            return self

        def order_by(self, *args):
            return self

        def all(self):
            return appointments

    monkeypatch.setattr(
        appointment_service.Appointment,
        "query",
        FakeQuery(),
    )

    result = appointment_service.get_appointments_for_staff(
        clinic_id=10,
        staff_id=30,
        date_=target_date,
    )

    assert result == appointments


# ============================================================================
# Reminder task
# ============================================================================


def test_send_appointment_reminder_ignores_missing_appointment(
    app,
    monkeypatch,
):
    monkeypatch.setattr(
        appointment_service.db.session,
        "get",
        lambda model, appointment_id: None,
    )

    result = appointment_service.send_appointment_reminder(
        999,
    )

    assert result is None


def test_send_appointment_reminder_ignores_already_sent_reminder(
    app,
    monkeypatch,
):
    appointment = make_appointment(
        appointment_id=12,
        reminder_sent=True,
    )

    monkeypatch.setattr(
        appointment_service.db.session,
        "get",
        lambda model, appointment_id: appointment,
    )

    result = appointment_service.send_appointment_reminder(
        12,
    )

    assert result is None
    assert appointment.reminder_sent is True


def test_send_appointment_reminder_marks_reminder_sent(
    app,
    monkeypatch,
):
    appointment = make_appointment(
        appointment_id=13,
        reminder_sent=False,
    )

    committed = False

    monkeypatch.setattr(
        appointment_service.db.session,
        "get",
        lambda model, appointment_id: appointment,
    )

    def fake_commit():
        nonlocal committed
        committed = True

    monkeypatch.setattr(
        appointment_service.db.session,
        "commit",
        fake_commit,
    )

    result = appointment_service.send_appointment_reminder(
        13,
    )

    assert result is None
    assert appointment.reminder_sent is True
    assert committed is True


# ============================================================================
# Upcoming appointment reminder task
# ============================================================================


def test_check_upcoming_appointments_queues_reminders(
    app,
    monkeypatch,
):
    appointment_one = make_appointment(
        appointment_id=20,
        status=AppointmentStatus.SCHEDULED,
        reminder_sent=False,
    )

    appointment_two = make_appointment(
        appointment_id=21,
        status=AppointmentStatus.CONFIRMED,
        reminder_sent=False,
    )

    appointments = [
        appointment_one,
        appointment_two,
    ]

    class FakeQuery:
        def filter(self, *args):
            return self

        def all(self):
            return appointments

    monkeypatch.setattr(
        appointment_service.Appointment,
        "query",
        FakeQuery(),
    )

    queued = []

    class FakeReminderTask:
        def delay(self, appointment_id):
            queued.append(appointment_id)

    monkeypatch.setattr(
        appointment_service,
        "send_appointment_reminder",
        FakeReminderTask(),
    )

    appointment_service.check_upcoming_appointments()

    assert queued == [20, 21]


def test_check_upcoming_appointments_handles_no_upcoming_appointments(
    app,
    monkeypatch,
):
    class FakeQuery:
        def filter(self, *args):
            return self

        def all(self):
            return []

    monkeypatch.setattr(
        appointment_service.Appointment,
        "query",
        FakeQuery(),
    )

    queued = []

    class FakeReminderTask:
        def delay(self, appointment_id):
            queued.append(appointment_id)

    monkeypatch.setattr(
        appointment_service,
        "send_appointment_reminder",
        FakeReminderTask(),
    )

    appointment_service.check_upcoming_appointments()

    assert queued == []