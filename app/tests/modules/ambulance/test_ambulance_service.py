# app/tests/modules/ambulance/test_ambulance_service.py

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import g

from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus
from app.core.enums.ambulance_enums import TripStatus, TripType
from app.core.enums.ambulance_enums import VehicleStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.ambulance.services import ambulance_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_ambulance_side_effects(monkeypatch):
    """
    Keep service unit tests focused on ambulance service behavior.

    The real transaction decorator is intentionally left untouched.
    """

    monkeypatch.setattr(
        ambulance_service,
        "ensure_clinic_active",
        Mock(),
    )

    monkeypatch.setattr(
        ambulance_service,
        "create_audit_log",
        Mock(),
    )


def make_user(
    user_id=1,
    clinic_id=10,
    is_active=True,
    role=Role.ADMIN,
):
    return SimpleNamespace(
        id=user_id,
        clinic_id=clinic_id,
        is_active=is_active,
        role=role,
    )


def make_patient(
    patient_id=100,
    clinic_id=10,
    is_active=True,
):
    return SimpleNamespace(
        id=patient_id,
        clinic_id=clinic_id,
        is_active=is_active,
    )


def make_vehicle(
    vehicle_id=1,
    clinic_id=10,
    plate_number="AB-123",
    capacity=2,
    status=VehicleStatus.AVAILABLE,
):
    return SimpleNamespace(
        id=vehicle_id,
        clinic_id=clinic_id,
        plate_number=plate_number,
        capacity=capacity,
        status=status,
        equipment_level=SimpleNamespace(value="BLS"),
    )


def make_trip(
    trip_id=1,
    clinic_id=10,
    status=TripStatus.REQUESTED,
    patient=None,
    admission=None,
    vehicle=None,
):
    return SimpleNamespace(
        id=trip_id,
        clinic_id=clinic_id,
        status=status,
        patient=patient,
        patient_id=getattr(patient, "id", None),
        admission=admission,
        admission_id=getattr(admission, "id", None),
        vehicle=vehicle,
        vehicle_id=getattr(vehicle, "id", None),
        driver=None,
        driver_id=None,
        paramedic=None,
        paramedic_id=None,
        invoice=None,
        invoice_id=None,
        dispatched_at=None,
        pickup_at=None,
        completed_at=None,
        cancelled_at=None,
        cancellation_reason=None,
    )


def make_staff(
    staff_id=50,
    clinic_id=10,
    role=Role.DRIVER,
    active=True,
    linked_user=None,
):
    if linked_user is None:
        linked_user = make_user(
            user_id=staff_id + 1000,
            clinic_id=clinic_id,
            is_active=active,
            role=role,
        )

    return SimpleNamespace(
        id=staff_id,
        clinic_id=clinic_id,
        status=StaffStatus.ACTIVE if active else next(
            status
            for status in StaffStatus
            if status != StaffStatus.ACTIVE
        ),
        user=linked_user,
        user_id=linked_user.id if linked_user else None,
    )


def make_invoice(
    invoice_id=500,
    clinic_id=10,
    patient_id=100,
):
    return SimpleNamespace(
        id=invoice_id,
        clinic_id=clinic_id,
        patient_id=patient_id,
    )


def install_current_user(monkeypatch, user):
    """
    Mock the service's db.session.get(User, id) lookup while using
    a real Flask request context.
    """

    original_get = ambulance_service.db.session.get

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        return original_get(model, object_id)

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )


# ---------------------------------------------------------------------------
# Authentication / clinic helpers
# ---------------------------------------------------------------------------

def test_current_user_requires_request_context():
    with pytest.raises(ValidationError, match="Authenticated request context is required"):
        ambulance_service._current_user()


def test_current_user_requires_current_user_id(app, monkeypatch):
    with app.test_request_context():
        g.current_user_id = None

        with pytest.raises(ValidationError):
            ambulance_service._current_user()


