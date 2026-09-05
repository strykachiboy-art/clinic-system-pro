from datetime import datetime
from types import SimpleNamespace

import pytest

from app.core.enums.ambulance_enums import (
    TripStatus,
    TripType,
)

from app.core.enums.role_enums import Role

import app.modules.ambulance.routes.ambulance_trip_routes as trip_route


# ============================================================
# HELPERS
# ============================================================


def make_trip(
    clinic_id=1,
    trip_id=1,
    vehicle_id=10,
    patient_id=None,
    driver_id=None,
    paramedic_id=None,
    admission_id=None,
    trip_type=None,
    status=None,
    pickup_address="123 Pickup Street",
    pickup_lat=4.8156,
    pickup_lng=7.0498,
    destination_address="456 Destination Street",
    destination_lat=4.8200,
    destination_lng=7.0600,
    notes="Test ambulance trip",
    invoice_id=None,
):
    if trip_type is None:
        trip_type = list(TripType)[0]

    if status is None:
        status = TripStatus.REQUESTED

    now = datetime(2026, 1, 1, 12, 0, 0)

    return SimpleNamespace(
        id=trip_id,
        clinic_id=clinic_id,
        vehicle_id=vehicle_id,
        patient_id=patient_id,
        driver_id=driver_id,
        paramedic_id=paramedic_id,
        admission_id=admission_id,
        trip_type=trip_type,
        status=status,
        pickup_address=pickup_address,
        pickup_lat=pickup_lat,
        pickup_lng=pickup_lng,
        destination_address=destination_address,
        destination_lat=destination_lat,
        destination_lng=destination_lng,
        created_at=now,
        updated_at=now,
        requested_at=now,
        dispatched_at=None,
        pickup_at=None,
        completed_at=None,
        cancelled_at=None,
        cancellation_reason=None,
        notes=notes,
        invoice_id=invoice_id,
    )


class FakePayload:
    def __init__(self, **data):
        self._data = data

        for key, value in data.items():
            setattr(self, key, value)

    def model_dump(self):
        return dict(self._data)


# ============================================================
# REQUEST TRIP
# ============================================================


