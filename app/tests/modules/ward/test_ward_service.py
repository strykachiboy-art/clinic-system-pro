from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus
from app.core.enums.ward_enums import (
    AdmissionStatus,
    BedStatus,
    ReservationStatus,
    WardType,
)
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.extensions import db
from app.modules.ward.models.ward_model import Ward
from app.modules.ward.services import ward_service


# ============================================================================
# HELPERS
# ============================================================================


def _future_datetime(minutes: int = 30) -> datetime:
    return datetime.now(timezone.utc) + timedelta(
        minutes=minutes,
    )


def _naive_utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(
        tzinfo=None,
    )


def _future_expiry(minutes: int = 30) -> datetime:
    return _naive_utc_now() + timedelta(
        minutes=minutes,
    )


def _create_ward(
    clinic,
    *,
    name: str = "General Ward",
    ward_type: WardType = WardType.GENERAL,
    capacity: int = 5,
    actor_user_id: int | None = None,
):
    return ward_service.create_ward(
        clinic_id=clinic.id,
        name=name,
        ward_type=ward_type,
        capacity=capacity,
        actor_user_id=actor_user_id,
    )


def _create_bed(
    clinic,
    *,
    name: str = "General Ward",
    capacity: int = 5,
    bed_number: str = "B-001",
    actor_user_id: int | None = None,
):
    ward = _create_ward(
        clinic,
        name=name,
        capacity=capacity,
        actor_user_id=actor_user_id,
    )

    bed = ward_service.add_bed(
        ward_id=ward.id,
        bed_number=bed_number,
        clinic_id=clinic.id,
        actor_user_id=actor_user_id,
    )

    return ward, bed


def _create_reservation(
    clinic,
    make_patient,
    make_staff,
    *,
    bed_number: str = "B-001",
    ward_name: str = "General Ward",
    actor_staff=None,
    patient=None,
    expires_at=None,
    reason: str | None = None,
):
    if actor_staff is None:
        actor_staff = make_staff(
            clinic=clinic,
            role=Role.DOCTOR,
        )

    if patient is None:
        patient = make_patient(
            clinic=clinic,
        )

    ward, bed = _create_bed(
        clinic,
        name=ward_name,
        bed_number=bed_number,
    )

    reservation = ward_service.reserve_bed(
        patient_id=patient.id,
        bed_id=bed.id,
        reserved_by_id=actor_staff.id,
        clinic_id=clinic.id,
        reason=reason,
        expires_at=expires_at,
        actor_user_id=actor_staff.user_id,
    )

    return (
        ward,
        bed,
        patient,
        actor_staff,
        reservation,
    )


def _create_admission(
    clinic,
    make_patient,
    make_staff,
    *,
    bed_number: str = "B-001",
    ward_name: str = "General Ward",
    actor_staff=None,
    patient=None,
    reason: str | None = None,
):
    if actor_staff is None:
        actor_staff = make_staff(
            clinic=clinic,
            role=Role.DOCTOR,
        )

    if patient is None:
        patient = make_patient(
            clinic=clinic,
        )

    ward, bed = _create_bed(
        clinic,
        name=ward_name,
        bed_number=bed_number,
    )

    admission = ward_service.admit_patient(
        patient_id=patient.id,
        bed_id=bed.id,
        admitted_by_id=actor_staff.id,
        clinic_id=clinic.id,
        reason=reason,
        actor_user_id=actor_staff.user_id,
    )

    return (
        ward,
        bed,
        patient,
        actor_staff,
        admission,
    )


# ============================================================================
# DATETIME HELPERS
# ============================================================================


def test_utcnow_returns_timezone_aware_datetime():
    result = ward_service._utcnow()

    assert isinstance(result, datetime)
    assert result.tzinfo is not None


def test_db_now_returns_naive_datetime():
    result = ward_service._db_now()

    assert isinstance(result, datetime)
    assert result.tzinfo is None


def test_normalize_db_datetime_converts_aware_datetime_to_naive_utc():
    value = datetime(
        2026,
        9,
        9,
        12,
        30,
        tzinfo=timezone.utc,
    )

    result = ward_service._normalize_db_datetime(value)

    assert result.tzinfo is None
    assert result == datetime(
        2026,
        9,
        9,
        12,
        30,
    )


def test_normalize_db_datetime_accepts_naive_datetime():
    value = datetime(
        2026,
        9,
        9,
        12,
        30,
    )

    result = ward_service._normalize_db_datetime(value)

    assert result == value
    assert result.tzinfo is None


def test_normalize_db_datetime_none_returns_none():
    assert (
        ward_service._normalize_db_datetime(None)
        is None
    )


def test_normalize_db_datetime_rejects_invalid_value():
    with pytest.raises(
        ValidationError,
        match="Invalid datetime value",
    ):
        ward_service._normalize_db_datetime(
            "2026-09-09"
        )


# ============================================================================
# GENERAL VALIDATION
# ============================================================================


@pytest.mark.parametrize(
    "value",
    [
        None,
        0,
        -1,
        "1",
    ],
)
def test_validate_positive_id_rejects_invalid_values(
    value,
):
    with pytest.raises(
        ValidationError,
        match="must be a positive integer|required",
    ):
        ward_service._validate_positive_id(
            value,
            "test_id",
        )


def test_validate_positive_id_accepts_positive_integer():
    assert (
        ward_service._validate_positive_id(
            10,
            "test_id",
        )
        == 10
    )


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
    ],
)
def test_normalize_text_returns_none_for_blank(
    value,
):
    assert ward_service._normalize_text(value) is None


def test_normalize_text_strips_text():
    assert (
        ward_service._normalize_text(
            "  General Ward  "
        )
        == "General Ward"
    )


def test_validate_ward_type_defaults_to_general():
    assert (
        ward_service._validate_ward_type(None)
        == WardType.GENERAL
    )


def test_validate_ward_type_accepts_enum():
    assert (
        ward_service._validate_ward_type(
            WardType.GENERAL
        )
        == WardType.GENERAL
    )


def test_validate_ward_type_accepts_value():
    assert (
        ward_service._validate_ward_type(
            WardType.GENERAL.value
        )
        == WardType.GENERAL
    )


def test_validate_ward_type_rejects_invalid_value():
    with pytest.raises(
        ValidationError,
        match="Invalid ward type",
    ):
        ward_service._validate_ward_type(
            "NOT_A_REAL_WARD_TYPE"
        )


@pytest.mark.parametrize(
    "value",
    [
        None,
        -1,
    ],
)
def test_validate_capacity_rejects_invalid_value(
    value,
):
    with pytest.raises(
        ValidationError,
        match="capacity",
    ):
        ward_service._validate_ward_capacity_value(
            value
        )


def test_validate_capacity_rejects_non_integer():
    with pytest.raises(
        ValidationError,
        match="capacity must be an integer",
    ):
        ward_service._validate_ward_capacity_value(
            "5"
        )


def test_validate_capacity_accepts_zero():
    assert (
        ward_service._validate_ward_capacity_value(
            0
        )
        == 0
    )


def test_validate_bed_number_normalizes_text():
    assert (
        ward_service._validate_bed_number(
            "  B-001  "
        )
        == "B-001"
    )


def test_validate_bed_number_rejects_blank():
    with pytest.raises(
        ValidationError,
        match="bed_number is required",
    ):
        ward_service._validate_bed_number("   ")


def test_validate_bed_number_rejects_too_long():
    with pytest.raises(
        ValidationError,
        match="cannot exceed 30",
    ):
        ward_service._validate_bed_number(
            "B" * 31
        )


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
    ],
)
def test_validate_reason_normalizes_blank_to_none(
    value,
):
    assert (
        ward_service._validate_reason(value)
        is None
    )


def test_validate_reason_strips_text():
    assert (
        ward_service._validate_reason(
            "  Patient transferred  "
        )
        == "Patient transferred"
    )


def test_validate_reason_rejects_too_long():
    with pytest.raises(
        ValidationError,
        match="reason cannot exceed 255",
    ):
        ward_service._validate_reason(
            "x" * 256
        )


# ============================================================================
# WARD LOOKUP / LIST
# ============================================================================


