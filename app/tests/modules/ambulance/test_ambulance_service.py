from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.enums.ambulance_enums import (
    EquipmentLevel,
    TripStatus,
    TripType,
    VehicleStatus,
)
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.ambulance.services import ambulance_service
from app.tests.modules.ward.test_ward_service import _create_admission


# Helpers


def make_user(
    *,
    user_id=1,
    clinic_id=1,
    role=Role.ADMIN,
    is_active=True,
):
    return SimpleNamespace(
        id=user_id,
        clinic_id=clinic_id,
        role=role,
        is_active=is_active,
    )


def make_patient(
    *,
    patient_id=1,
    clinic_id=1,
    is_active=True,
):
    return SimpleNamespace(
        id=patient_id,
        clinic_id=clinic_id,
        is_active=is_active,
    )


def make_vehicle(
    *,
    vehicle_id=1,
    clinic_id=1,
    plate_number="AMB-001",
    equipment_level=EquipmentLevel.BLS,
    capacity=4,
    status=VehicleStatus.AVAILABLE,
):
    return SimpleNamespace(
        id=vehicle_id,
        clinic_id=clinic_id,
        plate_number=plate_number,
        equipment_level=equipment_level,
        capacity=capacity,
        status=status,
    )


def make_staff(
    *,
    staff_id=1,
    clinic_id=1,
    role=Role.DRIVER,
    status=StaffStatus.ACTIVE,
    user=None,
):
    if user is None:
        user = make_user(
            user_id=staff_id,
            clinic_id=clinic_id,
            role=role,
        )

    return SimpleNamespace(
        id=staff_id,
        clinic_id=clinic_id,
        status=status,
        user=user,
    )


def make_admission(
    *,
    admission_id=1,
    patient=None,
):
    if patient is None:
        patient = make_patient()

    return SimpleNamespace(
        id=admission_id,
        patient_id=patient.id,
        patient=patient,
    )


def make_invoice(
    *,
    invoice_id=1,
    clinic_id=1,
    patient_id=1,
    ambulance_trip=None,
):
    return SimpleNamespace(
        id=invoice_id,
        clinic_id=clinic_id,
        patient_id=patient_id,
        ambulance_trip=ambulance_trip,
    )


def make_trip(
    *,
    trip_id=1,
    clinic_id=1,
    status=TripStatus.REQUESTED,
    patient=None,
    admission=None,
    vehicle=None,
    driver=None,
    paramedic=None,
    invoice=None,
):
    return SimpleNamespace(
        id=trip_id,
        clinic_id=clinic_id,
        trip_type=TripType.EMERGENCY_PICKUP,
        status=status,
        patient=patient,
        patient_id=patient.id if patient else None,
        admission=admission,
        admission_id=admission.id if admission else None,
        vehicle=vehicle,
        vehicle_id=vehicle.id if vehicle else None,
        driver=driver,
        driver_id=driver.id if driver else None,
        paramedic=paramedic,
        paramedic_id=paramedic.id if paramedic else None,
        invoice=invoice,
        invoice_id=invoice.id if invoice else None,
        pickup_address=None,
        pickup_lat=None,
        pickup_lng=None,
        destination_address=None,
        destination_lat=None,
        destination_lng=None,
        notes=None,
        dispatched_at=None,
        pickup_at=None,
        completed_at=None,
        cancelled_at=None,
        cancellation_reason=None,
    )


def install_locked_trip(monkeypatch, trip):
    monkeypatch.setattr(
        ambulance_service,
        "_lock_trip",
        Mock(return_value=trip),
    )


def install_query_chain(query):
    query.filter_by.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.with_for_update.return_value = query
    return query


def install_fake_trip_model(monkeypatch):
    def fake_trip(**kwargs):
        trip = SimpleNamespace(**kwargs)
        trip.id = getattr(trip, "id", 1) or 1

        if not hasattr(trip, "patient"):
            trip.patient = None
        if not hasattr(trip, "patient_id"):
            trip.patient_id = (
                trip.patient.id
                if trip.patient is not None
                else None
            )

        if not hasattr(trip, "admission"):
            trip.admission = None
        if not hasattr(trip, "admission_id"):
            trip.admission_id = (
                trip.admission.id
                if trip.admission is not None
                else None
            )

        return trip

    monkeypatch.setattr(
        ambulance_service,
        "AmbulanceTrip",
        fake_trip,
    )
    monkeypatch.setattr(
        ambulance_service.db.session,
        "add",
        Mock(),
    )
    monkeypatch.setattr(
        ambulance_service.db.session,
        "flush",
        Mock(),
    )


@pytest.fixture
def request_context(app, user):
    with app.test_request_context():
        from flask import g

        g.current_user_id = user.id
        yield


@pytest.fixture
def audit_mock(monkeypatch):
    mock = Mock()
    monkeypatch.setattr(
        ambulance_service,
        "create_audit_log",
        mock,
    )
    return mock


@pytest.fixture
def clinic_active_mock(monkeypatch):
    mock = Mock()
    monkeypatch.setattr(
        ambulance_service,
        "ensure_clinic_active",
        mock,
    )
    return mock


# Validation helpers


@pytest.mark.parametrize(
    "value",
    [True, False, 0, -1, 1.5, "1", None],
)
def test_validate_positive_id_rejects_invalid(value):
    with pytest.raises(ValidationError):
        ambulance_service._validate_positive_id(
            value,
            "Vehicle ID",
        )


def test_validate_positive_id_accepts_positive_integer():
    ambulance_service._validate_positive_id(1, "Vehicle ID")