def test_current_user_loads_active_user(app, monkeypatch):
    user = make_user()

    with app.test_request_context():
        g.current_user_id = user.id

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=user),
        )

        result = ambulance_service._current_user()

        assert result is user


def test_current_user_rejects_missing_user(app, monkeypatch):
    with app.test_request_context():
        g.current_user_id = 999

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=None),
        )

        with pytest.raises(ValidationError):
            ambulance_service._current_user()


def test_current_user_rejects_inactive_user(app, monkeypatch):
    user = make_user(is_active=False)

    with app.test_request_context():
        g.current_user_id = user.id

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=user),
        )

        with pytest.raises(ValidationError):
            ambulance_service._current_user()


def test_current_clinic_id_requires_clinic(app, monkeypatch):
    user = make_user(clinic_id=None)

    with app.test_request_context():
        g.current_user_id = user.id

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=user),
        )

        with pytest.raises(ValidationError):
            ambulance_service._current_clinic_id()


def test_current_clinic_id_returns_authenticated_clinic(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    with app.test_request_context():
        g.current_user_id = user.id

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=user),
        )

        assert ambulance_service._current_clinic_id() == 10


def test_assert_authenticated_clinic_skips_without_request_context():
    ambulance_service._assert_authenticated_clinic(999)


def test_assert_authenticated_clinic_rejects_cross_clinic(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    with app.test_request_context():
        g.current_user_id = user.id

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=user),
        )

        with pytest.raises(ValidationError):
            ambulance_service._assert_authenticated_clinic(20)


def test_assert_authenticated_clinic_allows_same_clinic(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    with app.test_request_context():
        g.current_user_id = user.id

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=user),
        )

        ambulance_service._assert_authenticated_clinic(10)


# ---------------------------------------------------------------------------
# Vehicle lookup
# ---------------------------------------------------------------------------

def test_get_vehicle_returns_vehicle(app, monkeypatch):
    user = make_user(clinic_id=10)
    vehicle = make_vehicle(clinic_id=10)

    with app.test_request_context():
        g.current_user_id = user.id

        def fake_get(model, object_id):
            if model is ambulance_service.User:
                return user
            if model is ambulance_service.AmbulanceVehicle:
                return vehicle
            return None

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            fake_get,
        )

        result = ambulance_service.get_vehicle(vehicle.id)

        assert result is vehicle


def test_get_vehicle_not_found(app, monkeypatch):
    user = make_user()

    with app.test_request_context():
        g.current_user_id = user.id

        def fake_get(model, object_id):
            if model is ambulance_service.User:
                return user
            return None

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            fake_get,
        )

        with pytest.raises(NotFoundError):
            ambulance_service.get_vehicle(999)


def test_get_vehicle_rejects_other_clinic(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    vehicle = make_vehicle(clinic_id=20)

    with app.test_request_context():
        g.current_user_id = user.id

        def fake_get(model, object_id):
            if model is ambulance_service.User:
                return user
            if model is ambulance_service.AmbulanceVehicle:
                return vehicle
            return None

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            fake_get,
        )

        with pytest.raises(ValidationError):
            ambulance_service.get_vehicle(vehicle.id)


# ---------------------------------------------------------------------------
# Vehicle listing
# ---------------------------------------------------------------------------

def test_list_vehicles_requires_authenticated_clinic(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    with app.test_request_context():
        g.current_user_id = user.id

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=user),
        )

        query = Mock()
        query.filter_by.return_value = query
        query.order_by.return_value = query
        query.all.return_value = []

        monkeypatch.setattr(
            ambulance_service.AmbulanceVehicle,
            "query",
            query,
        )

        result = ambulance_service.list_vehicles(10)

        assert result == []


def test_list_vehicles_rejects_other_clinic(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    with app.test_request_context():
        g.current_user_id = user.id

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=user),
        )

        with pytest.raises(ValidationError):
            ambulance_service.list_vehicles(20)


