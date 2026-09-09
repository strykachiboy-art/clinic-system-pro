# app/tests/modules/ambulance/test_ambulance_trip_routes.py

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.enums.ambulance_enums import (
    TripStatus,
    TripType,
)
from app.core.enums.role_enums import Role
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.ambulance.routes import ambulance_trip_routes
from app.modules.ambulance.schemas.ambulance_trip_schema import (
    AmbulanceTripCancelSchema,
)


def make_trip(
    trip_id=1,
    clinic_id=10,
    vehicle_id=20,
    patient_id=30,
    driver_id=40,
    paramedic_id=50,
    admission_id=60,
    trip_type=TripType.NON_EMERGENCY,
    status=TripStatus.REQUESTED,
):
    now = datetime.now(timezone.utc)

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
        pickup_address="Pickup address",
        pickup_lat=4.8156,
        pickup_lng=7.0498,
        destination_address="Destination address",
        destination_lat=4.8242,
        destination_lng=7.0336,
        requested_at=now,
        dispatched_at=now,
        pickup_at=now,
        completed_at=now,
        cancelled_at=now,
        cancellation_reason=None,
        notes="Ambulance test trip",
        invoice_id=None,
    )


def make_pagination(
    items,
    *,
    page=1,
    per_page=50,
    total=None,
):
    total = len(items) if total is None else total

    pages = (
        (total + per_page - 1) // per_page
        if total
        else 0
    )

    return SimpleNamespace(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        has_next=page < pages,
        has_prev=page > 1,
    )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_trip_data_serializes_trip():
    trip = make_trip()

    result = ambulance_trip_routes._trip_data(trip)

    assert result["id"] == trip.id
    assert result["clinic_id"] == trip.clinic_id
    assert result["vehicle_id"] == trip.vehicle_id
    assert result["patient_id"] == trip.patient_id
    assert result["driver_id"] == trip.driver_id
    assert result["paramedic_id"] == trip.paramedic_id
    assert result["admission_id"] == trip.admission_id

    assert result["trip_type"] == TripType.NON_EMERGENCY.value
    assert result["status"] == TripStatus.REQUESTED.value

    assert result["pickup_address"] == trip.pickup_address
    assert result["destination_address"] == (
        trip.destination_address
    )
    assert result["notes"] == trip.notes
    assert result["invoice_id"] == trip.invoice_id

    assert result["pickup_lat"] == float(trip.pickup_lat)
    assert result["pickup_lng"] == float(trip.pickup_lng)

    assert result["destination_lat"] == float(
        trip.destination_lat
    )
    assert result["destination_lng"] == float(
        trip.destination_lng
    )

    assert result["requested_at"] == (
        trip.requested_at.isoformat()
    )
    assert result["dispatched_at"] == (
        trip.dispatched_at.isoformat()
    )
    assert result["pickup_at"] == (
        trip.pickup_at.isoformat()
    )
    assert result["completed_at"] == (
        trip.completed_at.isoformat()
    )
    assert result["cancelled_at"] == (
        trip.cancelled_at.isoformat()
    )


def test_trip_data_handles_none_optional_values():
    trip = make_trip()

    trip.vehicle_id = None
    trip.patient_id = None
    trip.driver_id = None
    trip.paramedic_id = None
    trip.admission_id = None
    trip.trip_type = None
    trip.status = None
    trip.pickup_lat = None
    trip.pickup_lng = None
    trip.destination_lat = None
    trip.destination_lng = None
    trip.requested_at = None
    trip.dispatched_at = None
    trip.pickup_at = None
    trip.completed_at = None
    trip.cancelled_at = None

    result = ambulance_trip_routes._trip_data(trip)

    assert result["vehicle_id"] is None
    assert result["patient_id"] is None
    assert result["driver_id"] is None
    assert result["paramedic_id"] is None
    assert result["admission_id"] is None
    assert result["trip_type"] is None
    assert result["status"] is None
    assert result["pickup_lat"] is None
    assert result["pickup_lng"] is None
    assert result["destination_lat"] is None
    assert result["destination_lng"] is None
    assert result["requested_at"] is None
    assert result["dispatched_at"] is None
    assert result["pickup_at"] is None
    assert result["completed_at"] is None
    assert result["cancelled_at"] is None