def test_get_ward_returns_clinic_owned_ward(
    clinic,
):
    ward = _create_ward(clinic)

    result = ward_service.get_ward(
        ward_id=ward.id,
        clinic_id=clinic.id,
    )

    assert result.id == ward.id


def test_get_ward_can_read_without_clinic_scope(
    clinic,
):
    ward = _create_ward(clinic)

    result = ward_service.get_ward(
        ward_id=ward.id,
    )

    assert result.id == ward.id


def test_get_ward_enforces_clinic_isolation(
    clinic,
    make_clinic,
):
    other_clinic = make_clinic()

    ward = _create_ward(
        other_clinic,
        name="Foreign Ward",
    )

    with pytest.raises(NotFoundError):
        ward_service.get_ward(
            ward_id=ward.id,
            clinic_id=clinic.id,
        )


def test_get_ward_missing_raises_not_found(
    clinic,
):
    with pytest.raises(NotFoundError):
        ward_service.get_ward(
            ward_id=999999,
            clinic_id=clinic.id,
        )


def test_list_wards_returns_only_clinic_wards(
    clinic,
    make_clinic,
):
    other_clinic = make_clinic()

    local = _create_ward(
        clinic,
        name="Local Ward",
    )

    foreign = _create_ward(
        other_clinic,
        name="Foreign Ward",
    )

    results = ward_service.list_wards(
        clinic.id,
    )

    ids = {ward.id for ward in results}

    assert local.id in ids
    assert foreign.id not in ids


def test_list_wards_filters_by_type(
    clinic,
):
    general = _create_ward(
        clinic,
        name="General Ward",
        ward_type=WardType.GENERAL,
    )

    other_type = next(
        ward_type
        for ward_type in WardType
        if ward_type != WardType.GENERAL
    )

    specialty = _create_ward(
        clinic,
        name="Specialty Ward",
        ward_type=other_type,
    )

    results = ward_service.list_wards(
        clinic.id,
        ward_type=other_type,
    )

    ids = {ward.id for ward in results}

    assert specialty.id in ids
    assert general.id not in ids


def test_list_wards_accepts_string_ward_type(
    clinic,
):
    ward = _create_ward(
        clinic,
        name="General Ward",
        ward_type=WardType.GENERAL,
    )

    results = ward_service.list_wards(
        clinic.id,
        ward_type=WardType.GENERAL.value,
    )

    ids = {item.id for item in results}

    assert ward.id in ids


def test_list_wards_rejects_invalid_ward_type(
    clinic,
):
    with pytest.raises(
        ValidationError,
        match="Invalid ward type",
    ):
        ward_service.list_wards(
            clinic.id,
            ward_type="NOT_REAL",
        )


# ============================================================================
# CREATE WARD
# ============================================================================


def test_create_ward_success(
    clinic,
    make_staff,
    monkeypatch,
):
    actor = make_staff(
        clinic=clinic,
        role=Role.ADMIN,
    )

    audit = Mock()

    monkeypatch.setattr(
        ward_service,
        "create_audit_log",
        audit,
    )

    ward = ward_service.create_ward(
        clinic_id=clinic.id,
        name="  Surgical Ward  ",
        ward_type=WardType.GENERAL,
        capacity=20,
        actor_user_id=actor.user_id,
    )

    assert ward.id is not None
    assert ward.clinic_id == clinic.id
    assert ward.name == "Surgical Ward"
    assert ward.ward_type == WardType.GENERAL
    assert ward.capacity == 20

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == AuditAction.CREATE
    assert kwargs["entity_type"] == "ward"
    assert kwargs["entity_id"] == ward.id
    assert kwargs["user_id"] == actor.user_id


def test_create_ward_defaults_none_type_to_general(
    clinic,
):
    ward = ward_service.create_ward(
        clinic_id=clinic.id,
        name="General Ward",
        ward_type=None,
        capacity=10,
    )

    assert ward.ward_type == WardType.GENERAL


def test_create_ward_rejects_blank_name(
    clinic,
):
    with pytest.raises(
        ValidationError,
        match="Ward name is required",
    ):
        ward_service.create_ward(
            clinic_id=clinic.id,
            name="   ",
            ward_type=WardType.GENERAL,
            capacity=5,
        )


def test_create_ward_rejects_long_name(
    clinic,
):
    with pytest.raises(
        ValidationError,
        match="cannot exceed 150",
    ):
        ward_service.create_ward(
            clinic_id=clinic.id,
            name="W" * 151,
            ward_type=WardType.GENERAL,
            capacity=5,
        )


def test_create_ward_rejects_duplicate_name(
    clinic,
):
    _create_ward(
        clinic,
        name="General Ward",
    )

    with pytest.raises(
        ConflictError,
        match="already exists",
    ):
        ward_service.create_ward(
            clinic_id=clinic.id,
            name="General Ward",
            ward_type=WardType.GENERAL,
            capacity=5,
        )


def test_create_ward_allows_same_name_in_different_clinics(
    clinic,
    make_clinic,
):
    other_clinic = make_clinic()

    first = _create_ward(
        clinic,
        name="Shared Name",
    )

    second = _create_ward(
        other_clinic,
        name="Shared Name",
    )

    assert first.name == second.name
    assert first.clinic_id != second.clinic_id


def test_create_ward_rejects_inactive_clinic(
    suspended_clinic,
):
    with pytest.raises(
        ValidationError,
        match="not active",
    ):
        ward_service.create_ward(
            clinic_id=suspended_clinic.id,
            name="Closed Ward",
            ward_type=WardType.GENERAL,
            capacity=5,
        )


def test_create_ward_rejects_invalid_clinic_id(
    app,
):
    with pytest.raises(NotFoundError):
        ward_service.create_ward(
            clinic_id=999999,
            name="Missing Clinic Ward",
            ward_type=WardType.GENERAL,
            capacity=5,
        )


def test_create_ward_rejects_invalid_actor_id(
    clinic,
):
    with pytest.raises(
        ValidationError,
        match="actor_user_id",
    ):
        ward_service.create_ward(
            clinic_id=clinic.id,
            name="Invalid Actor Ward",
            ward_type=WardType.GENERAL,
            capacity=5,
            actor_user_id=0,
        )


# ============================================================================
# UPDATE WARD
# ============================================================================


def test_update_ward_updates_allowed_fields(
    clinic,
    make_staff,
    monkeypatch,
):
    actor = make_staff(
        clinic=clinic,
        role=Role.ADMIN,
    )

    ward = _create_ward(
        clinic,
        name="Old Ward",
        capacity=10,
    )

    audit = Mock()

    monkeypatch.setattr(
        ward_service,
        "create_audit_log",
        audit,
    )

    other_type = next(iter(WardType))

    result = ward_service.update_ward(
        ward_id=ward.id,
        clinic_id=clinic.id,
        actor_user_id=actor.user_id,
        name="  New Ward  ",
        ward_type=other_type,
        capacity=12,
    )

    assert result.name == "New Ward"
    assert result.ward_type == other_type
    assert result.capacity == 12

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == AuditAction.UPDATE
    assert kwargs["entity_type"] == "ward"
    assert kwargs["entity_id"] == ward.id
    assert kwargs["old_value"]["name"] == "Old Ward"
    assert kwargs["new_value"]["name"] == "New Ward"


def test_update_ward_rejects_blank_name(
    clinic,
):
    ward = _create_ward(clinic)

    with pytest.raises(
        ValidationError,
        match="Ward name cannot be empty",
    ):
        ward_service.update_ward(
            ward.id,
            clinic.id,
            name="   ",
        )


def test_update_ward_rejects_long_name(
    clinic,
):
    ward = _create_ward(clinic)

    with pytest.raises(
        ValidationError,
        match="cannot exceed 150",
    ):
        ward_service.update_ward(
            ward.id,
            clinic.id,
            name="W" * 151,
        )


def test_update_ward_rejects_duplicate_name(
    clinic,
):
    first = _create_ward(
        clinic,
        name="Ward One",
    )

    second = _create_ward(
        clinic,
        name="Ward Two",
    )

    with pytest.raises(
        ConflictError,
        match="already exists",
    ):
        ward_service.update_ward(
            second.id,
            clinic.id,
            name=first.name,
        )