def test_list_vehicles_filters_status(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    vehicle = make_vehicle()

    with app.test_request_context():
        g.current_user_id = user.id

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=user),
        )

        query = Mock()
        query.filter_by.return_value = query
        query.order_by.return_value = query
        query.all.return_value = [vehicle]

        monkeypatch.setattr(
            ambulance_service.AmbulanceVehicle,
            "query",
            query,
        )

        result = ambulance_service.list_vehicles(
            10,
            status=VehicleStatus.AVAILABLE,
        )

        assert result == [vehicle]
        query.filter_by.assert_called()


# ---------------------------------------------------------------------------
# Vehicle creation
# ---------------------------------------------------------------------------

def test_create_vehicle_normalizes_plate(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    query = Mock()
    query.filter_by.return_value = query
    query.first.return_value = None

    vehicle = make_vehicle(
        plate_number="AB-123",
        capacity=2,
    )

    vehicle_cls = Mock(return_value=vehicle)
    vehicle_cls.query = query

    monkeypatch.setattr(
        ambulance_service,
        "AmbulanceVehicle",
        vehicle_cls,
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

    with app.test_request_context():
        g.current_user_id = user.id

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=user),
        )

        result = ambulance_service.create_vehicle(
            clinic_id=10,
            plate_number="  ab-123  ",
            equipment_level="BLS",
            capacity=2,
        )

        assert result is vehicle
        vehicle_cls.assert_called_once()


def test_create_vehicle_rejects_non_string_plate(app):
    with app.test_request_context():
        g.current_user_id = 1

        with pytest.raises(ValidationError):
            ambulance_service.create_vehicle(
                clinic_id=10,
                plate_number=123,
                equipment_level="BLS",
                capacity=2,
            )


def test_create_vehicle_rejects_blank_plate(app):
    with app.test_request_context():
        g.current_user_id = 1

        with pytest.raises(ValidationError):
            ambulance_service.create_vehicle(
                clinic_id=10,
                plate_number="   ",
                equipment_level="BLS",
                capacity=2,
            )


def test_create_vehicle_rejects_invalid_capacity(app):
    with app.test_request_context():
        g.current_user_id = 1

        with pytest.raises(ValidationError):
            ambulance_service.create_vehicle(
                clinic_id=10,
                plate_number="AB-123",
                equipment_level="BLS",
                capacity=0,
            )


def test_create_vehicle_rejects_invalid_initial_status(app):
    with app.test_request_context():
        g.current_user_id = 1

        with pytest.raises(ValidationError):
            ambulance_service.create_vehicle(
                clinic_id=10,
                plate_number="AB-123",
                equipment_level="BLS",
                capacity=2,
                status=VehicleStatus.ON_TRIP,
            )


def test_create_vehicle_rejects_duplicate_plate(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    query = Mock()
    query.filter_by.return_value = query
    query.first.return_value = make_vehicle()

    monkeypatch.setattr(
        ambulance_service.AmbulanceVehicle,
        "query",
        query,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=user),
        )

        with pytest.raises(ConflictError):
            ambulance_service.create_vehicle(
                clinic_id=10,
                plate_number="AB-123",
                equipment_level="BLS",
                capacity=2,
            )


def test_create_vehicle_rejects_wrong_authenticated_clinic(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    with app.test_request_context():
        g.current_user_id = user.id

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=user),
        )

        with pytest.raises(ValidationError):
            ambulance_service.create_vehicle(
                clinic_id=20,
                plate_number="AB-123",
                equipment_level="BLS",
                capacity=2,
            )


def test_create_vehicle_requires_active_clinic(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    monkeypatch.setattr(
        ambulance_service,
        "ensure_clinic_active",
        Mock(side_effect=ValidationError("Clinic is inactive")),
    )

    with app.test_request_context():
        g.current_user_id = user.id

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=user),
        )

        with pytest.raises(ValidationError):
            ambulance_service.create_vehicle(
                clinic_id=10,
                plate_number="AB-123",
                equipment_level="BLS",
                capacity=2,
            )