@pytest.mark.parametrize(
    "page,per_page",
    [
        (0, 50),
        (-1, 50),
        (True, 50),
        (1, 0),
        (1, -1),
        (1, True),
        (1, 501),
    ],
)
def test_validate_pagination_rejects_invalid(page, per_page):
    with pytest.raises(ValidationError):
        ambulance_service._validate_pagination(
            page,
            per_page,
        )


def test_validate_pagination_accepts_valid_values():
    ambulance_service._validate_pagination(1, 50)
    ambulance_service._validate_pagination(2, 500)


def test_normalize_enum_accepts_enum():
    result = ambulance_service._normalize_enum(
        VehicleStatus.AVAILABLE,
        VehicleStatus,
        "vehicle status",
    )

    assert result is VehicleStatus.AVAILABLE


def test_normalize_enum_accepts_value():
    result = ambulance_service._normalize_enum(
        "available",
        VehicleStatus,
        "vehicle status",
    )

    assert result is VehicleStatus.AVAILABLE


def test_normalize_enum_rejects_invalid():
    with pytest.raises(ValidationError, match="Invalid vehicle status"):
        ambulance_service._normalize_enum(
            "invalid",
            VehicleStatus,
            "vehicle status",
        )


# Authentication / clinic helpers


def test_current_user_requires_request_context():
    with pytest.raises(
        ValidationError,
        match="Authenticated request context is required",
    ):
        ambulance_service._current_user()


def test_current_user_requires_positive_identity(app):
    with app.test_request_context():
        from flask import g

        g.current_user_id = 0

        with pytest.raises(
            ValidationError,
            match="Authenticated user is required",
        ):
            ambulance_service._current_user()


def test_current_user_rejects_missing_user(
    app,
    monkeypatch,
):
    with app.test_request_context():
        from flask import g

        g.current_user_id = 1

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=None),
        )

        with pytest.raises(
            ValidationError,
            match="Authenticated user was not found",
        ):
            ambulance_service._current_user()


def test_current_user_rejects_inactive_user(
    app,
    monkeypatch,
):
    user = make_user(is_active=False)

    with app.test_request_context():
        from flask import g

        g.current_user_id = user.id

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=user),
        )

        with pytest.raises(
            ValidationError,
            match="User account is inactive",
        ):
            ambulance_service._current_user()


def test_current_user_returns_active_user(
    app,
    monkeypatch,
):
    user = make_user()

    with app.test_request_context():
        from flask import g

        g.current_user_id = user.id

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=user),
        )

        assert ambulance_service._current_user() is user


def test_current_clinic_requires_clinic():
    user = make_user(clinic_id=None)

    with pytest.raises(
        ValidationError,
        match="not associated with a clinic",
    ):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                ambulance_service,
                "_current_user",
                Mock(return_value=user),
            )
            ambulance_service._current_clinic_id()


def test_authenticated_clinic_rejects_wrong_clinic(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=1)

    with app.test_request_context():
        from flask import g

        g.current_user_id = user.id

        monkeypatch.setattr(
            ambulance_service,
            "_current_user",
            Mock(return_value=user),
        )

        with pytest.raises(
            ValidationError,
            match="does not belong",
        ):
            ambulance_service._assert_authenticated_clinic(2)


def test_authenticated_clinic_allows_same_clinic(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=1)

    with app.test_request_context():
        monkeypatch.setattr(
            ambulance_service,
            "_current_user",
            Mock(return_value=user),
        )

        ambulance_service._assert_authenticated_clinic(1)


# Vehicle lookup / listing


def test_get_vehicle_returns_vehicle(
    app,
    monkeypatch,
):
    vehicle = make_vehicle()

    with app.test_request_context():
        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=vehicle),
        )
        monkeypatch.setattr(
            ambulance_service,
            "_assert_authenticated_clinic",
            Mock(),
        )

        result = ambulance_service.get_vehicle(vehicle.id)

        assert result is vehicle


def test_get_vehicle_not_found(
    app,
    monkeypatch,
):
    with app.test_request_context():
        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=None),
        )

        with pytest.raises(NotFoundError):
            ambulance_service.get_vehicle(1)


def test_get_vehicle_rejects_other_clinic(
    app,
    monkeypatch,
):
    vehicle = make_vehicle(clinic_id=2)

    with app.test_request_context():
        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=vehicle),
        )
        monkeypatch.setattr(
            ambulance_service,
            "_assert_authenticated_clinic",
            Mock(
                side_effect=ValidationError(
                    "Resource does not belong to the authenticated user's clinic"
                )
            ),
        )

        with pytest.raises(ValidationError):
            ambulance_service.get_vehicle(vehicle.id)


def test_list_vehicles_uses_pagination(
    app,
    monkeypatch,
):
    query = install_query_chain(Mock())
    pagination = Mock()
    query.paginate.return_value = pagination

    monkeypatch.setattr(
        ambulance_service.AmbulanceVehicle,
        "query",
        query,
    )
    monkeypatch.setattr(
        ambulance_service,
        "_assert_authenticated_clinic",
        Mock(),
    )

    result = ambulance_service.list_vehicles(
        clinic_id=1,
        page=2,
        per_page=25,
    )

    assert result is pagination
    query.filter_by.assert_called_once_with(
        clinic_id=1,
    )
    query.order_by.assert_called_once()
    query.paginate.assert_called_once_with(
        page=2,
        per_page=25,
        error_out=False,
    )