def test_update_ward_rejects_capacity_below_configured_beds(
    clinic,
):
    ward = _create_ward(
        clinic,
        name="Capacity Ward",
        capacity=3,
    )

    ward_service.add_bed(
        ward_id=ward.id,
        bed_number="B-001",
        clinic_id=clinic.id,
    )

    ward_service.add_bed(
        ward_id=ward.id,
        bed_number="B-002",
        clinic_id=clinic.id,
    )

    with pytest.raises(
        ConflictError,
        match="configured bed count",
    ):
        ward_service.update_ward(
            ward.id,
            clinic.id,
            capacity=1,
        )


def test_update_ward_allows_capacity_above_configured_beds(
    clinic,
):
    ward = _create_ward(
        clinic,
        name="Capacity Ward",
        capacity=3,
    )

    ward_service.add_bed(
        ward.id,
        "B-001",
        clinic.id,
    )

    result = ward_service.update_ward(
        ward.id,
        clinic.id,
        capacity=5,
    )

    assert result.capacity == 5


def test_update_ward_enforces_clinic_isolation(
    clinic,
    make_clinic,
):
    other_clinic = make_clinic()

    ward = _create_ward(
        other_clinic,
        name="Foreign Ward",
    )

    with pytest.raises(NotFoundError):
        ward_service.update_ward(
            ward.id,
            clinic.id,
            name="No Access",
        )


def test_update_ward_rejects_inactive_clinic(
    suspended_clinic,
):
    with pytest.raises(
        ValidationError,
        match="not active",
    ):
        ward_service.update_ward(
            ward_id=1,
            clinic_id=suspended_clinic.id,
            name="Updated Ward",
        )


# ============================================================================
# WARD OCCUPANCY
# ============================================================================


def test_get_ward_occupancy_reports_bed_states(
    clinic,
    make_patient,
    make_staff,
):
    ward = _create_ward(
        clinic,
        name="Occupancy Ward",
        capacity=4,
    )

    bed_available = ward_service.add_bed(
        ward.id,
        "B-001",
        clinic.id,
    )

    bed_reserved = ward_service.add_bed(
        ward.id,
        "B-002",
        clinic.id,
    )

    bed_occupied = ward_service.add_bed(
        ward.id,
        "B-003",
        clinic.id,
    )

    bed_maintenance = ward_service.add_bed(
        ward.id,
        "B-004",
        clinic.id,
    )

    patient = make_patient(
        clinic=clinic,
    )

    actor = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    ward_service.reserve_bed(
        patient_id=patient.id,
        bed_id=bed_reserved.id,
        reserved_by_id=actor.id,
        clinic_id=clinic.id,
        actor_user_id=actor.user_id,
    )

    patient2 = make_patient(
        clinic=clinic,
    )

    ward_service.admit_patient(
        patient_id=patient2.id,
        bed_id=bed_occupied.id,
        admitted_by_id=actor.id,
        clinic_id=clinic.id,
        actor_user_id=actor.user_id,
    )

    ward_service.set_bed_maintenance(
        bed_maintenance.id,
        True,
        clinic.id,
    )

    db.session.refresh(ward)

    result = ward_service.get_ward_occupancy(
        ward.id,
        clinic.id,
    )

    assert result["ward_id"] == ward.id
    assert result["clinic_id"] == clinic.id
    assert result["ward_name"] == ward.name
    assert result["capacity"] == 4
    assert result["total_beds"] == 4
    assert result["available"] == 1
    assert result["reserved"] == 1
    assert result["occupied"] == 1
    assert result["maintenance"] == 1


# ============================================================================
# BED LOOKUP / LIST
# ============================================================================


def test_get_bed_returns_clinic_owned_bed(
    clinic,
):
    ward, bed = _create_bed(clinic)

    result = ward_service.get_bed(
        bed.id,
        clinic.id,
    )

    assert result.id == bed.id
    assert result.ward_id == ward.id


def test_get_bed_enforces_clinic_isolation(
    clinic,
    make_clinic,
):
    other_clinic = make_clinic()

    _, bed = _create_bed(
        other_clinic,
        name="Foreign Ward",
    )

    with pytest.raises(NotFoundError):
        ward_service.get_bed(
            bed.id,
            clinic.id,
        )


def test_get_bed_missing_raises_not_found(
    clinic,
):
    with pytest.raises(NotFoundError):
        ward_service.get_bed(
            999999,
            clinic.id,
        )


def test_list_beds_returns_ward_beds(
    clinic,
):
    ward = _create_ward(
        clinic,
        name="Bed Ward",
        capacity=3,
    )

    first = ward_service.add_bed(
        ward.id,
        "B-002",
        clinic.id,
    )

    second = ward_service.add_bed(
        ward.id,
        "B-001",
        clinic.id,
    )

    results = ward_service.list_beds(
        ward.id,
        clinic.id,
    )

    assert [bed.id for bed in results] == [
        second.id,
        first.id,
    ]


def test_list_beds_filters_by_status(
    clinic,
):
    ward = _create_ward(
        clinic,
        name="Status Ward",
        capacity=2,
    )

    available = ward_service.add_bed(
        ward.id,
        "B-001",
        clinic.id,
    )

    maintenance = ward_service.add_bed(
        ward.id,
        "B-002",
        clinic.id,
    )

    ward_service.set_bed_maintenance(
        maintenance.id,
        True,
        clinic.id,
    )

    results = ward_service.list_beds(
        ward.id,
        clinic.id,
        status=BedStatus.MAINTENANCE,
    )

    ids = {bed.id for bed in results}

    assert maintenance.id in ids
    assert available.id not in ids


def test_list_beds_accepts_string_status(
    clinic,
):
    ward, bed = _create_bed(clinic)

    results = ward_service.list_beds(
        ward.id,
        clinic.id,
        status=BedStatus.AVAILABLE.value,
    )

    ids = {item.id for item in results}

    assert bed.id in ids


def test_list_beds_rejects_invalid_status(
    clinic,
):
    ward = _create_ward(
        clinic,
        name="Status Ward",
        capacity=1,
    )

    with pytest.raises(
        ValidationError,
        match="Invalid bed status",
    ):
        ward_service.list_beds(
            ward.id,
            clinic.id,
            status="INVALID_STATUS",
        )


def test_list_beds_rejects_foreign_ward(
    clinic,
    make_clinic,
):
    other_clinic = make_clinic()

    ward = _create_ward(
        other_clinic,
        name="Foreign Ward",
        capacity=1,
    )

    with pytest.raises(NotFoundError):
        ward_service.list_beds(
            ward.id,
            clinic.id,
        )


# ============================================================================
# ADD BED
# ============================================================================


def test_add_bed_success(
    clinic,
    make_staff,
    monkeypatch,
):
    actor = make_staff(
        clinic=clinic,
        role=Role.ADMIN,
    )

    ward = _create_ward(
        clinic,
        name="Bed Ward",
        capacity=2,
    )

    audit = Mock()

    monkeypatch.setattr(
        ward_service,
        "create_audit_log",
        audit,
    )

    bed = ward_service.add_bed(
        ward_id=ward.id,
        bed_number="  B-001  ",
        clinic_id=clinic.id,
        actor_user_id=actor.user_id,
    )

    assert bed.id is not None
    assert bed.ward_id == ward.id
    assert bed.bed_number == "B-001"
    assert bed.status == BedStatus.AVAILABLE

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == AuditAction.CREATE
    assert kwargs["entity_type"] == "bed"
    assert kwargs["entity_id"] == bed.id
    assert kwargs["user_id"] == actor.user_id


def test_add_bed_rejects_duplicate_number(
    clinic,
):
    ward = _create_ward(
        clinic,
        name="Duplicate Bed Ward",
        capacity=3,
    )

    ward_service.add_bed(
        ward.id,
        "B-001",
        clinic.id,
    )

    with pytest.raises(
        ConflictError,
        match="already exists",
    ):
        ward_service.add_bed(
            ward.id,
            "B-001",
            clinic.id,
        )