# ---------------------------------------------------------------------------
# Create trip
# ---------------------------------------------------------------------------


def test_create_ambulance_trip_success(
    app,
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(clinic=clinic)

    trip = make_trip(
        clinic_id=clinic.id,
        status=TripStatus.REQUESTED,
    )

    service = Mock(return_value=trip)

    monkeypatch.setattr(
        ambulance_trip_routes,
        "request_trip",
        service,
    )

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/trips",
        json={
            "trip_type": TripType.NON_EMERGENCY.value,
            "pickup_address": "Pickup address",
            "destination_address": "Destination address",
        },
        headers=headers,
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == trip.id
    assert body["data"]["trip_type"] == (
        TripType.NON_EMERGENCY.value
    )

    assert service.call_args.kwargs["clinic_id"] == (
        user.clinic_id
    )
    assert service.call_args.kwargs["clinic_id"] != 999


def test_create_ambulance_trip_passes_payload_to_service(
    app,
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(clinic=clinic)

    trip = make_trip(
        clinic_id=clinic.id,
        trip_type=TripType.EMERGENCY_PICKUP,
    )

    service = Mock(return_value=trip)

    monkeypatch.setattr(
        ambulance_trip_routes,
        "request_trip",
        service,
    )

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/trips",
        json={
            "trip_type": TripType.EMERGENCY_PICKUP.value,
            "pickup_address": "Pickup",
            "destination_address": "Destination",
            "notes": "Urgent transport",
        },
        headers=headers,
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True

    kwargs = service.call_args.kwargs

    assert kwargs["clinic_id"] == clinic.id
    assert kwargs["trip_type"] == TripType.EMERGENCY_PICKUP
    assert kwargs["pickup_address"] == "Pickup"
    assert kwargs["destination_address"] == "Destination"
    assert kwargs["notes"] == "Urgent transport"


def test_create_ambulance_trip_rejects_invalid_payload(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    user = make_user(clinic=clinic)

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/trips",
        json={},
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Invalid request payload"
    assert "details" in body


def test_create_ambulance_trip_rejects_non_object_json(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    user = make_user(clinic=clinic)

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/trips",
        data="[]",
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Request body must be a JSON object"
    )


def test_create_ambulance_trip_maps_domain_error(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(clinic=clinic)

    monkeypatch.setattr(
        ambulance_trip_routes,
        "request_trip",
        Mock(
            side_effect=ConflictError(
                "Ambulance trip already exists"
            )
        ),
    )

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/trips",
        json={
            "trip_type": TripType.NON_EMERGENCY.value,
            "pickup_address": "Pickup address",
            "destination_address": "Destination address",
        },
        headers=headers,
    )

    assert response.status_code == 409

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Ambulance trip already exists"
    )


# ---------------------------------------------------------------------------
# List trips
# ---------------------------------------------------------------------------


def test_get_ambulance_trips_success(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(clinic=clinic)

    trips = [
        make_trip(
            trip_id=1,
            clinic_id=clinic.id,
            status=TripStatus.REQUESTED,
        ),
        make_trip(
            trip_id=2,
            clinic_id=clinic.id,
            status=TripStatus.DISPATCHED,
        ),
    ]

    pagination = make_pagination(
        trips,
        page=1,
        per_page=50,
        total=2,
    )

    service = Mock(return_value=pagination)

    monkeypatch.setattr(
        ambulance_trip_routes,
        "list_trips",
        service,
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/ambulance/trips",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True

    data = body["data"]

    assert len(data["items"]) == 2
    assert data["items"][0]["id"] == 1
    assert data["items"][1]["id"] == 2
    assert data["total"] == 2
    assert data["page"] == 1
    assert data["per_page"] == 50
    assert data["pages"] == 1
    assert data["has_next"] is False
    assert data["has_prev"] is False

    service.assert_called_once_with(
        clinic_id=clinic.id,
        status=None,
        page=1,
        per_page=50,
    )


def test_get_ambulance_trips_supports_pagination(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(clinic=clinic)

    trips = [
        make_trip(
            trip_id=51,
            clinic_id=clinic.id,
        ),
    ]

    pagination = make_pagination(
        trips,
        page=2,
        per_page=25,
        total=51,
    )

    service = Mock(return_value=pagination)

    monkeypatch.setattr(
        ambulance_trip_routes,
        "list_trips",
        service,
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/ambulance/trips",
        query_string={
            "page": "2",
            "per_page": "25",
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()
    data = body["data"]

    assert data["page"] == 2
    assert data["per_page"] == 25
    assert data["total"] == 51
    assert data["pages"] == 3
    assert data["has_next"] is True
    assert data["has_prev"] is True

    service.assert_called_once_with(
        clinic_id=clinic.id,
        status=None,
        page=2,
        per_page=25,
    )


def test_get_ambulance_trips_supports_status_filter(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(clinic=clinic)

    trip = make_trip(
        clinic_id=clinic.id,
        status=TripStatus.DISPATCHED,
    )

    service = Mock(
        return_value=make_pagination(
            [trip],
            total=1,
        )
    )

    monkeypatch.setattr(
        ambulance_trip_routes,
        "list_trips",
        service,
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/ambulance/trips",
        query_string={
            "status": TripStatus.DISPATCHED.value,
        },
        headers=headers,
    )

    assert response.status_code == 200

    service.assert_called_once_with(
        clinic_id=clinic.id,
        status=TripStatus.DISPATCHED,
        page=1,
        per_page=50,
    )


def test_get_ambulance_trips_rejects_invalid_status(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    user = make_user(clinic=clinic)

    headers = auth_headers_for(user)

    response = client.get(
        "/api/ambulance/trips",
        query_string={
            "status": "not-a-real-status",
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "Invalid trip status" in body["error"]


def test_get_ambulance_trips_rejects_empty_status(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    user = make_user(clinic=clinic)

    headers = auth_headers_for(user)

    response = client.get(
        "/api/ambulance/trips",
        query_string={"status": "   "},
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Trip status cannot be empty"


@pytest.mark.parametrize(
    "query_string",
    [
        {"page": "0"},
        {"page": "-1"},
        {"page": "abc"},
        {"page": ""},
        {"per_page": "0"},
        {"per_page": "-1"},
        {"per_page": "abc"},
        {"per_page": ""},
        {"per_page": "501"},
    ],
)
def test_get_ambulance_trips_rejects_invalid_pagination(
    client,
    clinic,
    make_user,
    auth_headers_for,
    query_string,
):
    user = make_user(clinic=clinic)

    headers = auth_headers_for(user)

    response = client.get(
        "/api/ambulance/trips",
        query_string=query_string,
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


# ---------------------------------------------------------------------------
# Get single trip
# ---------------------------------------------------------------------------


def test_get_ambulance_trip_success(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(clinic=clinic)

    trip = make_trip(
        trip_id=123,
        clinic_id=clinic.id,
    )

    service = Mock(return_value=trip)

    monkeypatch.setattr(
        ambulance_trip_routes,
        "get_trip",
        service,
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/ambulance/trips/123",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 123

    service.assert_called_once_with(123)


def test_get_ambulance_trip_maps_not_found(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(clinic=clinic)

    monkeypatch.setattr(
        ambulance_trip_routes,
        "get_trip",
        Mock(
            side_effect=NotFoundError(
                "Ambulance trip not found"
            )
        ),
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/ambulance/trips/999",
        headers=headers,
    )

    assert response.status_code == 404

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Ambulance trip not found"


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def test_dispatch_ambulance_trip_success(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(clinic=clinic)

    trip = make_trip(
        trip_id=1,
        clinic_id=clinic.id,
        status=TripStatus.DISPATCHED,
    )

    service = Mock(return_value=trip)

    monkeypatch.setattr(
        ambulance_trip_routes,
        "dispatch_trip",
        service,
    )

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/trips/1/dispatch",
        json={
            "vehicle_id": 20,
            "driver_id": 40,
            "paramedic_id": 50,
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 1

    service.assert_called_once_with(
        trip_id=1,
        vehicle_id=20,
        driver_id=40,
        paramedic_id=50,
    )


def test_dispatch_ambulance_trip_rejects_invalid_payload(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    user = make_user(clinic=clinic)

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/trips/1/dispatch",
        json={},
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Invalid request payload"


def test_dispatch_ambulance_trip_maps_domain_error(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(clinic=clinic)

    monkeypatch.setattr(
        ambulance_trip_routes,
        "dispatch_trip",
        Mock(
            side_effect=ConflictError(
                "Vehicle is not available"
            )
        ),
    )

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/trips/1/dispatch",
        json={
            "vehicle_id": 20,
            "driver_id": 40,
        },
        headers=headers,
    )

    assert response.status_code == 409

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Vehicle is not available"


# ---------------------------------------------------------------------------
# Status update
# ---------------------------------------------------------------------------


def test_update_ambulance_trip_status_success(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(clinic=clinic)

    trip = make_trip(
        trip_id=1,
        clinic_id=clinic.id,
        status=TripStatus.EN_ROUTE_TO_PICKUP,
    )

    service = Mock(return_value=trip)

    monkeypatch.setattr(
        ambulance_trip_routes,
        "update_trip_status",
        service,
    )

    headers = auth_headers_for(user)

    response = client.patch(
        "/api/ambulance/trips/1/status",
        json={
            "status": TripStatus.EN_ROUTE_TO_PICKUP.value,
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 1

    service.assert_called_once_with(
        trip_id=1,
        new_status=TripStatus.EN_ROUTE_TO_PICKUP,
    )


def test_update_ambulance_trip_status_rejects_invalid_payload(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    user = make_user(clinic=clinic)

    headers = auth_headers_for(user)

    response = client.patch(
        "/api/ambulance/trips/1/status",
        json={},
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Invalid request payload"


# ---------------------------------------------------------------------------
# Link patient
# ---------------------------------------------------------------------------


def test_link_ambulance_patient_success(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(clinic=clinic)

    trip = make_trip(
        trip_id=1,
        clinic_id=clinic.id,
        patient_id=30,
    )

    service = Mock(return_value=trip)

    monkeypatch.setattr(
        ambulance_trip_routes,
        "link_patient",
        service,
    )

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/trips/1/patient",
        json={
            "patient_id": 30,
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["patient_id"] == 30

    service.assert_called_once_with(
        trip_id=1,
        patient_id=30,
    )


def test_link_ambulance_patient_rejects_invalid_payload(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    user = make_user(clinic=clinic)

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/trips/1/patient",
        json={},
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Invalid request payload"


def test_link_ambulance_patient_maps_domain_error(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(clinic=clinic)

    monkeypatch.setattr(
        ambulance_trip_routes,
        "link_patient",
        Mock(
            side_effect=ValidationError(
                "Patient does not belong to this clinic"
            )
        ),
    )

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/trips/1/patient",
        json={
            "patient_id": 30,
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Patient does not belong to this clinic"
    )


# ---------------------------------------------------------------------------
# Complete
# ---------------------------------------------------------------------------


def test_complete_ambulance_trip_success(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(clinic=clinic)

    trip = make_trip(
        trip_id=1,
        clinic_id=clinic.id,
        status=TripStatus.COMPLETED,
    )

    service = Mock(return_value=trip)

    monkeypatch.setattr(
        ambulance_trip_routes,
        "complete_trip",
        service,
    )

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/trips/1/complete",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 1

    service.assert_called_once_with(1)


def test_complete_ambulance_trip_maps_domain_error(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(clinic=clinic)

    monkeypatch.setattr(
        ambulance_trip_routes,
        "complete_trip",
        Mock(
            side_effect=ConflictError(
                "Trip is not ready for completion"
            )
        ),
    )

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/trips/1/complete",
        headers=headers,
    )

    assert response.status_code == 409

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Trip is not ready for completion"
    )


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------


def test_link_ambulance_invoice_success(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(clinic=clinic)

    trip = make_trip(
        trip_id=1,
        clinic_id=clinic.id,
    )

    trip.invoice_id = 900

    service = Mock(return_value=trip)

    monkeypatch.setattr(
        ambulance_trip_routes,
        "link_invoice",
        service,
    )

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/trips/1/invoice",
        json={
            "invoice_id": 900,
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["invoice_id"] == 900

    service.assert_called_once_with(
        trip_id=1,
        invoice_id=900,
    )


def test_link_ambulance_invoice_rejects_invalid_payload(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    user = make_user(clinic=clinic)

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/trips/1/invoice",
        json={},
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Invalid request payload"


def test_link_ambulance_invoice_maps_domain_error(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(clinic=clinic)

    monkeypatch.setattr(
        ambulance_trip_routes,
        "link_invoice",
        Mock(
            side_effect=ConflictError(
                "Invoice is already linked"
            )
        ),
    )

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/trips/1/invoice",
        json={
            "invoice_id": 900,
        },
        headers=headers,
    )

    assert response.status_code == 409

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Invoice is already linked"


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


def test_cancel_ambulance_trip_success(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(clinic=clinic)

    trip = make_trip(
        trip_id=1,
        clinic_id=clinic.id,
        status=TripStatus.CANCELLED,
    )

    trip.cancellation_reason = (
        "Patient no longer requires transport"
    )

    service = Mock(return_value=trip)

    monkeypatch.setattr(
        ambulance_trip_routes,
        "cancel_trip",
        service,
    )

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/trips/1/cancel",
        json={
            "reason": "Patient no longer requires transport",
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 1
    assert body["data"]["cancellation_reason"] == (
        "Patient no longer requires transport"
    )

    service.assert_called_once_with(
        trip_id=1,
        reason="Patient no longer requires transport",
    )


def test_cancel_ambulance_trip_rejects_invalid_payload(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    user = make_user(clinic=clinic)

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/trips/1/cancel",
        json={"reason": 123},
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Invalid request payload"


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/ambulance/trips"),
        ("GET", "/api/ambulance/trips/1"),
        ("POST", "/api/ambulance/trips"),
        ("POST", "/api/ambulance/trips/1/dispatch"),
        ("PATCH", "/api/ambulance/trips/1/status"),
        ("POST", "/api/ambulance/trips/1/patient"),
        ("POST", "/api/ambulance/trips/1/complete"),
        ("POST", "/api/ambulance/trips/1/invoice"),
        ("POST", "/api/ambulance/trips/1/cancel"),
    ],
)
def test_ambulance_trip_routes_require_authentication(
    client,
    method,
    path,
):
    response = client.open(
        path,
        method=method,
    )

    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role",
    [
        Role.ADMIN,
        Role.AMBULANCE_COORDINATOR,
        Role.AMBULANCE_DISPATCHER,
    ],
)
def test_ambulance_management_roles_can_create_trip(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
    role,
):
    user = make_user(
        clinic=clinic,
        role=role,
    )

    trip = make_trip(clinic_id=clinic.id)

    monkeypatch.setattr(
        ambulance_trip_routes,
        "request_trip",
        Mock(return_value=trip),
    )

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/trips",
        json={
            "trip_type": TripType.NON_EMERGENCY.value,
            "pickup_address": "Pickup",
            "destination_address": "Destination",
        },
        headers=headers,
    )

    assert response.status_code == 201


@pytest.mark.parametrize(
    "role",
    [
        Role.DRIVER,
        Role.PARAMEDIC,
        Role.EMT,
    ],
)
def test_ambulance_management_routes_reject_crew_roles(
    client,
    clinic,
    make_user,
    auth_headers_for,
    role,
):
    user = make_user(
        clinic=clinic,
        role=role,
    )

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/trips",
        json={
            "trip_type": TripType.NON_EMERGENCY.value,
            "pickup_address": "Pickup address",
            "destination_address": "Destination address",
        },
        headers=headers,
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "role",
    [
        Role.ADMIN,
        Role.AMBULANCE_COORDINATOR,
        Role.AMBULANCE_DISPATCHER,
        Role.DRIVER,
        Role.PARAMEDIC,
        Role.EMT,
    ],
)
def test_ambulance_view_routes_allow_view_roles(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
    role,
):
    user = make_user(
        clinic=clinic,
        role=role,
    )

    monkeypatch.setattr(
        ambulance_trip_routes,
        "list_trips",
        Mock(
            return_value=make_pagination(
                [],
                total=0,
            )
        ),
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/ambulance/trips",
        headers=headers,
    )

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Authenticated-user validation
# ---------------------------------------------------------------------------


def test_ambulance_route_rejects_inactive_authenticated_user(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    user = make_user(
        clinic=clinic,
        is_active=False,
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/ambulance/trips",
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "User account is inactive"


def test_ambulance_route_rejects_user_without_clinic(
    client,
    make_user,
    auth_headers_for,
):
    user = make_user()

    headers = auth_headers_for(user)

    response = client.get(
        "/api/ambulance/trips",
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Authenticated user is not associated "
        "with a clinic"
    )


# ---------------------------------------------------------------------------
# Clinic isolation
# ---------------------------------------------------------------------------


def test_create_ambulance_trip_uses_authenticated_clinic(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(clinic=clinic)

    trip = make_trip(
        clinic_id=clinic.id,
    )

    service = Mock(return_value=trip)

    monkeypatch.setattr(
        ambulance_trip_routes,
        "request_trip",
        service,
    )

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/trips",
        json={
            "trip_type": TripType.NON_EMERGENCY.value,
            "pickup_address": "Pickup address",
            "destination_address": "Destination address",
        },
        headers=headers,
    )

    assert response.status_code == 201

    assert service.call_args.kwargs["clinic_id"] == (
        clinic.id
    )
    assert service.call_args.kwargs["clinic_id"] != 999


def test_get_ambulance_trip_does_not_accept_clinic_parameter(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(clinic=clinic)

    trip = make_trip(clinic_id=clinic.id)

    service = Mock(return_value=trip)

    monkeypatch.setattr(
        ambulance_trip_routes,
        "get_trip",
        service,
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/ambulance/trips/1?clinic_id=999",
        headers=headers,
    )

    assert response.status_code == 200
    service.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# DomainError response mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exception,status_code",
    [
        (
            ValidationError("Validation failed"),
            422,
        ),
        (
            ConflictError("Conflict occurred"),
            409,
        ),
        (
            NotFoundError("Trip not found"),
            404,
        ),
    ],
)
def test_ambulance_route_maps_domain_errors(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
    exception,
    status_code,
):
    user = make_user(clinic=clinic)

    monkeypatch.setattr(
        ambulance_trip_routes,
        "get_trip",
        Mock(side_effect=exception),
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/ambulance/trips/1",
        headers=headers,
    )

    assert response.status_code == status_code

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == str(exception)


# ---------------------------------------------------------------------------
# Direct helper validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "",
        "0",
        "-1",
        "abc",
        "  ",
    ],
)
def test_get_int_query_param_rejects_invalid_values(
    app,
    value,
):
    with app.test_request_context(
        "/api/ambulance/trips",
        query_string={"page": value},
    ):
        with pytest.raises(ValidationError):
            ambulance_trip_routes._get_int_query_param(
                "page",
                default=1,
            )


def test_get_int_query_param_uses_default(
    app,
):
    with app.test_request_context(
        "/api/ambulance/trips",
    ):
        result = ambulance_trip_routes._get_int_query_param(
            "page",
            default=1,
        )

    assert result == 1


def test_pagination_params_use_defaults(
    app,
):
    with app.test_request_context(
        "/api/ambulance/trips",
    ):
        page, per_page = (
            ambulance_trip_routes._pagination_params()
        )

    assert page == ambulance_trip_routes.DEFAULT_PAGE
    assert per_page == (
        ambulance_trip_routes.DEFAULT_PER_PAGE
    )


def test_pagination_params_enforce_max_per_page(
    app,
):
    with app.test_request_context(
        "/api/ambulance/trips",
        query_string={"per_page": "501"},
    ):
        with pytest.raises(ValidationError):
            ambulance_trip_routes._pagination_params()