def test_list_vehicles_filters_status(
    app,
    monkeypatch,
):
    query = install_query_chain(Mock())
    query.paginate.return_value = Mock()

    monkeypatch.setattr(
        ambulance_service.AmbulanceVehicle,
        "query",
        query,
    )
    monkeypatch.setattr(
        ambulance_service,
        "_assert_authenticated_clinic",
        Mock(),
    )

    ambulance_service.list_vehicles(
        clinic_id=1,
        status=VehicleStatus.MAINTENANCE,
    )

    query.filter.assert_called_once()


# Vehicle creation


def test_create_vehicle_creates_with_equipment_level(
    app,
    user,
    monkeypatch,
    audit_mock,
    clinic_active_mock,
):
    with app.test_request_context():
        from flask import g

        g.current_user_id = user.id

        query = Mock()
        query.filter_by.return_value = query
        query.first.return_value = None

        monkeypatch.setattr(
            ambulance_service.AmbulanceVehicle,
            "query",
            query,
        )

        captured = {}

        def fake_add(vehicle):
            captured["vehicle"] = vehicle
            vehicle.id = 1

        monkeypatch.setattr(
            ambulance_service.db.session,
            "add",
            fake_add,
        )
        monkeypatch.setattr(
            ambulance_service.db.session,
            "flush",
            Mock(),
        )

        vehicle = ambulance_service.create_vehicle(
            clinic_id=user.clinic_id,
            plate_number=" amb-001 ",
            equipment_level=EquipmentLevel.ALS,
            capacity=6,
        )

        assert vehicle is captured["vehicle"]
        assert vehicle.plate_number == "AMB-001"
        assert vehicle.equipment_level == EquipmentLevel.ALS
        assert vehicle.capacity == 6
        assert vehicle.status == VehicleStatus.AVAILABLE

        audit_mock.assert_called_once()
        assert (
            audit_mock.call_args.kwargs["action"]
            == AuditAction.CREATE
        )


@pytest.mark.parametrize(
    "equipment_level",
    [
        EquipmentLevel.BLS,
        EquipmentLevel.ALS,
        EquipmentLevel.CCT,
    ],
)
def test_create_vehicle_supports_all_equipment_levels(
    app,
    monkeypatch,
    equipment_level,
    audit_mock,
    clinic_active_mock,
):
    with app.test_request_context():
        query = Mock()
        query.filter_by.return_value = query
        query.first.return_value = None

        monkeypatch.setattr(
            ambulance_service.AmbulanceVehicle,
            "query",
            query,
        )

        vehicle = ambulance_service.AmbulanceVehicle(
            clinic_id=1,
            plate_number="AMB-001",
            equipment_level=equipment_level,
            capacity=4,
            status=VehicleStatus.AVAILABLE,
        )

        assert vehicle.equipment_level == equipment_level


@pytest.mark.parametrize(
    "plate_number",
    ["", "   ", None, 123],
)
def test_create_vehicle_rejects_invalid_plate(
    app,
    user,
    plate_number,
    monkeypatch,
    clinic_active_mock,
):
    with app.test_request_context():
        from flask import g

        g.current_user_id = user.id

        with pytest.raises(ValidationError):
            ambulance_service.create_vehicle(
                clinic_id=user.clinic_id,
                plate_number=plate_number,
                equipment_level=EquipmentLevel.BLS,
            )


def test_create_vehicle_rejects_long_plate(
    app,
    user,
    clinic_active_mock,
):
    with app.test_request_context():
        from flask import g

        g.current_user_id = user.id

        with pytest.raises(ValidationError):
            ambulance_service.create_vehicle(
                clinic_id=user.clinic_id,
                plate_number="A" * 31,
                equipment_level=EquipmentLevel.BLS,
            )


@pytest.mark.parametrize(
    "capacity",
    [0, -1, True, False, 1.5, "4"],
)
def test_create_vehicle_rejects_invalid_capacity(
    app,
    user,
    capacity,
    clinic_active_mock,
):
    with app.test_request_context():
        from flask import g

        g.current_user_id = user.id

        with pytest.raises(ValidationError):
            ambulance_service.create_vehicle(
                clinic_id=user.clinic_id,
                plate_number="AMB-001",
                equipment_level=EquipmentLevel.BLS,
                capacity=capacity,
            )


def test_create_vehicle_rejects_non_available_status(
    app,
    user,
    clinic_active_mock,
):
    with app.test_request_context():
        from flask import g

        g.current_user_id = user.id

        with pytest.raises(
            ValidationError,
            match="must start",
        ):
            ambulance_service.create_vehicle(
                clinic_id=user.clinic_id,
                plate_number="AMB-001",
                equipment_level=EquipmentLevel.BLS,
                status=VehicleStatus.ON_TRIP,
            )


def test_create_vehicle_rejects_duplicate_plate(
    app,
    user,
    monkeypatch,
    clinic_active_mock,
):
    existing = make_vehicle(
        clinic_id=user.clinic_id,
    )

    query = Mock()
    query.filter_by.return_value = query
    query.first.return_value = existing

    monkeypatch.setattr(
        ambulance_service.AmbulanceVehicle,
        "query",
        query,
    )

    with app.test_request_context():
        from flask import g

        g.current_user_id = user.id

        with pytest.raises(ConflictError):
            ambulance_service.create_vehicle(
                clinic_id=user.clinic_id,
                plate_number="AMB-001",
                equipment_level=EquipmentLevel.BLS,
            )


# Vehicle status


def test_set_vehicle_status_updates_status(
    app,
    monkeypatch,
    audit_mock,
    clinic_active_mock,
):
    vehicle = make_vehicle()

    monkeypatch.setattr(
        ambulance_service,
        "get_vehicle",
        Mock(return_value=vehicle),
    )

    with app.test_request_context():
        result = ambulance_service.set_vehicle_status(
            vehicle.id,
            VehicleStatus.MAINTENANCE,
        )

    assert result.status == VehicleStatus.MAINTENANCE
    audit_mock.assert_called_once()