def test_add_bed_rejects_capacity_exceeded(
    clinic,
):
    ward = _create_ward(
        clinic,
        name="Full Ward",
        capacity=1,
    )

    ward_service.add_bed(
        ward.id,
        "B-001",
        clinic.id,
    )

    with pytest.raises(
        ConflictError,
        match="reached",
    ):
        ward_service.add_bed(
            ward.id,
            "B-002",
            clinic.id,
        )


def test_add_bed_rejects_invalid_bed_number(
    clinic,
):
    ward = _create_ward(
        clinic,
        name="Invalid Bed Ward",
        capacity=2,
    )

    with pytest.raises(
        ValidationError,
        match="bed_number is required",
    ):
        ward_service.add_bed(
            ward.id,
            "   ",
            clinic.id,
        )


def test_add_bed_rejects_foreign_ward(
    clinic,
    make_clinic,
):
    other_clinic = make_clinic()

    ward = _create_ward(
        other_clinic,
        name="Foreign Ward",
        capacity=1,
    )

    with pytest.raises(NotFoundError):
        ward_service.add_bed(
            ward.id,
            "B-001",
            clinic.id,
        )


def test_add_bed_rejects_inactive_clinic(
    suspended_clinic,
):
    ward = Ward(
        clinic_id=suspended_clinic.id,
        name="Suspended Ward",
        ward_type=WardType.GENERAL,
        capacity=1,
    )

    db.session.add(ward)
    db.session.flush()

    with pytest.raises(
        ValidationError,
        match="not active",
    ):
        ward_service.add_bed(
            ward_id=ward.id,
            bed_number="B-001",
            clinic_id=suspended_clinic.id,
        )


# ============================================================================
# BED MAINTENANCE
# ============================================================================


def test_set_bed_maintenance_places_available_bed_into_maintenance(
    clinic,
    monkeypatch,
):
    _, bed = _create_bed(clinic)

    audit = Mock()

    monkeypatch.setattr(
        ward_service,
        "create_audit_log",
        audit,
    )

    result = ward_service.set_bed_maintenance(
        bed.id,
        True,
        clinic.id,
    )

    assert result.status == BedStatus.MAINTENANCE

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == AuditAction.UPDATE
    assert kwargs["entity_type"] == "bed"
    assert kwargs["old_value"]["status"] == (
        BedStatus.AVAILABLE.value
    )
    assert kwargs["new_value"]["status"] == (
        BedStatus.MAINTENANCE.value
    )


def test_set_bed_maintenance_restores_available_bed(
    clinic,
):
    _, bed = _create_bed(clinic)

    ward_service.set_bed_maintenance(
        bed.id,
        True,
        clinic.id,
    )

    result = ward_service.set_bed_maintenance(
        bed.id,
        False,
        clinic.id,
    )

    assert result.status == BedStatus.AVAILABLE


def test_set_bed_maintenance_rejects_non_boolean(
    clinic,
):
    _, bed = _create_bed(clinic)

    with pytest.raises(
        ValidationError,
        match="must be boolean",
    ):
        ward_service.set_bed_maintenance(
            bed.id,
            "true",
            clinic.id,
        )


def test_set_bed_maintenance_rejects_occupied_bed(
    clinic,
    make_patient,
    make_staff,
):
    _, bed, _, _, _ = _create_admission(
        clinic,
        make_patient,
        make_staff,
    )

    with pytest.raises(
        ConflictError,
        match="while 'occupied'",
    ):
        ward_service.set_bed_maintenance(
            bed.id,
            True,
            clinic.id,
        )


def test_set_bed_maintenance_rejects_reserved_bed(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        bed,
        _,
        _,
        _,
    ) = _create_reservation(
        clinic,
        make_patient,
        make_staff,
    )

    with pytest.raises(
        ConflictError,
        match="while 'reserved'",
    ):
        ward_service.set_bed_maintenance(
            bed.id,
            True,
            clinic.id,
        )


def test_set_bed_maintenance_rejects_restore_when_not_in_maintenance(
    clinic,
):
    _, bed = _create_bed(clinic)

    with pytest.raises(
        ConflictError,
        match="not under maintenance",
    ):
        ward_service.set_bed_maintenance(
            bed.id,
            False,
            clinic.id,
        )


# ============================================================================
# BED RESERVATIONS
# ============================================================================


def test_get_bed_reservation_returns_clinic_owned_reservation(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        _,
        _,
        _,
        reservation,
    ) = _create_reservation(
        clinic,
        make_patient,
        make_staff,
    )

    result = ward_service.get_bed_reservation(
        reservation.id,
        clinic.id,
    )

    assert result.id == reservation.id


def test_get_bed_reservation_enforces_clinic_isolation(
    clinic,
    make_clinic,
    make_patient,
    make_staff,
):
    other_clinic = make_clinic()

    (
        _,
        _,
        _,
        _,
        reservation,
    ) = _create_reservation(
        other_clinic,
        make_patient,
        make_staff,
    )

    with pytest.raises(NotFoundError):
        ward_service.get_bed_reservation(
            reservation.id,
            clinic.id,
        )


def test_list_bed_reservations_filters_status(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        _,
        _,
        _,
        pending,
    ) = _create_reservation(
        clinic,
        make_patient,
        make_staff,
        bed_number="B-001",
    )

    _, cancelled_bed = _create_bed(
        clinic,
        name="Another Ward",
        bed_number="B-002",
    )

    patient = make_patient(
        clinic=clinic,
    )

    actor = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    cancelled = ward_service.reserve_bed(
        patient_id=patient.id,
        bed_id=cancelled_bed.id,
        reserved_by_id=actor.id,
        clinic_id=clinic.id,
        actor_user_id=actor.user_id,
    )

    ward_service.cancel_bed_reservation(
        reservation_id=cancelled.id,
        clinic_id=clinic.id,
        actor_user_id=actor.user_id,
    )

    results = ward_service.list_bed_reservations(
        clinic_id=clinic.id,
        status=ReservationStatus.PENDING,
    )

    ids = {item.id for item in results}

    assert pending.id in ids
    assert cancelled.id not in ids


def test_list_bed_reservations_filters_patient(
    clinic,
    make_patient,
    make_staff,
):
    actor = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    patient_a = make_patient(
        clinic=clinic,
    )

    patient_b = make_patient(
        clinic=clinic,
    )

    _, bed_a = _create_bed(
        clinic,
        name="Reservation Ward A",
        bed_number="B-001",
    )

    _, bed_b = _create_bed(
        clinic,
        name="Reservation Ward B",
        bed_number="B-002",
    )

    first = ward_service.reserve_bed(
        patient_id=patient_a.id,
        bed_id=bed_a.id,
        reserved_by_id=actor.id,
        clinic_id=clinic.id,
        actor_user_id=actor.user_id,
    )

    second = ward_service.reserve_bed(
        patient_id=patient_b.id,
        bed_id=bed_b.id,
        reserved_by_id=actor.id,
        clinic_id=clinic.id,
        actor_user_id=actor.user_id,
    )

    results = ward_service.list_bed_reservations(
        clinic_id=clinic.id,
        patient_id=patient_a.id,
    )

    ids = {item.id for item in results}

    assert ids == {first.id}
    assert second.id not in ids


def test_list_bed_reservations_filters_bed(
    clinic,
    make_patient,
    make_staff,
):
    actor = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    patient_a = make_patient(
        clinic=clinic,
    )

    patient_b = make_patient(
        clinic=clinic,
    )

    _, bed_a = _create_bed(
        clinic,
        name="Reservation Ward A",
        bed_number="B-001",
    )

    _, bed_b = _create_bed(
        clinic,
        name="Reservation Ward B",
        bed_number="B-002",
    )

    first = ward_service.reserve_bed(
        patient_id=patient_a.id,
        bed_id=bed_a.id,
        reserved_by_id=actor.id,
        clinic_id=clinic.id,
        actor_user_id=actor.user_id,
    )

    second = ward_service.reserve_bed(
        patient_id=patient_b.id,
        bed_id=bed_b.id,
        reserved_by_id=actor.id,
        clinic_id=clinic.id,
        actor_user_id=actor.user_id,
    )

    results = ward_service.list_bed_reservations(
        clinic_id=clinic.id,
        bed_id=bed_a.id,
    )

    ids = {item.id for item in results}

    assert ids == {first.id}
    assert second.id not in ids