# ---------------------------------------------------------------------------
# Vehicle status
# ---------------------------------------------------------------------------

def test_set_vehicle_status_same_status_is_idempotent(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    vehicle = make_vehicle(status=VehicleStatus.AVAILABLE)

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceVehicle:
            return vehicle
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        result = ambulance_service.set_vehicle_status(
            vehicle.id,
            VehicleStatus.AVAILABLE,
        )

        assert result is vehicle
        assert vehicle.status == VehicleStatus.AVAILABLE


def test_set_vehicle_status_rejects_manual_on_trip(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    vehicle = make_vehicle(
        status=VehicleStatus.AVAILABLE,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user

        if model is ambulance_service.AmbulanceVehicle:
            return vehicle

        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(
            ValidationError,
            match="ON_TRIP is managed automatically",
        ):
            ambulance_service.set_vehicle_status(
                vehicle.id,
                VehicleStatus.ON_TRIP,
            )


def test_set_vehicle_status_cannot_change_vehicle_away_from_on_trip(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    vehicle = make_vehicle(status=VehicleStatus.ON_TRIP)

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceVehicle:
            return vehicle
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    target_status = next(
        status
        for status in VehicleStatus
        if status != VehicleStatus.ON_TRIP
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(ConflictError):
            ambulance_service.set_vehicle_status(
                vehicle.id,
                target_status,
            )


def test_set_vehicle_status_updates_normal_status(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    vehicle = make_vehicle(status=VehicleStatus.AVAILABLE)

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceVehicle:
            return vehicle
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    target_status = next(
        status
        for status in VehicleStatus
        if status not in {
            VehicleStatus.AVAILABLE,
            VehicleStatus.ON_TRIP,
        }
    )

    with app.test_request_context():
        g.current_user_id = user.id

        result = ambulance_service.set_vehicle_status(
            vehicle.id,
            target_status,
        )

        assert result is vehicle
        assert vehicle.status == target_status


# ---------------------------------------------------------------------------
# Trip lookup / listing
# ---------------------------------------------------------------------------

def test_get_trip_returns_trip(app, monkeypatch):
    user = make_user(clinic_id=10)
    trip = make_trip(clinic_id=10)

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        assert ambulance_service.get_trip(trip.id) is trip


def test_get_trip_not_found(app, monkeypatch):
    user = make_user(clinic_id=10)

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(NotFoundError):
            ambulance_service.get_trip(999)


def test_get_trip_rejects_other_clinic(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    trip = make_trip(clinic_id=20)

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(ValidationError):
            ambulance_service.get_trip(trip.id)


def test_list_trips_rejects_other_clinic(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    with app.test_request_context():
        g.current_user_id = user.id

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=user),
        )

        with pytest.raises(ValidationError):
            ambulance_service.list_trips(20)


# ---------------------------------------------------------------------------
# Patient / admission helpers
# ---------------------------------------------------------------------------

def test_get_patient_returns_active_same_clinic_patient(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    patient = make_patient(clinic_id=10)

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.Patient:
            return patient
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        result = ambulance_service._get_patient(
            patient.id,
            10,
        )

        assert result is patient


def test_get_patient_rejects_missing_patient(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(NotFoundError):
            ambulance_service._get_patient(999, 10)


def test_get_patient_rejects_other_clinic(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    patient = make_patient(clinic_id=20)

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.Patient:
            return patient
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(ValidationError):
            ambulance_service._get_patient(
                patient.id,
                10,
            )


def test_get_patient_rejects_inactive_patient(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    patient = make_patient(
        clinic_id=10,
        is_active=False,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.Patient:
            return patient
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(ValidationError):
            ambulance_service._get_patient(
                patient.id,
                10,
            )


# ---------------------------------------------------------------------------
# Crew validation
# ---------------------------------------------------------------------------

def test_get_driver_accepts_driver_role(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    staff = make_staff(
        clinic_id=10,
        role=Role.DRIVER,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.Staff:
            return staff
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        result = ambulance_service._get_ambulance_crew_member(
            staff.id,
            10,
            (Role.DRIVER,),
            "driver",
        )

        assert result is staff


def test_get_paramedic_accepts_paramedic_role(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    staff = make_staff(
        clinic_id=10,
        role=Role.PARAMEDIC,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.Staff:
            return staff
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        result = ambulance_service._get_ambulance_crew_member(
            staff.id,
            10,
            (Role.PARAMEDIC, Role.EMT),
            "paramedic",
        )

        assert result is staff


def test_get_crew_member_rejects_inactive_staff(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    staff = make_staff(
        clinic_id=10,
        role=Role.DRIVER,
        active=False,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.Staff:
            return staff
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(ValidationError):
            ambulance_service._get_ambulance_crew_member(
                staff.id,
                10,
                (Role.DRIVER,),
                "driver",
            )


def test_get_crew_member_rejects_wrong_role(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    staff = make_staff(
        clinic_id=10,
        role=Role.PARAMEDIC,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.Staff:
            return staff
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(ValidationError):
            ambulance_service._get_ambulance_crew_member(
                staff.id,
                10,
                (Role.DRIVER,),
                "driver",
            )


# ---------------------------------------------------------------------------
# Vehicle locking
# ---------------------------------------------------------------------------

def test_lock_vehicle_uses_row_lock(
    app,
    monkeypatch,
):
    vehicle = make_vehicle()

    query = Mock()
    query.filter_by.return_value = query
    query.with_for_update.return_value = query
    query.first.return_value = vehicle

    with app.app_context():
        monkeypatch.setattr(
            ambulance_service.AmbulanceVehicle,
            "query",
            query,
        )

        result = ambulance_service._lock_vehicle(
            vehicle.id,
        )

    assert result is vehicle

    query.filter_by.assert_called_once_with(
        id=vehicle.id,
    )
    query.with_for_update.assert_called_once_with()
    query.first.assert_called_once_with()


def test_lock_vehicle_not_found(
    app,
    monkeypatch,
):
    query = Mock()
    query.filter_by.return_value = query
    query.with_for_update.return_value = query
    query.first.return_value = None

    with app.app_context():
        monkeypatch.setattr(
            ambulance_service.AmbulanceVehicle,
            "query",
            query,
        )

        with pytest.raises(NotFoundError):
            ambulance_service._lock_vehicle(999)

    query.filter_by.assert_called_once_with(
        id=999,
    )
    query.with_for_update.assert_called_once_with()
    query.first.assert_called_once_with()


# ---------------------------------------------------------------------------
# Request trip
# ---------------------------------------------------------------------------

def test_request_trip_creates_requested_trip(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.REQUESTED,
    )

    trip_cls = Mock(return_value=trip)

    monkeypatch.setattr(
        ambulance_service,
        "AmbulanceTrip",
        trip_cls,
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

    with app.test_request_context():
        g.current_user_id = user.id

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=user),
        )

        result = ambulance_service.request_trip(
            clinic_id=10,
            trip_type=TripType.NON_EMERGENCY,
        )

        assert result is trip
        trip_cls.assert_called_once()


def test_request_trip_rejects_wrong_clinic(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    with app.test_request_context():
        g.current_user_id = user.id

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=user),
        )

        with pytest.raises(ValidationError):
            ambulance_service.request_trip(
                clinic_id=20,
                trip_type=TripType.NON_EMERGENCY,
            )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def test_dispatch_trip_requires_requested_status(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.DISPATCHED,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(ConflictError):
            ambulance_service.dispatch_trip(
                trip.id,
                1,
                50,
            )


def test_dispatch_trip_rejects_unavailable_vehicle(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.REQUESTED,
    )

    vehicle = make_vehicle(
        clinic_id=10,
        status=next(
            status
            for status in VehicleStatus
            if status not in {
                VehicleStatus.AVAILABLE,
                VehicleStatus.ON_TRIP,
            }
        ),
    )

    driver = make_staff(
        staff_id=50,
        clinic_id=10,
        role=Role.DRIVER,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        if model is ambulance_service.Staff:
            return driver
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    monkeypatch.setattr(
        ambulance_service,
        "_lock_vehicle",
        Mock(return_value=vehicle),
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(ConflictError):
            ambulance_service.dispatch_trip(
                trip.id,
                vehicle.id,
                driver.id,
            )


def test_dispatch_trip_rejects_same_driver_and_paramedic(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.REQUESTED,
    )

    vehicle = make_vehicle(
        clinic_id=10,
        status=VehicleStatus.AVAILABLE,
    )

    driver = make_staff(
        staff_id=50,
        clinic_id=10,
        role=Role.DRIVER,
    )

    paramedic = make_staff(
        staff_id=50,
        clinic_id=10,
        role=Role.PARAMEDIC,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user

        if model is ambulance_service.AmbulanceTrip:
            return trip

        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    monkeypatch.setattr(
        ambulance_service,
        "_lock_vehicle",
        Mock(return_value=vehicle),
    )

    def fake_crew_member(
        staff_id,
        clinic_id,
        allowed_roles,
        position,
    ):
        if position == "driver":
            return driver

        return paramedic

    monkeypatch.setattr(
        ambulance_service,
        "_get_ambulance_crew_member",
        fake_crew_member,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(
            ValidationError,
            match="Driver and paramedic must be different staff members",
        ):
            ambulance_service.dispatch_trip(
                trip.id,
                vehicle.id,
                driver.id,
                paramedic.id,
            )


# ---------------------------------------------------------------------------
# Trip status transitions
# ---------------------------------------------------------------------------

def test_update_trip_status_dispatch_to_en_route(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.DISPATCHED,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        result = ambulance_service.update_trip_status(
            trip.id,
            TripStatus.EN_ROUTE_TO_PICKUP,
        )

        assert result is trip
        assert trip.status == TripStatus.EN_ROUTE_TO_PICKUP


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (
            TripStatus.DISPATCHED,
            TripStatus.AT_PICKUP,
        ),
        (
            TripStatus.EN_ROUTE_TO_PICKUP,
            TripStatus.PATIENT_ON_BOARD,
        ),
        (
            TripStatus.AT_PICKUP,
            TripStatus.EN_ROUTE_TO_DESTINATION,
        ),
    ],
)
def test_update_trip_status_rejects_invalid_transition(
    app,
    monkeypatch,
    current,
    target,
):
    user = make_user(clinic_id=10)

    trip = make_trip(
        clinic_id=10,
        status=current,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(ConflictError):
            ambulance_service.update_trip_status(
                trip.id,
                target,
            )


def test_update_trip_status_requires_patient_before_patient_on_board(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.AT_PICKUP,
        patient=None,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(ValidationError):
            ambulance_service.update_trip_status(
                trip.id,
                TripStatus.PATIENT_ON_BOARD,
            )


# ---------------------------------------------------------------------------
# Link patient
# ---------------------------------------------------------------------------

def test_link_patient_assigns_patient(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    patient = make_patient(clinic_id=10)

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.REQUESTED,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        if model is ambulance_service.Patient:
            return patient
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        result = ambulance_service.link_patient(
            trip.id,
            patient.id,
        )

        assert result is trip
        assert trip.patient is patient


def test_link_patient_is_idempotent_for_same_patient(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    patient = make_patient(clinic_id=10)

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.REQUESTED,
        patient=patient,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        if model is ambulance_service.Patient:
            return patient
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        result = ambulance_service.link_patient(
            trip.id,
            patient.id,
        )

        assert result is trip
        assert trip.patient is patient


def test_link_patient_rejects_different_existing_patient(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    existing = make_patient(
        patient_id=100,
        clinic_id=10,
    )
    replacement = make_patient(
        patient_id=200,
        clinic_id=10,
    )

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.REQUESTED,
        patient=existing,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        if model is ambulance_service.Patient:
            if object_id == existing.id:
                return existing
            return replacement
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(ConflictError):
            ambulance_service.link_patient(
                trip.id,
                replacement.id,
            )


def test_link_patient_rejects_completed_trip(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    patient = make_patient(clinic_id=10)

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.COMPLETED,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        if model is ambulance_service.Patient:
            return patient
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(ConflictError):
            ambulance_service.link_patient(
                trip.id,
                patient.id,
            )


# ---------------------------------------------------------------------------
# Complete trip
# ---------------------------------------------------------------------------

def test_complete_trip_requires_destination_state(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    patient = make_patient(clinic_id=10)
    vehicle = make_vehicle(
        clinic_id=10,
        status=VehicleStatus.ON_TRIP,
    )

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.PATIENT_ON_BOARD,
        patient=patient,
        vehicle=vehicle,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        if model is ambulance_service.Patient:
            return patient
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(ConflictError):
            ambulance_service.complete_trip(trip.id)


def test_complete_trip_requires_patient(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    vehicle = make_vehicle(
        clinic_id=10,
        status=VehicleStatus.ON_TRIP,
    )

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.EN_ROUTE_TO_DESTINATION,
        patient=None,
        vehicle=vehicle,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(ValidationError):
            ambulance_service.complete_trip(trip.id)


def test_complete_trip_releases_vehicle(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    patient = make_patient(clinic_id=10)

    vehicle = make_vehicle(
        clinic_id=10,
        status=VehicleStatus.ON_TRIP,
    )

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.EN_ROUTE_TO_DESTINATION,
        patient=patient,
        vehicle=vehicle,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        if model is ambulance_service.Patient:
            return patient
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    monkeypatch.setattr(
        ambulance_service,
        "_lock_vehicle",
        Mock(return_value=vehicle),
    )

    with app.test_request_context():
        g.current_user_id = user.id

        result = ambulance_service.complete_trip(trip.id)

        assert result is trip
        assert trip.status == TripStatus.COMPLETED
        assert vehicle.status == VehicleStatus.AVAILABLE


# ---------------------------------------------------------------------------
# Invoice linking
# ---------------------------------------------------------------------------

def test_link_invoice_requires_completed_trip(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    patient = make_patient(clinic_id=10)

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.EN_ROUTE_TO_DESTINATION,
        patient=patient,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(
                side_effect=lambda model, object_id: (
                    user
                    if model is ambulance_service.User
                    else trip
                    if model is ambulance_service.AmbulanceTrip
                    else None
                )
            ),
        )

        with pytest.raises(ConflictError):
            ambulance_service.link_invoice(
                trip.id,
                500,
            )


def test_link_invoice_requires_patient(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.COMPLETED,
        patient=None,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(ValidationError):
            ambulance_service.link_invoice(
                trip.id,
                500,
            )


def test_link_invoice_rejects_other_clinic_invoice(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    patient = make_patient(clinic_id=10)

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.COMPLETED,
        patient=patient,
    )

    invoice = make_invoice(
        clinic_id=20,
        patient_id=patient.id,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        if model is ambulance_service.Invoice:
            return invoice
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(ValidationError):
            ambulance_service.link_invoice(
                trip.id,
                invoice.id,
            )


def test_link_invoice_rejects_wrong_patient(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    patient = make_patient(
        patient_id=100,
        clinic_id=10,
    )

    invoice = make_invoice(
        invoice_id=500,
        clinic_id=10,
        patient_id=999,
    )

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.COMPLETED,
        patient=patient,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        if model is ambulance_service.Invoice:
            return invoice
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(ValidationError):
            ambulance_service.link_invoice(
                trip.id,
                invoice.id,
            )


def test_link_invoice_rejects_invoice_already_linked(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)
    patient = make_patient(clinic_id=10)

    invoice = make_invoice(
        clinic_id=10,
        patient_id=patient.id,
    )

    another_trip = make_trip(
        trip_id=99,
        clinic_id=10,
        status=TripStatus.COMPLETED,
        patient=patient,
    )

    invoice.ambulance_trip = another_trip

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.COMPLETED,
        patient=patient,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        if model is ambulance_service.Invoice:
            return invoice
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(ConflictError):
            ambulance_service.link_invoice(
                trip.id,
                invoice.id,
            )


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------

def test_cancel_trip_requires_reason(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.REQUESTED,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(ValidationError):
            ambulance_service.cancel_trip(
                trip.id,
                "   ",
            )


def test_cancel_trip_rejects_completed_trip(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.COMPLETED,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(ConflictError):
            ambulance_service.cancel_trip(
                trip.id,
                "Patient cancelled",
            )


def test_cancel_trip_is_not_allowed_twice(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.CANCELLED,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        with pytest.raises(ConflictError):
            ambulance_service.cancel_trip(
                trip.id,
                "Duplicate cancellation",
            )


def test_cancel_trip_releases_on_trip_vehicle(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    vehicle = make_vehicle(
        clinic_id=10,
        status=VehicleStatus.ON_TRIP,
    )

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.DISPATCHED,
        vehicle=vehicle,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    monkeypatch.setattr(
        ambulance_service,
        "_lock_vehicle",
        Mock(return_value=vehicle),
    )

    with app.test_request_context():
        g.current_user_id = user.id

        result = ambulance_service.cancel_trip(
            trip.id,
            "Transport no longer required",
        )

        assert result is trip
        assert trip.status == TripStatus.CANCELLED
        assert trip.cancellation_reason == (
            "Transport no longer required"
        )
        assert vehicle.status == VehicleStatus.AVAILABLE


def test_cancel_trip_strips_reason(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.REQUESTED,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        result = ambulance_service.cancel_trip(
            trip.id,
            "   Patient cancelled   ",
        )

        assert result is trip
        assert trip.status == TripStatus.CANCELLED
        assert trip.cancellation_reason == "Patient cancelled"


# ---------------------------------------------------------------------------
# Audit coverage
# ---------------------------------------------------------------------------

def test_create_vehicle_writes_audit(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    query = Mock()
    query.filter_by.return_value = query
    query.first.return_value = None

    vehicle = make_vehicle()

    vehicle_cls = Mock(return_value=vehicle)
    vehicle_cls.query = query

    monkeypatch.setattr(
        ambulance_service,
        "AmbulanceVehicle",
        vehicle_cls,
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

    audit = Mock()

    monkeypatch.setattr(
        ambulance_service,
        "create_audit_log",
        audit,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        monkeypatch.setattr(
            ambulance_service.db.session,
            "get",
            Mock(return_value=user),
        )

        ambulance_service.create_vehicle(
            clinic_id=10,
            plate_number="AB-123",
            equipment_level="BLS",
            capacity=2,
        )

        audit.assert_called_once()


def test_cancel_trip_writes_audit(
    app,
    monkeypatch,
):
    user = make_user(clinic_id=10)

    trip = make_trip(
        clinic_id=10,
        status=TripStatus.REQUESTED,
    )

    def fake_get(model, object_id):
        if model is ambulance_service.User:
            return user
        if model is ambulance_service.AmbulanceTrip:
            return trip
        return None

    monkeypatch.setattr(
        ambulance_service.db.session,
        "get",
        fake_get,
    )

    audit = Mock()

    monkeypatch.setattr(
        ambulance_service,
        "create_audit_log",
        audit,
    )

    with app.test_request_context():
        g.current_user_id = user.id

        ambulance_service.cancel_trip(
            trip.id,
            "Transport cancelled",
        )

        audit.assert_called_once()