def test_set_vehicle_status_same_status_is_noop(
    app,
    monkeypatch,
    audit_mock,
    clinic_active_mock,
):
    vehicle = make_vehicle()

    monkeypatch.setattr(
        ambulance_service,
        "get_vehicle",
        Mock(return_value=vehicle),
    )

    with app.test_request_context():
        result = ambulance_service.set_vehicle_status(
            vehicle.id,
            VehicleStatus.AVAILABLE,
        )

    assert result is vehicle
    audit_mock.assert_not_called()


def test_set_vehicle_status_rejects_manual_on_trip(
    app,
    monkeypatch,
    clinic_active_mock,
):
    vehicle = make_vehicle(
        status=VehicleStatus.AVAILABLE,
    )

    monkeypatch.setattr(
        ambulance_service,
        "get_vehicle",
        Mock(return_value=vehicle),
    )

    with app.test_request_context():
        with pytest.raises(ValidationError):
            ambulance_service.set_vehicle_status(
                vehicle.id,
                VehicleStatus.ON_TRIP,
            )


def test_set_vehicle_status_rejects_changing_on_trip_vehicle(
    app,
    monkeypatch,
    clinic_active_mock,
):
    vehicle = make_vehicle(
        status=VehicleStatus.ON_TRIP,
    )

    monkeypatch.setattr(
        ambulance_service,
        "get_vehicle",
        Mock(return_value=vehicle),
    )

    with app.test_request_context():
        with pytest.raises(ConflictError):
            ambulance_service.set_vehicle_status(
                vehicle.id,
                VehicleStatus.MAINTENANCE,
            )


# Trip lookup / listing


def test_get_trip_returns_trip(
    app,
    monkeypatch,
):
    trip = make_trip()

    with app.test_request_context():
        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=trip),
        )
        monkeypatch.setattr(
            ambulance_service,
            "_assert_authenticated_clinic",
            Mock(),
        )

        assert ambulance_service.get_trip(1) is trip


def test_get_trip_not_found(
    app,
    monkeypatch,
):
    with app.test_request_context():
        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=None),
        )

        with pytest.raises(NotFoundError):
            ambulance_service.get_trip(1)


def test_list_trips_uses_pagination(
    app,
    monkeypatch,
):
    query = install_query_chain(Mock())
    pagination = Mock()
    query.paginate.return_value = pagination

    monkeypatch.setattr(
        ambulance_service.AmbulanceTrip,
        "query",
        query,
    )
    monkeypatch.setattr(
        ambulance_service,
        "_assert_authenticated_clinic",
        Mock(),
    )

    result = ambulance_service.list_trips(
        clinic_id=1,
        page=3,
        per_page=25,
    )

    assert result is pagination
    query.filter_by.assert_called_once_with(
        clinic_id=1,
    )
    query.paginate.assert_called_once_with(
        page=3,
        per_page=25,
        error_out=False,
    )


def test_list_trips_filters_status(
    app,
    monkeypatch,
):
    query = install_query_chain(Mock())
    query.paginate.return_value = Mock()

    monkeypatch.setattr(
        ambulance_service.AmbulanceTrip,
        "query",
        query,
    )
    monkeypatch.setattr(
        ambulance_service,
        "_assert_authenticated_clinic",
        Mock(),
    )

    ambulance_service.list_trips(
        clinic_id=1,
        status=TripStatus.REQUESTED,
    )

    query.filter.assert_called_once()


# Row locking


def test_lock_trip_uses_row_lock(
    app,
    monkeypatch,
):
    trip = make_trip()

    query = install_query_chain(Mock())
    query.first.return_value = trip

    monkeypatch.setattr(
        ambulance_service.AmbulanceTrip,
        "query",
        query,
    )
    monkeypatch.setattr(
        ambulance_service,
        "_assert_authenticated_clinic",
        Mock(),
    )

    result = ambulance_service._lock_trip(1)

    assert result is trip
    query.filter.assert_called_once()
    query.with_for_update.assert_called_once_with()
    query.first.assert_called_once_with()


def test_lock_trip_not_found(
    app,
    monkeypatch,
):
    query = install_query_chain(Mock())
    query.first.return_value = None

    monkeypatch.setattr(
        ambulance_service.AmbulanceTrip,
        "query",
        query,
    )

    with pytest.raises(NotFoundError):
        ambulance_service._lock_trip(1)


def test_lock_vehicle_uses_row_lock(
    app,
    monkeypatch,
):
    vehicle = make_vehicle()

    query = install_query_chain(Mock())
    query.first.return_value = vehicle

    monkeypatch.setattr(
        ambulance_service.AmbulanceVehicle,
        "query",
        query,
    )

    result = ambulance_service._lock_vehicle(1)

    assert result is vehicle
    query.filter.assert_called_once()
    query.with_for_update.assert_called_once_with()
    query.first.assert_called_once_with()


def test_lock_vehicle_not_found(
    app,
    monkeypatch,
):
    query = install_query_chain(Mock())
    query.first.return_value = None

    monkeypatch.setattr(
        ambulance_service.AmbulanceVehicle,
        "query",
        query,
    )

    with pytest.raises(NotFoundError):
        ambulance_service._lock_vehicle(1)


# Patient / admission / crew helpers


def test_get_patient_returns_active_patient(
    monkeypatch,
):
    patient = make_patient()

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        Mock(return_value=patient),
    )

    assert ambulance_service._get_patient(
        patient.id,
        patient.clinic_id,
    ) is patient