def test_create_ambulance_trip_success(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.ADMIN,
    )

    trip = make_trip(
        clinic_id=clinic.id,
        trip_id=1,
        status=TripStatus.REQUESTED,
    )

    payload = FakePayload(
        clinic_id=clinic.id,
        trip_type=trip.trip_type,
        pickup_address="123 Pickup Street",
        pickup_lat=4.8156,
        pickup_lng=7.0498,
        destination_address="456 Destination Street",
        destination_lat=4.8200,
        destination_lng=7.0600,
        notes="Emergency transfer",
    )

    called = {}

    def fake_request_trip(**kwargs):
        called.update(kwargs)
        return trip

    monkeypatch.setattr(
        trip_route,
        "_payload",
        lambda schema: payload,
    )

    monkeypatch.setattr(
        trip_route,
        "request_trip",
        fake_request_trip,
    )

    response = client.post(
        "/api/ambulance/trips",
        json={
            "clinic_id": clinic.id,
            "trip_type": trip.trip_type.value,
            "pickup_address": "123 Pickup Street",
            "pickup_lat": 4.8156,
            "pickup_lng": 7.0498,
            "destination_address": "456 Destination Street",
            "destination_lat": 4.8200,
            "destination_lng": 7.0600,
            "notes": "Emergency transfer",
        },
        headers=headers,
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == trip.id
    assert body["data"]["clinic_id"] == clinic.id
    assert body["data"]["status"] == trip.status.value
    assert body["data"]["trip_type"] == trip.trip_type.value
    assert body["data"]["pickup_address"] == (
        "123 Pickup Street"
    )
    assert body["data"]["destination_address"] == (
        "456 Destination Street"
    )

    assert called["clinic_id"] == clinic.id
    assert called["trip_type"] == trip.trip_type
    assert called["pickup_address"] == (
        "123 Pickup Street"
    )


def test_create_ambulance_trip_requires_management_role(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.DRIVER,
    )

    monkeypatch.setattr(
        trip_route,
        "request_trip",
        lambda **kwargs: pytest.fail(
            "request_trip should not be called"
        ),
    )

    response = client.post(
        "/api/ambulance/trips",
        json={},
        headers=headers,
    )

    assert response.status_code == 403

    body = response.get_json()
    assert body["error"] == "Insufficient permissions"


def test_create_ambulance_trip_unauthenticated(
    client,
):
    response = client.post(
        "/api/ambulance/trips",
        json={},
    )

    assert response.status_code in (401, 422)

    body = response.get_json()
    assert "msg" in body


def test_create_ambulance_trip_payload_validation_error(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.ADMIN,
    )

    validation_response = (
        trip_route.jsonify(
            {
                "success": False,
                "error": [
                    {
                        "type": "missing",
                        "loc": ["body", "clinic_id"],
                        "msg": "Field required",
                    }
                ],
            }
        ),
        422,
    )

    monkeypatch.setattr(
        trip_route,
        "_payload",
        lambda schema: validation_response,
    )

    response = client.post(
        "/api/ambulance/trips",
        json={},
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"][0]["type"] == "missing"


# ============================================================
# LIST TRIPS
# ============================================================


def test_list_ambulance_trips_success(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.ADMIN,
    )

    trips = [
        make_trip(
            clinic_id=clinic.id,
            trip_id=1,
        ),
        make_trip(
            clinic_id=clinic.id,
            trip_id=2,
        ),
    ]

    called = {}

    def fake_list_trips(**kwargs):
        called.update(kwargs)
        return trips

    monkeypatch.setattr(
        trip_route,
        "list_trips",
        fake_list_trips,
    )

    response = client.get(
        f"/api/ambulance/trips?clinic_id={clinic.id}",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert len(body["data"]) == 2

    assert body["data"][0]["id"] == 1
    assert body["data"][1]["id"] == 2

    assert called["clinic_id"] == clinic.id
    assert called["status"] is None


def test_list_ambulance_trips_with_status_filter(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.AMBULANCE_DISPATCHER,
    )

    trip = make_trip(
        clinic_id=clinic.id,
        status=TripStatus.DISPATCHED,
    )

    called = {}

    def fake_list_trips(**kwargs):
        called.update(kwargs)
        return [trip]

    monkeypatch.setattr(
        trip_route,
        "list_trips",
        fake_list_trips,
    )

    response = client.get(
        (
            f"/api/ambulance/trips"
            f"?clinic_id={clinic.id}"
            f"&status={TripStatus.DISPATCHED.value}"
        ),
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert len(body["data"]) == 1
    assert body["data"][0]["status"] == (
        TripStatus.DISPATCHED.value
    )

    assert called["clinic_id"] == clinic.id
    assert called["status"] == TripStatus.DISPATCHED


def test_list_ambulance_trips_missing_clinic_id(
    client,
    make_authenticated_staff,
    clinic,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.ADMIN,
    )

    response = client.get(
        "/api/ambulance/trips",
        headers=headers,
    )

    assert response.status_code == 400

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "clinic_id query parameter is required"
    )


def test_list_ambulance_trips_invalid_status(
    client,
    make_authenticated_staff,
    clinic,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.ADMIN,
    )

    response = client.get(
        (
            f"/api/ambulance/trips"
            f"?clinic_id={clinic.id}"
            f"&status=NOT_A_REAL_STATUS"
        ),
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Invalid trip status: NOT_A_REAL_STATUS"
    )


def test_list_ambulance_trips_allows_crew_role(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.PARAMEDIC,
    )

    monkeypatch.setattr(
        trip_route,
        "list_trips",
        lambda **kwargs: [],
    )

    response = client.get(
        f"/api/ambulance/trips?clinic_id={clinic.id}",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"] == []


def test_list_ambulance_trips_denies_unapproved_role(
    client,
    make_authenticated_staff,
    clinic,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.NURSE,
    )

    response = client.get(
        f"/api/ambulance/trips?clinic_id={clinic.id}",
        headers=headers,
    )

    assert response.status_code == 403

    body = response.get_json()
    assert body["error"] == "Insufficient permissions"


# ============================================================
# GET TRIP
# ============================================================


def test_get_ambulance_trip_success(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.AMBULANCE_COORDINATOR,
    )

    trip = make_trip(
        clinic_id=clinic.id,
        trip_id=7,
    )

    called = {}

    def fake_get_trip(trip_id):
        called["trip_id"] = trip_id
        return trip

    monkeypatch.setattr(
        trip_route,
        "get_trip",
        fake_get_trip,
    )

    response = client.get(
        "/api/ambulance/trips/7",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 7

    assert called["trip_id"] == 7


def test_get_ambulance_trip_allows_driver(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.DRIVER,
    )

    trip = make_trip(
        clinic_id=clinic.id,
        trip_id=8,
    )

    monkeypatch.setattr(
        trip_route,
        "get_trip",
        lambda trip_id: trip,
    )

    response = client.get(
        "/api/ambulance/trips/8",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True


def test_get_ambulance_trip_denies_unapproved_role(
    client,
    make_authenticated_staff,
    clinic,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.NURSE,
    )

    response = client.get(
        "/api/ambulance/trips/1",
        headers=headers,
    )

    assert response.status_code == 403

    body = response.get_json()

    assert body["error"] == "Insufficient permissions"


def test_get_ambulance_trip_unauthenticated(
    client,
):
    response = client.get(
        "/api/ambulance/trips/1",
    )

    assert response.status_code in (401, 422)

    body = response.get_json()
    assert "msg" in body


# ============================================================
# DISPATCH
# ============================================================


def test_dispatch_ambulance_trip_success(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.AMBULANCE_DISPATCHER,
    )

    trip = make_trip(
        clinic_id=clinic.id,
        trip_id=10,
        status=TripStatus.DISPATCHED,
        vehicle_id=20,
        driver_id=30,
        paramedic_id=40,
    )

    payload = FakePayload(
        vehicle_id=20,
        driver_id=30,
        paramedic_id=40,
    )

    called = {}

    def fake_dispatch_trip(**kwargs):
        called.update(kwargs)
        return trip

    monkeypatch.setattr(
        trip_route,
        "_payload",
        lambda schema: payload,
    )

    monkeypatch.setattr(
        trip_route,
        "dispatch_trip",
        fake_dispatch_trip,
    )

    response = client.post(
        "/api/ambulance/trips/10/dispatch",
        json={
            "vehicle_id": 20,
            "driver_id": 30,
            "paramedic_id": 40,
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 10
    assert body["data"]["status"] == (
        TripStatus.DISPATCHED.value
    )
    assert body["data"]["vehicle_id"] == 20
    assert body["data"]["driver_id"] == 30
    assert body["data"]["paramedic_id"] == 40

    assert called["trip_id"] == 10
    assert called["vehicle_id"] == 20
    assert called["driver_id"] == 30
    assert called["paramedic_id"] == 40


def test_dispatch_ambulance_trip_payload_validation_error(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.ADMIN,
    )

    validation_response = (
        trip_route.jsonify(
            {
                "success": False,
                "error": [
                    {
                        "type": "missing",
                        "loc": ["body", "vehicle_id"],
                        "msg": "Field required",
                    }
                ],
            }
        ),
        422,
    )

    monkeypatch.setattr(
        trip_route,
        "_payload",
        lambda schema: validation_response,
    )

    response = client.post(
        "/api/ambulance/trips/1/dispatch",
        json={},
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"][0]["type"] == "missing"


def test_dispatch_ambulance_trip_requires_management_role(
    client,
    make_authenticated_staff,
    clinic,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.DRIVER,
    )

    response = client.post(
        "/api/ambulance/trips/1/dispatch",
        json={},
        headers=headers,
    )

    assert response.status_code == 403

    body = response.get_json()

    assert body["error"] == "Insufficient permissions"


# ============================================================
# ADVANCE STATUS
# ============================================================


def test_update_ambulance_trip_status_success(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.DRIVER,
    )

    trip = make_trip(
        clinic_id=clinic.id,
        trip_id=11,
        status=TripStatus.EN_ROUTE_TO_PICKUP,
    )

    payload = FakePayload(
        status=TripStatus.EN_ROUTE_TO_PICKUP,
    )

    called = {}

    def fake_update_trip_status(
        trip_id,
        new_status,
    ):
        called["trip_id"] = trip_id
        called["new_status"] = new_status
        return trip

    monkeypatch.setattr(
        trip_route,
        "_payload",
        lambda schema: payload,
    )

    monkeypatch.setattr(
        trip_route,
        "update_trip_status",
        fake_update_trip_status,
    )

    response = client.patch(
        "/api/ambulance/trips/11/status",
        json={
            "status": TripStatus.EN_ROUTE_TO_PICKUP.value,
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 11
    assert body["data"]["status"] == (
        TripStatus.EN_ROUTE_TO_PICKUP.value
    )

    assert called["trip_id"] == 11
    assert called["new_status"] == (
        TripStatus.EN_ROUTE_TO_PICKUP
    )


def test_update_ambulance_trip_status_payload_validation_error(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.PARAMEDIC,
    )

    validation_response = (
        trip_route.jsonify(
            {
                "success": False,
                "error": [
                    {
                        "type": "missing",
                        "loc": ["body", "status"],
                        "msg": "Field required",
                    }
                ],
            }
        ),
        422,
    )

    monkeypatch.setattr(
        trip_route,
        "_payload",
        lambda schema: validation_response,
    )

    response = client.patch(
        "/api/ambulance/trips/1/status",
        json={},
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"][0]["type"] == "missing"


def test_update_ambulance_trip_status_requires_crew_role(
    client,
    make_authenticated_staff,
    clinic,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.NURSE,
    )

    response = client.patch(
        "/api/ambulance/trips/1/status",
        json={
            "status": TripStatus.DISPATCHED.value,
        },
        headers=headers,
    )

    assert response.status_code == 403

    body = response.get_json()

    assert body["error"] == "Insufficient permissions"


# ============================================================
# LINK PATIENT
# ============================================================


def test_link_ambulance_trip_patient_success(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.ADMIN,
    )

    trip = make_trip(
        clinic_id=clinic.id,
        trip_id=12,
        patient_id=55,
    )

    payload = FakePayload(
        patient_id=55,
    )

    called = {}

    def fake_link_patient(
        trip_id,
        patient_id,
    ):
        called["trip_id"] = trip_id
        called["patient_id"] = patient_id
        return trip

    monkeypatch.setattr(
        trip_route,
        "_payload",
        lambda schema: payload,
    )

    monkeypatch.setattr(
        trip_route,
        "link_patient",
        fake_link_patient,
    )

    response = client.post(
        "/api/ambulance/trips/12/patient",
        json={
            "patient_id": 55,
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 12
    assert body["data"]["patient_id"] == 55

    assert called["trip_id"] == 12
    assert called["patient_id"] == 55


def test_link_ambulance_trip_patient_payload_validation_error(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.ADMIN,
    )

    validation_response = (
        trip_route.jsonify(
            {
                "success": False,
                "error": [
                    {
                        "type": "missing",
                        "loc": ["body", "patient_id"],
                        "msg": "Field required",
                    }
                ],
            }
        ),
        422,
    )

    monkeypatch.setattr(
        trip_route,
        "_payload",
        lambda schema: validation_response,
    )

    response = client.post(
        "/api/ambulance/trips/1/patient",
        json={},
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"][0]["type"] == "missing"


def test_link_ambulance_trip_patient_requires_management_role(
    client,
    make_authenticated_staff,
    clinic,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.DRIVER,
    )

    response = client.post(
        "/api/ambulance/trips/1/patient",
        json={
            "patient_id": 55,
        },
        headers=headers,
    )

    assert response.status_code == 403

    body = response.get_json()

    assert body["error"] == "Insufficient permissions"


# ============================================================
# COMPLETE
# ============================================================


def test_complete_ambulance_trip_success(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.DRIVER,
    )

    trip = make_trip(
        clinic_id=clinic.id,
        trip_id=13,
        patient_id=55,
        status=TripStatus.COMPLETED,
    )

    called = {}

    def fake_complete_trip(trip_id):
        called["trip_id"] = trip_id
        return trip

    monkeypatch.setattr(
        trip_route,
        "complete_trip",
        fake_complete_trip,
    )

    response = client.post(
        "/api/ambulance/trips/13/complete",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 13
    assert body["data"]["patient_id"] == 55
    assert body["data"]["status"] == (
        TripStatus.COMPLETED.value
    )

    assert called["trip_id"] == 13


def test_complete_ambulance_trip_requires_crew_role(
    client,
    make_authenticated_staff,
    clinic,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.NURSE,
    )

    response = client.post(
        "/api/ambulance/trips/1/complete",
        headers=headers,
    )

    assert response.status_code == 403

    body = response.get_json()

    assert body["error"] == "Insufficient permissions"


def test_complete_ambulance_trip_unauthenticated(
    client,
):
    response = client.post(
        "/api/ambulance/trips/1/complete",
    )

    assert response.status_code in (401, 422)

    body = response.get_json()
    assert "msg" in body


# ============================================================
# LINK INVOICE
# ============================================================


def test_link_ambulance_trip_invoice_success(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.ADMIN,
    )

    trip = make_trip(
        clinic_id=clinic.id,
        trip_id=14,
        patient_id=55,
        status=TripStatus.COMPLETED,
        invoice_id=99,
    )

    payload = FakePayload(
        invoice_id=99,
    )

    called = {}

    def fake_link_invoice(
        trip_id,
        invoice_id,
    ):
        called["trip_id"] = trip_id
        called["invoice_id"] = invoice_id
        return trip

    monkeypatch.setattr(
        trip_route,
        "_payload",
        lambda schema: payload,
    )

    monkeypatch.setattr(
        trip_route,
        "link_invoice",
        fake_link_invoice,
    )

    response = client.post(
        "/api/ambulance/trips/14/invoice",
        json={
            "invoice_id": 99,
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 14
    assert body["data"]["invoice_id"] == 99

    assert called["trip_id"] == 14
    assert called["invoice_id"] == 99


def test_link_ambulance_trip_invoice_payload_validation_error(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.ADMIN,
    )

    validation_response = (
        trip_route.jsonify(
            {
                "success": False,
                "error": [
                    {
                        "type": "missing",
                        "loc": ["body", "invoice_id"],
                        "msg": "Field required",
                    }
                ],
            }
        ),
        422,
    )

    monkeypatch.setattr(
        trip_route,
        "_payload",
        lambda schema: validation_response,
    )

    response = client.post(
        "/api/ambulance/trips/1/invoice",
        json={},
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"][0]["type"] == "missing"


def test_link_ambulance_trip_invoice_requires_management_role(
    client,
    make_authenticated_staff,
    clinic,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.PARAMEDIC,
    )

    response = client.post(
        "/api/ambulance/trips/1/invoice",
        json={
            "invoice_id": 99,
        },
        headers=headers,
    )

    assert response.status_code == 403

    body = response.get_json()

    assert body["error"] == "Insufficient permissions"


# ============================================================
# CANCEL
# ============================================================


def test_cancel_ambulance_trip_success(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.AMBULANCE_COORDINATOR,
    )

    trip = make_trip(
        clinic_id=clinic.id,
        trip_id=15,
        status=TripStatus.CANCELLED,
    )

    payload = FakePayload(
        reason="Patient no longer requires transport",
    )

    called = {}

    def fake_cancel_trip(
        trip_id,
        reason,
    ):
        called["trip_id"] = trip_id
        called["reason"] = reason
        return trip

    monkeypatch.setattr(
        trip_route,
        "_payload",
        lambda schema: payload,
    )

    monkeypatch.setattr(
        trip_route,
        "cancel_trip",
        fake_cancel_trip,
    )

    response = client.post(
        "/api/ambulance/trips/15/cancel",
        json={
            "reason": "Patient no longer requires transport",
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 15
    assert body["data"]["status"] == (
        TripStatus.CANCELLED.value
    )

    assert called["trip_id"] == 15
    assert called["reason"] == (
        "Patient no longer requires transport"
    )


def test_cancel_ambulance_trip_payload_validation_error(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.ADMIN,
    )

    validation_response = (
        trip_route.jsonify(
            {
                "success": False,
                "error": [
                    {
                        "type": "missing",
                        "loc": ["body", "reason"],
                        "msg": "Field required",
                    }
                ],
            }
        ),
        422,
    )

    monkeypatch.setattr(
        trip_route,
        "_payload",
        lambda schema: validation_response,
    )

    response = client.post(
        "/api/ambulance/trips/1/cancel",
        json={},
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"][0]["type"] == "missing"


def test_cancel_ambulance_trip_requires_management_role(
    client,
    make_authenticated_staff,
    clinic,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.DRIVER,
    )

    response = client.post(
        "/api/ambulance/trips/1/cancel",
        json={
            "reason": "Test cancellation",
        },
        headers=headers,
    )

    assert response.status_code == 403

    body = response.get_json()

    assert body["error"] == "Insufficient permissions"


# ============================================================
# SERIALIZATION
# ============================================================


def test_trip_data_serializes_all_fields(
    app,
):
    trip = make_trip(
        clinic_id=5,
        trip_id=20,
        vehicle_id=30,
        patient_id=40,
        driver_id=50,
        paramedic_id=60,
        admission_id=70,
        invoice_id=80,
    )

    trip.dispatched_at = datetime(
        2026,
        1,
        1,
        13,
        0,
        0,
    )

    trip.pickup_at = datetime(
        2026,
        1,
        1,
        13,
        30,
        0,
    )

    data = trip_route._trip_data(trip)

    assert data["id"] == 20
    assert data["clinic_id"] == 5
    assert data["vehicle_id"] == 30
    assert data["patient_id"] == 40
    assert data["driver_id"] == 50
    assert data["paramedic_id"] == 60
    assert data["admission_id"] == 70

    assert data["trip_type"] == trip.trip_type.value
    assert data["status"] == trip.status.value

    assert data["pickup_address"] == (
        "123 Pickup Street"
    )
    assert data["pickup_lat"] == 4.8156
    assert data["pickup_lng"] == 7.0498

    assert data["destination_address"] == (
        "456 Destination Street"
    )
    assert data["destination_lat"] == 4.82
    assert data["destination_lng"] == 7.06

    assert data["created_at"] == (
        "2026-01-01T12:00:00"
    )
    assert data["updated_at"] == (
        "2026-01-01T12:00:00"
    )
    assert data["requested_at"] == (
        "2026-01-01T12:00:00"
    )

    assert data["dispatched_at"] == (
        "2026-01-01T13:00:00"
    )

    assert data["pickup_at"] == (
        "2026-01-01T13:30:00"
    )

    assert data["completed_at"] is None
    assert data["cancelled_at"] is None
    assert data["cancellation_reason"] is None

    assert data["notes"] == "Test ambulance trip"
    assert data["invoice_id"] == 80


def test_trip_data_handles_optional_fields(
    app,
):
    trip = make_trip()

    trip.vehicle_id = None
    trip.patient_id = None
    trip.driver_id = None
    trip.paramedic_id = None
    trip.admission_id = None
    trip.pickup_lat = None
    trip.pickup_lng = None
    trip.destination_lat = None
    trip.destination_lng = None
    trip.created_at = None
    trip.updated_at = None
    trip.requested_at = None
    trip.dispatched_at = None
    trip.pickup_at = None
    trip.completed_at = None
    trip.cancelled_at = None
    trip.invoice_id = None

    data = trip_route._trip_data(trip)

    assert data["vehicle_id"] is None
    assert data["patient_id"] is None
    assert data["driver_id"] is None
    assert data["paramedic_id"] is None
    assert data["admission_id"] is None

    assert data["pickup_lat"] is None
    assert data["pickup_lng"] is None
    assert data["destination_lat"] is None
    assert data["destination_lng"] is None

    assert data["created_at"] is None
    assert data["updated_at"] is None
    assert data["requested_at"] is None
    assert data["dispatched_at"] is None
    assert data["pickup_at"] is None
    assert data["completed_at"] is None
    assert data["cancelled_at"] is None

    assert data["invoice_id"] is None