def test_get_active_bed_reservation_for_patient_returns_pending_reservation(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        _,
        patient,
        _,
        reservation,
    ) = _create_reservation(
        clinic,
        make_patient,
        make_staff,
    )

    result = (
        ward_service
        .get_active_bed_reservation_for_patient(
            patient.id,
            clinic.id,
        )
    )

    assert result.id == reservation.id


def test_get_active_bed_reservation_for_bed_returns_pending_reservation(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        bed,
        _,
        _,
        reservation,
    ) = _create_reservation(
        clinic,
        make_patient,
        make_staff,
    )

    result = (
        ward_service
        .get_active_bed_reservation_for_bed(
            bed.id,
            clinic.id,
        )
    )

    assert result.id == reservation.id


def test_reserve_bed_success(
    clinic,
    make_patient,
    make_staff,
    monkeypatch,
):
    actor = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    patient = make_patient(
        clinic=clinic,
    )

    ward, bed = _create_bed(
        clinic,
        name="Reservation Ward",
        bed_number="B-001",
    )

    audit = Mock()

    monkeypatch.setattr(
        ward_service,
        "create_audit_log",
        audit,
    )

    expires_at = _future_datetime()

    reservation = ward_service.reserve_bed(
        patient_id=patient.id,
        bed_id=bed.id,
        reserved_by_id=actor.id,
        clinic_id=clinic.id,
        reason="  Expected admission  ",
        expires_at=expires_at,
        actor_user_id=actor.user_id,
    )

    assert reservation.id is not None
    assert reservation.patient_id == patient.id
    assert reservation.bed_id == bed.id
    assert reservation.reserved_by_id == actor.id
    assert reservation.status == ReservationStatus.PENDING
    assert reservation.reason == "Expected admission"
    assert reservation.expires_at is not None
    assert reservation.expires_at.tzinfo is None
    assert bed.status == BedStatus.RESERVED
    assert reservation.reserved_at.tzinfo is None

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == AuditAction.CREATE
    assert kwargs["entity_type"] == "bed_reservation"
    assert kwargs["entity_id"] == reservation.id
    assert kwargs["user_id"] == actor.user_id


def test_reserve_bed_defaults_actor_to_reserved_by_user(
    clinic,
    make_patient,
    make_staff,
):
    actor = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    patient = make_patient(
        clinic=clinic,
    )

    _, bed = _create_bed(clinic)

    reservation = ward_service.reserve_bed(
        patient_id=patient.id,
        bed_id=bed.id,
        reserved_by_id=actor.id,
        clinic_id=clinic.id,
    )

    assert reservation.status == ReservationStatus.PENDING


def test_reserve_bed_rejects_expired_expiration(
    clinic,
    make_patient,
    make_staff,
):
    actor = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    patient = make_patient(
        clinic=clinic,
    )

    _, bed = _create_bed(clinic)

    with pytest.raises(
        ValidationError,
        match="expires_at must be in the future",
    ):
        ward_service.reserve_bed(
            patient_id=patient.id,
            bed_id=bed.id,
            reserved_by_id=actor.id,
            clinic_id=clinic.id,
            expires_at=_naive_utc_now() - timedelta(
                minutes=1
            ),
            actor_user_id=actor.user_id,
        )


def test_reserve_bed_rejects_patient_with_active_admission(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        _,
        patient,
        actor,
        _,
    ) = _create_admission(
        clinic,
        make_patient,
        make_staff,
    )

    _, bed = _create_bed(
        clinic,
        name="Second Ward",
        bed_number="B-002",
    )

    with pytest.raises(
        ConflictError,
        match="active admission",
    ):
        ward_service.reserve_bed(
            patient_id=patient.id,
            bed_id=bed.id,
            reserved_by_id=actor.id,
            clinic_id=clinic.id,
            actor_user_id=actor.user_id,
        )


def test_reserve_bed_rejects_existing_patient_reservation(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        _,
        patient,
        actor,
        _,
    ) = _create_reservation(
        clinic,
        make_patient,
        make_staff,
    )

    _, bed = _create_bed(
        clinic,
        name="Second Ward",
        bed_number="B-002",
    )

    with pytest.raises(
        ConflictError,
        match="active bed reservation",
    ):
        ward_service.reserve_bed(
            patient_id=patient.id,
            bed_id=bed.id,
            reserved_by_id=actor.id,
            clinic_id=clinic.id,
            actor_user_id=actor.user_id,
        )


def test_reserve_bed_rejects_existing_bed_reservation(
    clinic,
    make_patient,
    make_staff,
):
    actor = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    patient_a = make_patient(
        clinic=clinic,
    )

    patient_b = make_patient(
        clinic=clinic,
    )

    _, bed = _create_bed(clinic)

    ward_service.reserve_bed(
        patient_id=patient_a.id,
        bed_id=bed.id,
        reserved_by_id=actor.id,
        clinic_id=clinic.id,
        actor_user_id=actor.user_id,
    )

    with pytest.raises(
        ConflictError,
        match="active reservation",
    ):
        ward_service.reserve_bed(
            patient_id=patient_b.id,
            bed_id=bed.id,
            reserved_by_id=actor.id,
            clinic_id=clinic.id,
            actor_user_id=actor.user_id,
        )


def test_reserve_bed_rejects_actor_mismatch(
    clinic,
    make_patient,
    make_staff,
):
    actor_staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    other_staff = make_staff(
        clinic=clinic,
        role=Role.NURSE,
    )

    patient = make_patient(
        clinic=clinic,
    )

    _, bed = _create_bed(clinic)

    with pytest.raises(
        ConflictError,
        match="actor does not match",
    ):
        ward_service.reserve_bed(
            patient_id=patient.id,
            bed_id=bed.id,
            reserved_by_id=actor_staff.id,
            clinic_id=clinic.id,
            actor_user_id=other_staff.user_id,
        )


def test_reserve_bed_rejects_inactive_staff(
    clinic,
    make_patient,
    make_staff,
):
    inactive = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
        status=StaffStatus.SUSPENDED,
    )

    patient = make_patient(
        clinic=clinic,
    )

    _, bed = _create_bed(clinic)

    with pytest.raises(
        ConflictError,
        match="not active",
    ):
        ward_service.reserve_bed(
            patient_id=patient.id,
            bed_id=bed.id,
            reserved_by_id=inactive.id,
            clinic_id=clinic.id,
            actor_user_id=inactive.user_id,
        )


def test_reserve_bed_rejects_maintenance_bed(
    clinic,
    make_patient,
    make_staff,
):
    actor = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    patient = make_patient(
        clinic=clinic,
    )

    _, bed = _create_bed(clinic)

    ward_service.set_bed_maintenance(
        bed.id,
        True,
        clinic.id,
    )

    with pytest.raises(
        ConflictError,
        match="not available",
    ):
        ward_service.reserve_bed(
            patient_id=patient.id,
            bed_id=bed.id,
            reserved_by_id=actor.id,
            clinic_id=clinic.id,
            actor_user_id=actor.user_id,
        )


def test_cancel_bed_reservation_success(
    clinic,
    make_patient,
    make_staff,
    monkeypatch,
):
    (
        _,
        bed,
        _,
        actor,
        reservation,
    ) = _create_reservation(
        clinic,
        make_patient,
        make_staff,
    )

    audit = Mock()

    monkeypatch.setattr(
        ward_service,
        "create_audit_log",
        audit,
    )

    result = ward_service.cancel_bed_reservation(
        reservation_id=reservation.id,
        clinic_id=clinic.id,
        reason="  Patient no longer requires bed  ",
        actor_user_id=actor.user_id,
    )

    assert result.status == ReservationStatus.CANCELLED
    assert result.cancelled_at is not None
    assert result.cancelled_at.tzinfo is None
    assert result.reason == (
        "Patient no longer requires bed"
    )
    assert bed.status == BedStatus.AVAILABLE

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == AuditAction.UPDATE
    assert kwargs["entity_type"] == "bed_reservation"
    assert kwargs["entity_id"] == reservation.id