def test_get_patient_not_found(monkeypatch):
    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        Mock(return_value=None),
    )

    with pytest.raises(NotFoundError):
        ambulance_service._get_patient(1, 1)


def test_get_patient_rejects_other_clinic(monkeypatch):
    patient = make_patient(clinic_id=2)

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        Mock(return_value=patient),
    )

    with pytest.raises(ValidationError):
        ambulance_service._get_patient(1, 1)


def test_get_patient_rejects_inactive_patient(monkeypatch):
    patient = make_patient(is_active=False)

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        Mock(return_value=patient),
    )

    with pytest.raises(ValidationError):
        ambulance_service._get_patient(1, 1)


def test_get_admission_returns_admission(monkeypatch):
    admission = make_admission()

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        Mock(return_value=admission),
    )

    assert ambulance_service._get_admission(
        admission.id,
        1,
    ) is admission


def test_get_admission_not_found(monkeypatch):
    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        Mock(return_value=None),
    )

    with pytest.raises(NotFoundError):
        ambulance_service._get_admission(1, 1)


def test_get_crew_member_returns_active_driver(monkeypatch):
    staff = make_staff(role=Role.DRIVER)

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        Mock(return_value=staff),
    )

    result = ambulance_service._get_ambulance_crew_member(
        staff.id,
        1,
        (Role.DRIVER,),
        "driver",
    )

    assert result is staff


def test_get_crew_member_requires_active_staff(monkeypatch):
    staff = make_staff(
        status="inactive",
        role=Role.DRIVER,
    )

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        Mock(return_value=staff),
    )

    with pytest.raises(ValidationError):
        ambulance_service._get_ambulance_crew_member(
            staff.id,
            1,
            (Role.DRIVER,),
            "driver",
        )


def test_get_crew_member_rejects_wrong_role(monkeypatch):
    staff = make_staff(role=Role.ADMIN)

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        Mock(return_value=staff),
    )

    with pytest.raises(ValidationError):
        ambulance_service._get_ambulance_crew_member(
            staff.id,
            1,
            (Role.DRIVER,),
            "driver",
        )


def test_get_crew_member_rejects_inactive_user(monkeypatch):
    staff = make_staff(
        role=Role.DRIVER,
        user=make_user(
            role=Role.DRIVER,
            is_active=False,
        ),
    )

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        Mock(return_value=staff),
    )

    with pytest.raises(ValidationError):
        ambulance_service._get_ambulance_crew_member(
            staff.id,
            1,
            (Role.DRIVER,),
            "driver",
        )


# Trip request


def test_request_trip_creates_emergency_trip(
    app,
    user,
    clinic,
    make_patient,
    monkeypatch,
    audit_mock,
    clinic_active_mock,
):
    patient = make_patient(clinic)

    monkeypatch.setattr(
        ambulance_service,
        "_get_patient",
        Mock(return_value=patient),
    )

    with app.test_request_context():
        from flask import g

        g.current_user_id = user.id

        install_fake_trip_model(monkeypatch)

        trip = ambulance_service.request_trip(
            clinic_id=user.clinic_id,
            trip_type=TripType.EMERGENCY_PICKUP,
            patient_id=patient.id,
            pickup_address="Pickup",
            destination_address="Hospital",
        )

        assert trip.trip_type == TripType.EMERGENCY_PICKUP
        assert trip.status == TripStatus.REQUESTED
        assert trip.patient is patient
        audit_mock.assert_called_once()


@pytest.mark.parametrize(
    "trip_type",
    [
        TripType.DISCHARGE_TRANSPORT,
        TripType.INTER_FACILITY_TRANSFER,
    ],
)
def test_request_trip_requires_admission(
    app,
    user,
    clinic,
    make_patient,
    trip_type,
    monkeypatch,
    clinic_active_mock,
):
    patient = make_patient(clinic)

    monkeypatch.setattr(
        ambulance_service,
        "_get_patient",
        Mock(return_value=patient),
    )

    with app.test_request_context():
        from flask import g

        g.current_user_id = user.id

        with pytest.raises(
            ValidationError,
            match="admission",
        ):
            ambulance_service.request_trip(
                clinic_id=user.clinic_id,
                trip_type=trip_type,
                patient_id=patient.id,
            )


def test_request_trip_rejects_mismatched_admission(
    app,
    user,
    monkeypatch,
    clinic_active_mock,
):
    patient = make_patient(
        patient_id=1,
        clinic_id=user.clinic_id,
    )
    other_patient = make_patient(
        patient_id=2,
        clinic_id=user.clinic_id,
    )
    admission = make_admission(
        patient=other_patient,
    )

    monkeypatch.setattr(
        ambulance_service,
        "_get_patient",
        Mock(return_value=patient),
    )
    monkeypatch.setattr(
        ambulance_service,
        "_get_admission",
        Mock(return_value=admission),
    )

    with app.test_request_context():
        from flask import g

        g.current_user_id = user.id

        with pytest.raises(ValidationError):
            ambulance_service.request_trip(
                clinic_id=user.clinic_id,
                trip_type=TripType.EMERGENCY_PICKUP,
                patient_id=patient.id,
                admission_id=admission.id,
            )


