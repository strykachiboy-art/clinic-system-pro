from __future__ import annotations

import os
from threading import Barrier

import pytest
from sqlalchemy import select

from app import create_app, extensions
from app.config import config_by_name
from app.core.enums.ambulance_enums import (
    EquipmentLevel,
    TripStatus,
    TripType,
    VehicleStatus,
)
from app.core.enums.clinic_enums import ClinicStatus
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import ConflictError
from app.extensions import db
from app.modules.ambulance.models.ambulance_model import (
    AmbulanceTrip,
    AmbulanceVehicle,
)
from app.modules.ambulance.services import ambulance_service
from app.modules.clinic.models.clinic_model import Clinic
from app.core.auth.user.models.user_model import User
from app.modules.staff.models.staff_model import Staff


def test_ambulance_vehicle_is_assigned_to_only_one_trip_under_concurrency(
    monkeypatch,
):
    database_url = os.getenv(
        "CONCURRENCY_TEST_DATABASE_URL"
    )

    if not database_url:
        pytest.fail(
            "CONCURRENCY_TEST_DATABASE_URL is required"
        )

    original_database_url = (
        config_by_name["testing"].SQLALCHEMY_DATABASE_URI
    )

    original_redis_client = (
        extensions.redis_client
    )

    config_by_name["testing"].SQLALCHEMY_DATABASE_URI = (
        database_url
    )

    app = create_app("testing")

    extensions.redis_client = (
        original_redis_client
    )

    monkeypatch.setattr(
        ambulance_service,
        "create_audit_log",
        lambda *args, **kwargs: None,
    )

    gate = Barrier(2)

    original_lock_vehicle = (
        ambulance_service._lock_vehicle
    )

    def synchronized_lock_vehicle(
        vehicle_id,
    ):
        gate.wait(
            timeout=15
        )

        return original_lock_vehicle(
            vehicle_id
        )

    monkeypatch.setattr(
        ambulance_service,
        "_lock_vehicle",
        synchronized_lock_vehicle,
    )

    harness = None

    try:
        with app.app_context():
            from app import models_registry  # noqa: F401

            db.drop_all()
            db.create_all()

            clinic = Clinic(
                name="Gate 9 Ambulance Clinic",
                status=ClinicStatus.ACTIVE,
                ai_credits=5,
            )

            db.session.add(
                clinic
            )
            db.session.flush()

            user = User(
                clinic_id=clinic.id,
                role=Role.DRIVER,
                is_active=True,
                email="gate9-ambulance-driver@test.com",
            )

            user.set_password(
                "supersecret"
            )

            db.session.add(
                user
            )
            db.session.flush()

            driver = Staff(
                clinic_id=clinic.id,
                user_id=user.id,
                first_name="Gate",
                last_name="Driver",
                status=StaffStatus.ACTIVE,
            )

            vehicle = AmbulanceVehicle(
                clinic_id=clinic.id,
                plate_number="G9-AMB-001",
                equipment_level=EquipmentLevel.BLS,
                capacity=1,
                status=VehicleStatus.AVAILABLE,
            )

            trip_one = AmbulanceTrip(
                clinic_id=clinic.id,
                trip_type=TripType.NON_EMERGENCY,
                status=TripStatus.REQUESTED,
                pickup_address="Gate 9 Pickup A",
                destination_address="Gate 9 Destination A",
            )

            trip_two = AmbulanceTrip(
                clinic_id=clinic.id,
                trip_type=TripType.NON_EMERGENCY,
                status=TripStatus.REQUESTED,
                pickup_address="Gate 9 Pickup B",
                destination_address="Gate 9 Destination B",
            )

            db.session.add_all(
                [
                    driver,
                    vehicle,
                    trip_one,
                    trip_two,
                ]
            )

            db.session.commit()

            vehicle_id = vehicle.id
            driver_id = driver.id
            trip_one_id = trip_one.id
            trip_two_id = trip_two.id
            clinic_id = clinic.id

        from app.tests.core.concurrency.concurrency_harness import (
            PostgresConcurrencyHarness,
        )

        harness = PostgresConcurrencyHarness(
            database_url
        )

        def dispatch(worker_index):
            trip_id = (
                trip_one_id
                if worker_index == 0
                else trip_two_id
            )

            try:
                result = ambulance_service.dispatch_trip(
                    trip_id=trip_id,
                    vehicle_id=vehicle_id,
                    driver_id=driver_id,
                )

                return {
                    "worker_index": worker_index,
                    "trip_id": trip_id,
                    "outcome": "accepted",
                    "vehicle_id": result.vehicle_id,
                    "status": result.status.value,
                }

            except Exception as exc:
                return {
                    "worker_index": worker_index,
                    "trip_id": trip_id,
                    "outcome": "rejected",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }

        results = harness.run_flask(
            app,
            dispatch,
        )

        assert len(results) == 2

        assert all(
            result.error is None
            for result in results
        )

        backend_pids = {
            result.backend_pid
            for result in results
        }

        assert len(backend_pids) == 2

        values = [
            result.value
            for result in results
        ]

        accepted = [
            value
            for value in values
            if value["outcome"] == "accepted"
        ]

        rejected = [
            value
            for value in values
            if value["outcome"] == "rejected"
        ]

        assert len(accepted) == 1
        assert accepted[0]["vehicle_id"] == vehicle_id
        assert accepted[0]["status"] == (
            TripStatus.DISPATCHED.value
        )

        assert len(rejected) == 1
        assert rejected[0]["error_type"] == (
            ConflictError.__name__
        )

        with app.app_context():
            final_vehicle = db.session.execute(
                select(AmbulanceVehicle).where(
                    AmbulanceVehicle.id == vehicle_id
                )
            ).scalar_one()

            assert final_vehicle.status == (
                VehicleStatus.ON_TRIP
            )

            dispatched_trips = db.session.execute(
                select(AmbulanceTrip).where(
                    AmbulanceTrip.id.in_(
                        [
                            trip_one_id,
                            trip_two_id,
                        ]
                    )
                )
            ).scalars().all()

            assert sum(
                trip.status == TripStatus.DISPATCHED
                for trip in dispatched_trips
            ) == 1

            assert sum(
                trip.vehicle_id == vehicle_id
                for trip in dispatched_trips
            ) == 1

            assert all(
                trip.status == TripStatus.REQUESTED
                or trip.status == TripStatus.DISPATCHED
                for trip in dispatched_trips
            )

    finally:
        if harness is not None:
            harness.close()

        with app.app_context():
            db.session.rollback()
            db.drop_all()
            db.session.remove()

            try:
                db.engine.dispose()
            except Exception:
                pass

        config_by_name["testing"].SQLALCHEMY_DATABASE_URI = (
            original_database_url
        )

        extensions.redis_client = (
            original_redis_client
        )