def test_cancel_bed_reservation_rejects_non_pending(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        _,
        _,
        actor,
        reservation,
    ) = _create_reservation(
        clinic,
        make_patient,
        make_staff,
    )

    ward_service.cancel_bed_reservation(
        reservation.id,
        clinic.id,
        actor_user_id=actor.user_id,
    )

    with pytest.raises(
        ConflictError,
        match="currently",
    ):
        ward_service.cancel_bed_reservation(
            reservation.id,
            clinic.id,
            actor_user_id=actor.user_id,
        )


def test_cancel_bed_reservation_enforces_clinic(
    clinic,
    make_clinic,
    make_patient,
    make_staff,
):
    other_clinic = make_clinic()

    (
        _,
        _,
        _,
        actor,
        reservation,
    ) = _create_reservation(
        other_clinic,
        make_patient,
        make_staff,
    )

    with pytest.raises(NotFoundError):
        ward_service.cancel_bed_reservation(
            reservation.id,
            clinic.id,
            actor_user_id=actor.user_id,
        )


def test_expire_bed_reservation_expires_due_reservation(
    clinic,
    make_patient,
    make_staff,
    monkeypatch,
):
    (
        _,
        bed,
        _,
        _,
        reservation,
    ) = _create_reservation(
        clinic,
        make_patient,
        make_staff,
        expires_at=_future_expiry(30),
    )

    expired_now = (
        reservation.expires_at
        + timedelta(minutes=1)
    )

    monkeypatch.setattr(
        ward_service,
        "_db_now",
        lambda: expired_now,
    )

    audit = Mock()

    monkeypatch.setattr(
        ward_service,
        "create_audit_log",
        audit,
    )

    result = ward_service.expire_bed_reservation(
        reservation.id,
    )

    assert result.status == ReservationStatus.EXPIRED
    assert bed.status == BedStatus.AVAILABLE

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == AuditAction.UPDATE
    assert kwargs["entity_type"] == "bed_reservation"
    assert kwargs["entity_id"] == reservation.id


def test_expire_bed_reservation_does_nothing_before_expiry(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        bed,
        _,
        _,
        reservation,
    ) = _create_reservation(
        clinic,
        make_patient,
        make_staff,
        expires_at=_future_expiry(30),
    )

    result = ward_service.expire_bed_reservation(
        reservation.id,
    )

    assert result.status == ReservationStatus.PENDING
    assert bed.status == BedStatus.RESERVED


def test_expire_bed_reservation_does_nothing_without_expiry(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        bed,
        _,
        _,
        reservation,
    ) = _create_reservation(
        clinic,
        make_patient,
        make_staff,
        expires_at=None,
    )

    result = ward_service.expire_bed_reservation(
        reservation.id,
    )

    assert result.status == ReservationStatus.PENDING
    assert bed.status == BedStatus.RESERVED


def test_expire_bed_reservation_returns_non_pending_unchanged(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        bed,
        _,
        actor,
        reservation,
    ) = _create_reservation(
        clinic,
        make_patient,
        make_staff,
    )

    ward_service.cancel_bed_reservation(
        reservation.id,
        clinic.id,
        actor_user_id=actor.user_id,
    )

    result = ward_service.expire_bed_reservation(
        reservation.id,
    )

    assert result.status == ReservationStatus.CANCELLED
    assert bed.status == BedStatus.AVAILABLE


def test_expire_due_bed_reservations_expires_due_records(
    clinic,
    make_patient,
    make_staff,
    monkeypatch,
):
    actor = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    patient = make_patient(
        clinic=clinic,
    )

    _, bed = _create_bed(clinic)

    reservation = ward_service.reserve_bed(
        patient_id=patient.id,
        bed_id=bed.id,
        reserved_by_id=actor.id,
        clinic_id=clinic.id,
        expires_at=_future_expiry(30),
        actor_user_id=actor.user_id,
    )

    expired_now = (
        reservation.expires_at
        + timedelta(minutes=1)
    )

    monkeypatch.setattr(
        ward_service,
        "_db_now",
        lambda: expired_now,
    )

    audit = Mock()

    monkeypatch.setattr(
        ward_service,
        "create_audit_log",
        audit,
    )

    results = ward_service.expire_due_bed_reservations(
        clinic_id=clinic.id,
    )

    assert reservation.id in {
        item.id for item in results
    }

    assert reservation.status == (
        ReservationStatus.EXPIRED
    )

    assert bed.status == (
        BedStatus.AVAILABLE
    )

    assert audit.called


def test_expire_due_bed_reservations_can_scan_all_clinics(
    clinic,
    make_clinic,
    make_patient,
    make_staff,
    monkeypatch,
):
    other_clinic = make_clinic()

    (
        _,
        foreign_bed,
        _,
        _,
        foreign_reservation,
    ) = _create_reservation(
        other_clinic,
        make_patient,
        make_staff,
        expires_at=_future_expiry(30),
    )

    expired_now = (
        foreign_reservation.expires_at
        + timedelta(minutes=1)
    )

    monkeypatch.setattr(
        ward_service,
        "_db_now",
        lambda: expired_now,
    )

    results = ward_service.expire_due_bed_reservations()

    ids = {
        item.id
        for item in results
    }

    assert foreign_reservation.id in ids
    assert foreign_reservation.status == (
        ReservationStatus.EXPIRED
    )
    assert foreign_bed.status == (
        BedStatus.AVAILABLE
    )


# ============================================================================
# ADMISSION LOOKUPS
# ============================================================================


def test_get_admission_returns_clinic_owned_admission(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        _,
        _,
        _,
        admission,
    ) = _create_admission(
        clinic,
        make_patient,
        make_staff,
    )

    result = ward_service.get_admission(
        admission.id,
        clinic.id,
    )

    assert result.id == admission.id


def test_get_admission_enforces_clinic_isolation(
    clinic,
    make_clinic,
    make_patient,
    make_staff,
):
    other_clinic = make_clinic()

    (
        _,
        _,
        _,
        _,
        admission,
    ) = _create_admission(
        other_clinic,
        make_patient,
        make_staff,
    )

    with pytest.raises(NotFoundError):
        ward_service.get_admission(
            admission.id,
            clinic.id,
        )


def test_get_active_admission_for_patient_returns_active_admission(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        _,
        patient,
        _,
        admission,
    ) = _create_admission(
        clinic,
        make_patient,
        make_staff,
    )

    result = (
        ward_service
        .get_active_admission_for_patient(
            patient.id,
            clinic.id,
        )
    )

    assert result.id == admission.id


def test_get_current_bed_returns_admitted_bed(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        bed,
        patient,
        _,
        _,
    ) = _create_admission(
        clinic,
        make_patient,
        make_staff,
    )

    result = ward_service.get_current_bed(
        patient.id,
        clinic.id,
    )

    assert result.id == bed.id


def test_get_current_bed_returns_none_without_active_admission(
    clinic,
    make_patient,
):
    patient = make_patient(
        clinic=clinic,
    )

    result = ward_service.get_current_bed(
        patient.id,
        clinic.id,
    )

    assert result is None


def test_list_admissions_for_patient_returns_patient_history(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        _,
        patient,
        actor,
        first,
    ) = _create_admission(
        clinic,
        make_patient,
        make_staff,
        bed_number="B-001",
    )

    ward_service.discharge_patient(
        first.id,
        clinic.id,
        actor_user_id=actor.user_id,
    )

    _, bed2 = _create_bed(
        clinic,
        name="Second Admission Ward",
        bed_number="B-002",
    )

    second = ward_service.admit_patient(
        patient_id=patient.id,
        bed_id=bed2.id,
        admitted_by_id=actor.id,
        clinic_id=clinic.id,
        actor_user_id=actor.user_id,
    )

    results = ward_service.list_admissions_for_patient(
        patient.id,
        clinic.id,
    )

    ids = {item.id for item in results}

    assert first.id in ids
    assert second.id in ids


# ============================================================================
# ADMIT PATIENT
# ============================================================================