def test_request_trip_uses_admission_patient(
    app,
    user,
    clinic,
    make_patient,
    make_staff,
    monkeypatch,
    audit_mock,
    clinic_active_mock,
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

    monkeypatch.setattr(
        ambulance_service,
        "_get_admission",
        Mock(return_value=admission),
    )

    with app.test_request_context():
        from flask import g

        g.current_user_id = user.id

        trip = ambulance_service.request_trip(
            clinic_id=user.clinic_id,
            trip_type=TripType.EMERGENCY_PICKUP,
            admission_id=admission.id,
        )

        assert trip.patient is patient
        assert trip.patient_id == patient.id
        assert trip.admission is admission
        assert trip.admission_id == admission.id


# Dispatch


def test_dispatch_trip_assigns_vehicle_and_crew(
    app,
    monkeypatch,
    audit_mock,
    clinic_active_mock,
):
    trip = make_trip()
    vehicle = make_vehicle()
    driver = make_staff(role=Role.DRIVER)
    paramedic = make_staff(
        staff_id=2,
        role=Role.PARAMEDIC,
    )

    install_locked_trip(monkeypatch, trip)
    monkeypatch.setattr(
        ambulance_service,
        "_lock_vehicle",
        Mock(return_value=vehicle),
    )
    monkeypatch.setattr(
        ambulance_service,
        "_get_ambulance_crew_member",
        Mock(
            side_effect=[
                driver,
                paramedic,
            ]
        ),
    )

    with app.test_request_context():
        result = ambulance_service.dispatch_trip(
            trip.id,
            vehicle.id,
            driver.id,
            paramedic.id,
        )

    assert result is trip
    assert trip.status == TripStatus.DISPATCHED
    assert trip.vehicle is vehicle
    assert trip.driver is driver
    assert trip.paramedic is paramedic
    assert vehicle.status == VehicleStatus.ON_TRIP
    audit_mock.assert_called_once()


def test_dispatch_rejects_non_requested_trip(
    app,
    monkeypatch,
    clinic_active_mock,
):
    trip = make_trip(
        status=TripStatus.DISPATCHED,
    )

    install_locked_trip(monkeypatch, trip)

    with app.test_request_context():
        with pytest.raises(ConflictError):
            ambulance_service.dispatch_trip(
                trip.id,
                1,
                1,
            )


def test_dispatch_rejects_busy_vehicle(
    app,
    monkeypatch,
    clinic_active_mock,
):
    trip = make_trip()
    vehicle = make_vehicle(
        status=VehicleStatus.ON_TRIP,
    )

    install_locked_trip(monkeypatch, trip)
    monkeypatch.setattr(
        ambulance_service,
        "_lock_vehicle",
        Mock(return_value=vehicle),
    )

    with app.test_request_context():
        with pytest.raises(ConflictError):
            ambulance_service.dispatch_trip(
                trip.id,
                vehicle.id,
                1,
            )


def test_dispatch_rejects_vehicle_from_other_clinic(
    app,
    monkeypatch,
    clinic_active_mock,
):
    trip = make_trip(clinic_id=1)
    vehicle = make_vehicle(clinic_id=2)

    install_locked_trip(monkeypatch, trip)
    monkeypatch.setattr(
        ambulance_service,
        "_lock_vehicle",
        Mock(return_value=vehicle),
    )

    with app.test_request_context():
        with pytest.raises(ValidationError):
            ambulance_service.dispatch_trip(
                trip.id,
                vehicle.id,
                1,
            )


def test_dispatch_rejects_same_driver_and_paramedic(
    app,
    monkeypatch,
    clinic_active_mock,
):
    trip = make_trip()
    vehicle = make_vehicle()
    staff = make_staff(role=Role.DRIVER)

    install_locked_trip(monkeypatch, trip)
    monkeypatch.setattr(
        ambulance_service,
        "_lock_vehicle",
        Mock(return_value=vehicle),
    )
    monkeypatch.setattr(
        ambulance_service,
        "_get_ambulance_crew_member",
        Mock(
            side_effect=[
                staff,
                staff,
            ]
        ),
    )

    with app.test_request_context():
        with pytest.raises(ValidationError):
            ambulance_service.dispatch_trip(
                trip.id,
                vehicle.id,
                staff.id,
                staff.id,
            )


# Trip status lifecycle


@pytest.mark.parametrize(
    "current,new_status",
    [
        (
            TripStatus.DISPATCHED,
            TripStatus.EN_ROUTE_TO_PICKUP,
        ),
        (
            TripStatus.EN_ROUTE_TO_PICKUP,
            TripStatus.AT_PICKUP,
        ),
        (
            TripStatus.AT_PICKUP,
            TripStatus.PATIENT_ON_BOARD,
        ),
        (
            TripStatus.PATIENT_ON_BOARD,
            TripStatus.EN_ROUTE_TO_DESTINATION,
        ),
    ],
)
def test_update_trip_status_valid_transitions(
    app,
    monkeypatch,
    current,
    new_status,
    audit_mock,
    clinic_active_mock,
):
    patient = make_patient()
    trip = make_trip(
        status=current,
        patient=patient,
    )

    install_locked_trip(monkeypatch, trip)
    monkeypatch.setattr(
        ambulance_service,
        "_get_patient",
        Mock(return_value=patient),
    )

    with app.test_request_context():
        result = ambulance_service.update_trip_status(
            trip.id,
            new_status,
        )

    assert result.status == new_status
    audit_mock.assert_called_once()


def test_update_trip_status_rejects_invalid_transition(
    app,
    monkeypatch,
    clinic_active_mock,
):
    trip = make_trip(
        status=TripStatus.REQUESTED,
    )

    install_locked_trip(monkeypatch, trip)

    with app.test_request_context():
        with pytest.raises(ConflictError):
            ambulance_service.update_trip_status(
                trip.id,
                TripStatus.COMPLETED,
            )


def test_update_trip_status_patient_on_board_requires_patient(
    app,
    monkeypatch,
    clinic_active_mock,
):
    trip = make_trip(
        status=TripStatus.AT_PICKUP,
    )

    install_locked_trip(monkeypatch, trip)

    with app.test_request_context():
        with pytest.raises(ValidationError):
            ambulance_service.update_trip_status(
                trip.id,
                TripStatus.PATIENT_ON_BOARD,
            )


# Link patient


def test_link_patient_links_patient(
    app,
    monkeypatch,
    audit_mock,
    clinic_active_mock,
):
    trip = make_trip()
    patient = make_patient()

    install_locked_trip(monkeypatch, trip)
    monkeypatch.setattr(
        ambulance_service,
        "_get_patient",
        Mock(return_value=patient),
    )

    with app.test_request_context():
        result = ambulance_service.link_patient(
            trip.id,
            patient.id,
        )

    assert result.patient is patient
    audit_mock.assert_called_once()


def test_link_patient_is_idempotent(
    app,
    monkeypatch,
    audit_mock,
    clinic_active_mock,
):
    patient = make_patient()
    trip = make_trip(patient=patient)

    install_locked_trip(monkeypatch, trip)
    monkeypatch.setattr(
        ambulance_service,
        "_get_patient",
        Mock(return_value=patient),
    )

    with app.test_request_context():
        result = ambulance_service.link_patient(
            trip.id,
            patient.id,
        )

    assert result is trip
    audit_mock.assert_not_called()


def test_link_patient_rejects_different_patient(
    app,
    monkeypatch,
    clinic_active_mock,
):
    existing = make_patient(patient_id=1)
    other = make_patient(patient_id=2)
    trip = make_trip(patient=existing)

    install_locked_trip(monkeypatch, trip)
    monkeypatch.setattr(
        ambulance_service,
        "_get_patient",
        Mock(return_value=other),
    )

    with app.test_request_context():
        with pytest.raises(ConflictError):
            ambulance_service.link_patient(
                trip.id,
                other.id,
            )


def test_link_patient_rejects_completed_trip(
    app,
    monkeypatch,
    clinic_active_mock,
):
    trip = make_trip(
        status=TripStatus.COMPLETED,
    )

    install_locked_trip(monkeypatch, trip)

    with app.test_request_context():
        with pytest.raises(ConflictError):
            ambulance_service.link_patient(
                trip.id,
                1,
            )


# Complete trip


def test_complete_trip_completes_and_releases_vehicle(
    app,
    monkeypatch,
    audit_mock,
    clinic_active_mock,
):
    patient = make_patient()
    vehicle = make_vehicle(
        status=VehicleStatus.ON_TRIP,
    )
    trip = make_trip(
        status=TripStatus.EN_ROUTE_TO_DESTINATION,
        patient=patient,
        vehicle=vehicle,
    )

    install_locked_trip(monkeypatch, trip)
    monkeypatch.setattr(
        ambulance_service,
        "_get_patient",
        Mock(return_value=patient),
    )
    monkeypatch.setattr(
        ambulance_service,
        "_lock_vehicle",
        Mock(return_value=vehicle),
    )

    with app.test_request_context():
        result = ambulance_service.complete_trip(trip.id)

    assert result.status == TripStatus.COMPLETED
    assert vehicle.status == VehicleStatus.AVAILABLE
    audit_mock.assert_called_once()


def test_complete_trip_requires_patient(
    app,
    monkeypatch,
    clinic_active_mock,
):
    trip = make_trip(
        status=TripStatus.EN_ROUTE_TO_DESTINATION,
    )

    install_locked_trip(monkeypatch, trip)

    with app.test_request_context():
        with pytest.raises(ValidationError):
            ambulance_service.complete_trip(trip.id)


def test_complete_trip_requires_correct_status(
    app,
    monkeypatch,
    clinic_active_mock,
):
    trip = make_trip(
        status=TripStatus.DISPATCHED,
        patient=make_patient(),
    )

    install_locked_trip(monkeypatch, trip)

    with app.test_request_context():
        with pytest.raises(ConflictError):
            ambulance_service.complete_trip(trip.id)


# Invoice


def test_link_invoice_links_matching_invoice(
    app,
    monkeypatch,
    audit_mock,
    clinic_active_mock,
):
    patient = make_patient()
    trip = make_trip(
        status=TripStatus.COMPLETED,
        patient=patient,
    )
    invoice = make_invoice(
        clinic_id=1,
        patient_id=patient.id,
    )

    install_locked_trip(monkeypatch, trip)
    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        Mock(return_value=invoice),
    )

    with app.test_request_context():
        result = ambulance_service.link_invoice(
            trip.id,
            invoice.id,
        )

    assert result.invoice is invoice
    audit_mock.assert_called_once()


def test_link_invoice_requires_completed_trip(
    app,
    monkeypatch,
    clinic_active_mock,
):
    trip = make_trip(
        status=TripStatus.DISPATCHED,
        patient=make_patient(),
    )

    install_locked_trip(monkeypatch, trip)

    with app.test_request_context():
        with pytest.raises(ConflictError):
            ambulance_service.link_invoice(
                trip.id,
                1,
            )


def test_link_invoice_requires_patient(
    app,
    monkeypatch,
    clinic_active_mock,
):
    trip = make_trip(
        status=TripStatus.COMPLETED,
    )

    install_locked_trip(monkeypatch, trip)

    with app.test_request_context():
        with pytest.raises(ValidationError):
            ambulance_service.link_invoice(
                trip.id,
                1,
            )


def test_link_invoice_rejects_wrong_clinic(
    app,
    monkeypatch,
    clinic_active_mock,
):
    trip = make_trip(
        status=TripStatus.COMPLETED,
        patient=make_patient(),
    )
    invoice = make_invoice(
        clinic_id=2,
        patient_id=trip.patient_id,
    )

    install_locked_trip(monkeypatch, trip)
    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        Mock(return_value=invoice),
    )

    with app.test_request_context():
        with pytest.raises(ValidationError):
            ambulance_service.link_invoice(
                trip.id,
                invoice.id,
            )