def test_admit_patient_success(
    clinic,
    make_patient,
    make_staff,
    monkeypatch,
):
    actor = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    patient = make_patient(
        clinic=clinic,
    )

    ward, bed = _create_bed(
        clinic,
        name="Admission Ward",
        bed_number="B-001",
    )

    audit = Mock()

    monkeypatch.setattr(
        ward_service,
        "create_audit_log",
        audit,
    )

    admission = ward_service.admit_patient(
        patient_id=patient.id,
        bed_id=bed.id,
        admitted_by_id=actor.id,
        clinic_id=clinic.id,
        reason="  Observation  ",
        actor_user_id=actor.user_id,
    )

    assert admission.id is not None
    assert admission.patient_id == patient.id
    assert admission.bed_id == bed.id
    assert admission.admitted_by_id == actor.id
    assert admission.status == AdmissionStatus.ADMITTED
    assert admission.reason == "Observation"
    assert admission.admitted_at.tzinfo is None
    assert bed.status == BedStatus.OCCUPIED

    assert audit.call_count == 1

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == AuditAction.CREATE
    assert kwargs["entity_type"] == "admission"
    assert kwargs["entity_id"] == admission.id
    assert kwargs["user_id"] == actor.user_id


def test_admit_patient_rejects_existing_active_admission(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        _,
        patient,
        actor,
        _,
    ) = _create_admission(
        clinic,
        make_patient,
        make_staff,
    )

    _, second_bed = _create_bed(
        clinic,
        name="Second Admission Ward",
        bed_number="B-002",
    )

    with pytest.raises(
        ConflictError,
        match="active admission",
    ):
        ward_service.admit_patient(
            patient_id=patient.id,
            bed_id=second_bed.id,
            admitted_by_id=actor.id,
            clinic_id=clinic.id,
            actor_user_id=actor.user_id,
        )


def test_admit_patient_rejects_active_reservation(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        reserved_bed,
        patient,
        actor,
        _,
    ) = _create_reservation(
        clinic,
        make_patient,
        make_staff,
    )

    with pytest.raises(
        ConflictError,
        match="active reservation",
    ):
        ward_service.admit_patient(
            patient_id=patient.id,
            bed_id=reserved_bed.id,
            admitted_by_id=actor.id,
            clinic_id=clinic.id,
            actor_user_id=actor.user_id,
        )


def test_admit_patient_rejects_occupied_bed(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        occupied_bed,
        _,
        actor,
        _,
    ) = _create_admission(
        clinic,
        make_patient,
        make_staff,
    )

    patient_b = make_patient(
        clinic=clinic,
    )

    with pytest.raises(
        ConflictError,
        match="not available",
    ):
        ward_service.admit_patient(
            patient_id=patient_b.id,
            bed_id=occupied_bed.id,
            admitted_by_id=actor.id,
            clinic_id=clinic.id,
            actor_user_id=actor.user_id,
        )


def test_admit_patient_rejects_actor_mismatch(
    clinic,
    make_patient,
    make_staff,
):
    actor = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    different_user_staff = make_staff(
        clinic=clinic,
        role=Role.NURSE,
    )

    patient = make_patient(
        clinic=clinic,
    )

    _, bed = _create_bed(clinic)

    with pytest.raises(
        ConflictError,
        match="actor does not match",
    ):
        ward_service.admit_patient(
            patient_id=patient.id,
            bed_id=bed.id,
            admitted_by_id=actor.id,
            clinic_id=clinic.id,
            actor_user_id=(
                different_user_staff.user_id
            ),
        )


def test_admit_patient_rejects_inactive_admitting_staff(
    clinic,
    make_patient,
    make_staff,
):
    inactive = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
        status=StaffStatus.SUSPENDED,
    )

    patient = make_patient(
        clinic=clinic,
    )

    _, bed = _create_bed(clinic)

    with pytest.raises(
        ConflictError,
        match="not active",
    ):
        ward_service.admit_patient(
            patient_id=patient.id,
            bed_id=bed.id,
            admitted_by_id=inactive.id,
            clinic_id=clinic.id,
            actor_user_id=inactive.user_id,
        )


# ============================================================================
# ADMISSION FROM RESERVATION
# ============================================================================


def test_admit_patient_from_reservation_success(
    clinic,
    make_patient,
    make_staff,
    monkeypatch,
):
    (
        _,
        bed,
        patient,
        actor,
        reservation,
    ) = _create_reservation(
        clinic,
        make_patient,
        make_staff,
        expires_at=_future_datetime(30),
        reason="Reserved admission",
    )

    audit = Mock()

    monkeypatch.setattr(
        ward_service,
        "create_audit_log",
        audit,
    )

    admission = (
        ward_service
        .admit_patient_from_reservation(
            reservation_id=reservation.id,
            admitted_by_id=actor.id,
            clinic_id=clinic.id,
            actor_user_id=actor.user_id,
            reason="  Final admission  ",
        )
    )

    assert admission.patient_id == patient.id
    assert admission.bed_id == bed.id
    assert admission.reservation_id == reservation.id
    assert admission.status == AdmissionStatus.ADMITTED
    assert admission.reason == "Final admission"

    assert reservation.status == (
        ReservationStatus.FULFILLED
    )
    assert reservation.fulfilled_at is not None
    assert reservation.fulfilled_at.tzinfo is None

    assert bed.status == BedStatus.OCCUPIED

    assert audit.call_count == 2

    actions = [
        call.kwargs["action"]
        for call in audit.call_args_list
    ]

    assert actions == [
        AuditAction.CREATE,
        AuditAction.UPDATE,
    ]


def test_admit_patient_from_reservation_uses_reservation_reason(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        _,
        _,
        actor,
        reservation,
    ) = _create_reservation(
        clinic,
        make_patient,
        make_staff,
        reason="Reservation reason",
        expires_at=_future_datetime(),
    )

    admission = (
        ward_service
        .admit_patient_from_reservation(
            reservation_id=reservation.id,
            admitted_by_id=actor.id,
            clinic_id=clinic.id,
            actor_user_id=actor.user_id,
        )
    )

    assert admission.reason == "Reservation reason"


def test_admit_patient_from_reservation_rejects_expired_reservation(
    clinic,
    make_patient,
    make_staff,
    monkeypatch,
):
    (
        _,
        _,
        _,
        actor,
        reservation,
    ) = _create_reservation(
        clinic,
        make_patient,
        make_staff,
        expires_at=_future_expiry(30),
    )

    expired_now = (
        reservation.expires_at
        + timedelta(minutes=1)
    )

    monkeypatch.setattr(
        ward_service,
        "_db_now",
        lambda: expired_now,
    )

    with pytest.raises(
        ConflictError,
        match="expired",
    ):
        ward_service.admit_patient_from_reservation(
            reservation_id=reservation.id,
            admitted_by_id=actor.id,
            clinic_id=clinic.id,
            actor_user_id=actor.user_id,
        )


def test_admit_patient_from_reservation_rejects_cancelled_reservation(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        _,
        _,
        actor,
        reservation,
    ) = _create_reservation(
        clinic,
        make_patient,
        make_staff,
    )

    ward_service.cancel_bed_reservation(
        reservation.id,
        clinic.id,
        actor_user_id=actor.user_id,
    )

    with pytest.raises(
        ConflictError,
        match="currently",
    ):
        ward_service.admit_patient_from_reservation(
            reservation.id,
            actor.id,
            clinic.id,
            actor_user_id=actor.user_id,
        )


def test_admit_patient_from_reservation_rejects_actor_mismatch(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        _,
        _,
        actor,
        reservation,
    ) = _create_reservation(
        clinic,
        make_patient,
        make_staff,
    )

    other_staff = make_staff(
        clinic=clinic,
        role=Role.NURSE,
    )

    with pytest.raises(
        ConflictError,
        match="actor does not match",
    ):
        ward_service.admit_patient_from_reservation(
            reservation_id=reservation.id,
            admitted_by_id=actor.id,
            clinic_id=clinic.id,
            actor_user_id=other_staff.user_id,
        )


def test_fulfill_bed_reservation_alias_matches_admission_function():
    assert (
        ward_service.fulfill_bed_reservation
        is ward_service.admit_patient_from_reservation
    )


# ============================================================================
# TRANSFER
# ============================================================================