def test_link_invoice_rejects_wrong_patient(
    app,
    monkeypatch,
    clinic_active_mock,
):
    patient = make_patient(patient_id=1)
    trip = make_trip(
        status=TripStatus.COMPLETED,
        patient=patient,
    )
    invoice = make_invoice(
        clinic_id=1,
        patient_id=2,
    )

    install_locked_trip(monkeypatch, trip)
    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        Mock(return_value=invoice),
    )

    with app.test_request_context():
        with pytest.raises(ValidationError):
            ambulance_service.link_invoice(
                trip.id,
                invoice.id,
            )


def test_link_invoice_rejects_already_linked_invoice(
    app,
    monkeypatch,
    clinic_active_mock,
):
    patient = make_patient()
    other_trip = make_trip(trip_id=99)
    invoice = make_invoice(
        clinic_id=1,
        patient_id=patient.id,
        ambulance_trip=other_trip,
    )
    trip = make_trip(
        status=TripStatus.COMPLETED,
        patient=patient,
    )

    install_locked_trip(monkeypatch, trip)
    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        Mock(return_value=invoice),
    )

    with app.test_request_context():
        with pytest.raises(ConflictError):
            ambulance_service.link_invoice(
                trip.id,
                invoice.id,
            )


# Cancellation


def test_cancel_trip_cancels_trip(
    app,
    monkeypatch,
    audit_mock,
    clinic_active_mock,
):
    trip = make_trip()
    install_locked_trip(monkeypatch, trip)

    with app.test_request_context():
        result = ambulance_service.cancel_trip(
            trip.id,
            "Patient cancelled transport",
        )

    assert result.status == TripStatus.CANCELLED
    assert (
        result.cancellation_reason
        == "Patient cancelled transport"
    )
    audit_mock.assert_called_once()


def test_cancel_trip_strips_reason(
    app,
    monkeypatch,
    audit_mock,
    clinic_active_mock,
):
    trip = make_trip()
    install_locked_trip(monkeypatch, trip)

    with app.test_request_context():
        ambulance_service.cancel_trip(
            trip.id,
            "  Cancelled by patient  ",
        )

    assert trip.cancellation_reason == "Cancelled by patient"


@pytest.mark.parametrize(
    "reason",
    ["", "   ", None, 123],
)
def test_cancel_trip_rejects_invalid_reason(
    app,
    monkeypatch,
    reason,
    clinic_active_mock,
):
    trip = make_trip()
    install_locked_trip(monkeypatch, trip)

    with app.test_request_context():
        with pytest.raises(ValidationError):
            ambulance_service.cancel_trip(
                trip.id,
                reason,
            )


def test_cancel_trip_rejects_long_reason(
    app,
    monkeypatch,
    clinic_active_mock,
):
    trip = make_trip()
    install_locked_trip(monkeypatch, trip)

    with app.test_request_context():
        with pytest.raises(ValidationError):
            ambulance_service.cancel_trip(
                trip.id,
                "x" * 256,
            )


def test_cancel_trip_rejects_completed_trip(
    app,
    monkeypatch,
    clinic_active_mock,
):
    trip = make_trip(
        status=TripStatus.COMPLETED,
    )

    install_locked_trip(monkeypatch, trip)

    with app.test_request_context():
        with pytest.raises(ConflictError):
            ambulance_service.cancel_trip(
                trip.id,
                "Too late",
            )


def test_cancel_trip_rejects_already_cancelled_trip(
    app,
    monkeypatch,
    clinic_active_mock,
):
    trip = make_trip(
        status=TripStatus.CANCELLED,
    )

    install_locked_trip(monkeypatch, trip)

    with app.test_request_context():
        with pytest.raises(ConflictError):
            ambulance_service.cancel_trip(
                trip.id,
                "Duplicate cancellation",
            )


def test_cancel_trip_releases_on_trip_vehicle(
    app,
    monkeypatch,
    audit_mock,
    clinic_active_mock,
):
    vehicle = make_vehicle(
        status=VehicleStatus.ON_TRIP,
    )
    trip = make_trip(
        vehicle=vehicle,
    )

    install_locked_trip(monkeypatch, trip)
    monkeypatch.setattr(
        ambulance_service,
        "_lock_vehicle",
        Mock(return_value=vehicle),
    )

    with app.test_request_context():
        ambulance_service.cancel_trip(
            trip.id,
            "Transport no longer required",
        )

    assert trip.status == TripStatus.CANCELLED
    assert vehicle.status == VehicleStatus.AVAILABLE


def test_cancel_trip_does_not_change_available_vehicle(
    app,
    monkeypatch,
    audit_mock,
    clinic_active_mock,
):
    vehicle = make_vehicle(
        status=VehicleStatus.AVAILABLE,
    )
    trip = make_trip(
        vehicle=vehicle,
    )

    install_locked_trip(monkeypatch, trip)
    monkeypatch.setattr(
        ambulance_service,
        "_lock_vehicle",
        Mock(return_value=vehicle),
    )

    with app.test_request_context():
        ambulance_service.cancel_trip(
            trip.id,
            "Transport no longer required",
        )
    assert vehicle.status == VehicleStatus.AVAILABLE