def test_transfer_bed_success(
    clinic,
    make_patient,
    make_staff,
    monkeypatch,
):
    (
        _,
        source_bed,
        _,
        actor,
        admission,
    ) = _create_admission(
        clinic,
        make_patient,
        make_staff,
        bed_number="B-001",
    )

    _, destination_bed = _create_bed(
        clinic,
        name="Transfer Ward",
        bed_number="B-002",
    )

    audit = Mock()

    monkeypatch.setattr(
        ward_service,
        "create_audit_log",
        audit,
    )

    transfer = ward_service.transfer_bed(
        admission_id=admission.id,
        to_bed_id=destination_bed.id,
        clinic_id=clinic.id,
        reason="  Clinical transfer  ",
        actor_user_id=actor.user_id,
    )

    assert transfer.id is not None
    assert transfer.admission_id == admission.id
    assert transfer.from_bed_id == source_bed.id
    assert transfer.to_bed_id == destination_bed.id
    assert transfer.reason == "Clinical transfer"
    assert transfer.transferred_at.tzinfo is None

    assert source_bed.status == BedStatus.AVAILABLE
    assert destination_bed.status == BedStatus.OCCUPIED
    assert admission.bed_id == destination_bed.id

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == AuditAction.UPDATE
    assert kwargs["entity_type"] == "admission"
    assert kwargs["entity_id"] == admission.id
    assert kwargs["old_value"]["bed_id"] == source_bed.id
    assert kwargs["new_value"]["bed_id"] == destination_bed.id


def test_transfer_bed_rejects_same_source_and_destination(
    clinic,
    make_patient,
    make_staff,
):
    _, bed, _, _, admission = _create_admission(
        clinic,
        make_patient,
        make_staff,
    )

    with pytest.raises(
        ValidationError,
        match="must be different",
    ):
        ward_service.transfer_bed(
            admission_id=admission.id,
            to_bed_id=bed.id,
            clinic_id=clinic.id,
        )


def test_transfer_bed_rejects_non_active_admission(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        _,
        _,
        actor,
        admission,
    ) = _create_admission(
        clinic,
        make_patient,
        make_staff,
    )

    ward_service.discharge_patient(
        admission.id,
        clinic.id,
        actor_user_id=actor.user_id,
    )

    _, destination = _create_bed(
        clinic,
        name="Destination Ward",
        bed_number="B-002",
    )

    with pytest.raises(
        ConflictError,
        match="currently",
    ):
        ward_service.transfer_bed(
            admission.id,
            destination.id,
            clinic.id,
        )


def test_transfer_bed_rejects_unavailable_destination(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        source_bed,
        _,
        actor,
        admission,
    ) = _create_admission(
        clinic,
        make_patient,
        make_staff,
    )

    patient_two = make_patient(
        clinic=clinic,
    )

    _, occupied_destination = _create_bed(
        clinic,
        name="Occupied Ward",
        bed_number="B-002",
    )

    ward_service.admit_patient(
        patient_id=patient_two.id,
        bed_id=occupied_destination.id,
        admitted_by_id=actor.id,
        clinic_id=clinic.id,
        actor_user_id=actor.user_id,
    )

    with pytest.raises(
        ConflictError,
        match="not available",
    ):
        ward_service.transfer_bed(
            admission.id,
            occupied_destination.id,
            clinic.id,
            actor_user_id=actor.user_id,
        )

    assert source_bed.status == (
        BedStatus.OCCUPIED
    )


def test_transfer_bed_rejects_foreign_destination(
    clinic,
    make_clinic,
    make_patient,
    make_staff,
):
    other_clinic = make_clinic()

    (
        _,
        _,
        _,
        actor,
        admission,
    ) = _create_admission(
        clinic,
        make_patient,
        make_staff,
    )

    _, foreign_bed = _create_bed(
        other_clinic,
        name="Foreign Ward",
        bed_number="B-001",
    )

    with pytest.raises(NotFoundError):
        ward_service.transfer_bed(
            admission.id,
            foreign_bed.id,
            clinic.id,
            actor_user_id=actor.user_id,
        )


# ============================================================================
# DISCHARGE
# ============================================================================


def test_discharge_patient_success(
    clinic,
    make_patient,
    make_staff,
    monkeypatch,
):
    (
        _,
        bed,
        _,
        actor,
        admission,
    ) = _create_admission(
        clinic,
        make_patient,
        make_staff,
    )

    audit = Mock()

    monkeypatch.setattr(
        ward_service,
        "create_audit_log",
        audit,
    )

    result = ward_service.discharge_patient(
        admission_id=admission.id,
        clinic_id=clinic.id,
        reason="  Patient recovered  ",
        actor_user_id=actor.user_id,
    )

    assert result.id == admission.id
    assert result.status == AdmissionStatus.DISCHARGED
    assert result.discharged_at is not None
    assert result.discharged_at.tzinfo is None
    assert result.reason == "Patient recovered"
    assert bed.status == BedStatus.AVAILABLE

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == AuditAction.UPDATE
    assert kwargs["entity_type"] == "admission"
    assert kwargs["entity_id"] == admission.id
    assert kwargs["user_id"] == actor.user_id
    assert kwargs["new_value"]["status"] == (
        AdmissionStatus.DISCHARGED.value
    )


def test_discharge_patient_allows_no_reason(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        bed,
        _,
        actor,
        admission,
    ) = _create_admission(
        clinic,
        make_patient,
        make_staff,
        reason="Original reason",
    )

    result = ward_service.discharge_patient(
        admission.id,
        clinic.id,
        actor_user_id=actor.user_id,
    )

    assert result.status == (
        AdmissionStatus.DISCHARGED
    )
    assert result.reason == "Original reason"
    assert bed.status == BedStatus.AVAILABLE


def test_discharge_patient_rejects_already_discharged(
    clinic,
    make_patient,
    make_staff,
):
    (
        _,
        _,
        _,
        actor,
        admission,
    ) = _create_admission(
        clinic,
        make_patient,
        make_staff,
    )

    ward_service.discharge_patient(
        admission.id,
        clinic.id,
        actor_user_id=actor.user_id,
    )

    with pytest.raises(
        ConflictError,
        match="currently",
    ):
        ward_service.discharge_patient(
            admission.id,
            clinic.id,
            actor_user_id=actor.user_id,
        )


def test_discharge_patient_rejects_foreign_admission(
    clinic,
    make_clinic,
    make_patient,
    make_staff,
):
    other_clinic = make_clinic()

    (
        _,
        _,
        _,
        actor,
        admission,
    ) = _create_admission(
        other_clinic,
        make_patient,
        make_staff,
    )

    with pytest.raises(NotFoundError):
        ward_service.discharge_patient(
            admission.id,
            clinic.id,
            actor_user_id=actor.user_id,
        )


# ============================================================================
# CROSS-CUTTING CLINIC ENFORCEMENT
# ============================================================================


def test_list_wards_rejects_invalid_clinic_id():
    with pytest.raises(
        ValidationError,
        match="clinic_id",
    ):
        ward_service.list_wards(0)


def test_get_ward_occupancy_rejects_invalid_clinic_id():
    with pytest.raises(
        ValidationError,
        match="clinic_id",
    ):
        ward_service.get_ward_occupancy(
            1,
            0,
        )


def test_active_clinic_required_for_reservation(
    suspended_clinic,
):
    with pytest.raises(
        ValidationError,
        match="not active",
    ):
        ward_service.reserve_bed(
            patient_id=1,
            bed_id=1,
            reserved_by_id=1,
            clinic_id=suspended_clinic.id,
        )


def test_active_clinic_required_for_admission(
    suspended_clinic,
):
    with pytest.raises(
        ValidationError,
        match="not active",
    ):
        ward_service.admit_patient(
            patient_id=1,
            bed_id=1,
            admitted_by_id=1,
            clinic_id=suspended_clinic.id,
        )


def test_active_clinic_required_for_transfer(
    suspended_clinic,
):
    with pytest.raises(
        ValidationError,
        match="not active",
    ):
        ward_service.transfer_bed(
            admission_id=1,
            to_bed_id=2,
            clinic_id=suspended_clinic.id,
        )


def test_active_clinic_required_for_discharge(
    suspended_clinic,
):
    with pytest.raises(
        ValidationError,
        match="not active",
    ):
        ward_service.discharge_patient(
            admission_id=1,
            clinic_id=suspended_clinic.id,
        )