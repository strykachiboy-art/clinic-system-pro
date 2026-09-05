from datetime import datetime
from types import SimpleNamespace

import pytest

from app.core.enums.ambulance_enums import VehicleStatus
from app.core.enums.role_enums import Role

import app.modules.ambulance.routes.ambulance_vehicle_routes as vehicle_route


# ============================================================
# HELPERS
# ============================================================


def make_vehicle(
    clinic_id=1,
    vehicle_id=1,
    plate_number="AMB-001",
    capacity=4,
    status=VehicleStatus.AVAILABLE,
):
    equipment_level = list(
        __import__(
            "app.core.enums.ambulance_enums",
            fromlist=["EquipmentLevel"],
        ).EquipmentLevel
    )[0]

    now = datetime(2026, 1, 1, 12, 0, 0)

    return SimpleNamespace(
        id=vehicle_id,
        clinic_id=clinic_id,
        plate_number=plate_number,
        equipment_level=equipment_level,
        capacity=capacity,
        status=status,
        last_service_date=None,
        created_at=now,
        updated_at=now,
    )


class FakePayload:
    def __init__(self, **data):
        self._data = data

        for key, value in data.items():
            setattr(self, key, value)

    def model_dump(self):
        return dict(self._data)


# ============================================================
# CREATE VEHICLE
# ============================================================


def test_create_vehicle_success(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.ADMIN,
    )

    vehicle = make_vehicle(
        clinic_id=clinic.id,
        plate_number="AMB-001",
    )

    payload = FakePayload(
        clinic_id=clinic.id,
        plate_number="AMB-001",
        capacity=4,
    )

    called = {}

    def fake_create_vehicle(**kwargs):
        called.update(kwargs)
        return vehicle

    monkeypatch.setattr(
        vehicle_route,
        "_payload",
        lambda schema: payload,
    )

    monkeypatch.setattr(
        vehicle_route,
        "create_vehicle",
        fake_create_vehicle,
    )

    response = client.post(
        "/api/ambulance/vehicles",
        json={
            "clinic_id": clinic.id,
            "plate_number": "AMB-001",
            "capacity": 4,
        },
        headers=headers,
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == vehicle.id
    assert body["data"]["clinic_id"] == clinic.id
    assert body["data"]["plate_number"] == "AMB-001"
    assert body["data"]["capacity"] == 4
    assert body["data"]["status"] == vehicle.status.value

    assert called["clinic_id"] == clinic.id
    assert called["plate_number"] == "AMB-001"
    assert called["capacity"] == 4


def test_create_vehicle_requires_management_role(
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
        vehicle_route,
        "create_vehicle",
        lambda **kwargs: pytest.fail(
            "create_vehicle should not be called"
        ),
    )

    response = client.post(
        "/api/ambulance/vehicles",
        json={
            "clinic_id": clinic.id,
            "plate_number": "AMB-002",
            "capacity": 4,
        },
        headers=headers,
    )

    assert response.status_code == 403

    body = response.get_json()
    assert body["error"] == "Insufficient permissions"


def test_create_vehicle_allows_ambulance_coordinator(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.AMBULANCE_COORDINATOR,
    )

    vehicle = make_vehicle(
        clinic_id=clinic.id,
        plate_number="AMB-003",
    )

    payload = FakePayload(
        clinic_id=clinic.id,
        plate_number="AMB-003",
        capacity=4,
    )

    monkeypatch.setattr(
        vehicle_route,
        "_payload",
        lambda schema: payload,
    )

    monkeypatch.setattr(
        vehicle_route,
        "create_vehicle",
        lambda **kwargs: vehicle,
    )

    response = client.post(
        "/api/ambulance/vehicles",
        json={
            "clinic_id": clinic.id,
            "plate_number": "AMB-003",
            "capacity": 4,
        },
        headers=headers,
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["plate_number"] == "AMB-003"


def test_create_vehicle_unauthenticated(client):
    response = client.post(
        "/api/ambulance/vehicles",
        json={
            "clinic_id": 1,
            "plate_number": "AMB-004",
            "capacity": 4,
        },
    )

    assert response.status_code in (401, 422)

    body = response.get_json()
    assert "msg" in body


def test_create_vehicle_payload_validation_error(
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
        vehicle_route.jsonify(
            {
                "success": False,
                "error": [
                    {
                        "type": "missing",
                        "loc": ["body", "plate_number"],
                        "msg": "Field required",
                    }
                ],
            }
        ),
        422,
    )

    monkeypatch.setattr(
        vehicle_route,
        "_payload",
        lambda schema: validation_response,
    )

    response = client.post(
        "/api/ambulance/vehicles",
        json={},
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"][0]["type"] == "missing"


# ============================================================
# LIST VEHICLES
# ============================================================


def test_list_vehicles_success(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.ADMIN,
    )

    vehicles = [
        make_vehicle(
            clinic_id=clinic.id,
            vehicle_id=1,
            plate_number="AMB-001",
        ),
        make_vehicle(
            clinic_id=clinic.id,
            vehicle_id=2,
            plate_number="AMB-002",
        ),
    ]

    called = {}

    def fake_list_vehicles(**kwargs):
        called.update(kwargs)
        return vehicles

    monkeypatch.setattr(
        vehicle_route,
        "list_vehicles",
        fake_list_vehicles,
    )

    response = client.get(
        f"/api/ambulance/vehicles?clinic_id={clinic.id}",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert len(body["data"]) == 2

    assert body["data"][0]["plate_number"] == "AMB-001"
    assert body["data"][1]["plate_number"] == "AMB-002"

    assert called["clinic_id"] == clinic.id
    assert called["status"] is None


def test_list_vehicles_with_status_filter(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.AMBULANCE_DISPATCHER,
    )

    vehicle = make_vehicle(
        clinic_id=clinic.id,
        status=VehicleStatus.AVAILABLE,
    )

    called = {}

    def fake_list_vehicles(**kwargs):
        called.update(kwargs)
        return [vehicle]

    monkeypatch.setattr(
        vehicle_route,
        "list_vehicles",
        fake_list_vehicles,
    )

    response = client.get(
        (
            f"/api/ambulance/vehicles"
            f"?clinic_id={clinic.id}"
            f"&status={VehicleStatus.AVAILABLE.value}"
        ),
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert len(body["data"]) == 1
    assert body["data"][0]["status"] == VehicleStatus.AVAILABLE.value

    assert called["clinic_id"] == clinic.id
    assert called["status"] == VehicleStatus.AVAILABLE


def test_list_vehicles_missing_clinic_id(
    client,
    make_authenticated_staff,
    clinic,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.ADMIN,
    )

    response = client.get(
        "/api/ambulance/vehicles",
        headers=headers,
    )

    assert response.status_code == 400

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "clinic_id query parameter is required"
    )


def test_list_vehicles_invalid_status(
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
            f"/api/ambulance/vehicles"
            f"?clinic_id={clinic.id}"
            f"&status=NOT_A_REAL_STATUS"
        ),
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Invalid vehicle status: NOT_A_REAL_STATUS"
    )


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
def test_list_vehicles_allows_view_roles(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
    role,
):
    _, headers = make_authenticated_staff(
        clinic,
        role,
    )

    monkeypatch.setattr(
        vehicle_route,
        "list_vehicles",
        lambda **kwargs: [],
    )

    response = client.get(
        f"/api/ambulance/vehicles?clinic_id={clinic.id}",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"] == []


def test_list_vehicles_denies_unapproved_role(
    client,
    make_authenticated_staff,
    clinic,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.NURSE,
    )

    response = client.get(
        f"/api/ambulance/vehicles?clinic_id={clinic.id}",
        headers=headers,
    )

    assert response.status_code == 403

    body = response.get_json()

    assert body["error"] == "Insufficient permissions"


# ============================================================
# GET VEHICLE
# ============================================================


def test_get_vehicle_success(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.AMBULANCE_COORDINATOR,
    )

    vehicle = make_vehicle(
        clinic_id=clinic.id,
        vehicle_id=7,
        plate_number="AMB-007",
    )

    called = {}

    def fake_get_vehicle(vehicle_id):
        called["vehicle_id"] = vehicle_id
        return vehicle

    monkeypatch.setattr(
        vehicle_route,
        "get_vehicle",
        fake_get_vehicle,
    )

    response = client.get(
        "/api/ambulance/vehicles/7",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 7
    assert body["data"]["clinic_id"] == clinic.id
    assert body["data"]["plate_number"] == "AMB-007"
    assert body["data"]["capacity"] == 4
    assert body["data"]["status"] == VehicleStatus.AVAILABLE.value

    assert called["vehicle_id"] == 7


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
def test_get_vehicle_allows_view_roles(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
    role,
):
    _, headers = make_authenticated_staff(
        clinic,
        role,
    )

    vehicle = make_vehicle(
        clinic_id=clinic.id,
        vehicle_id=8,
    )

    monkeypatch.setattr(
        vehicle_route,
        "get_vehicle",
        lambda vehicle_id: vehicle,
    )

    response = client.get(
        "/api/ambulance/vehicles/8",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 8


def test_get_vehicle_denies_unapproved_role(
    client,
    make_authenticated_staff,
    clinic,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.NURSE,
    )

    response = client.get(
        "/api/ambulance/vehicles/1",
        headers=headers,
    )

    assert response.status_code == 403

    body = response.get_json()

    assert body["error"] == "Insufficient permissions"


def test_get_vehicle_unauthenticated(client):
    response = client.get(
        "/api/ambulance/vehicles/1",
    )

    assert response.status_code in (401, 422)

    body = response.get_json()

    assert "msg" in body


# ============================================================
# UPDATE VEHICLE STATUS
# ============================================================


def test_update_vehicle_status_success(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.ADMIN,
    )

    updated_vehicle = make_vehicle(
        clinic_id=clinic.id,
        vehicle_id=10,
        status=VehicleStatus.MAINTENANCE,
    )

    payload = FakePayload(
        status=VehicleStatus.MAINTENANCE,
    )

    called = {}

    def fake_set_vehicle_status(
        vehicle_id,
        new_status,
    ):
        called["vehicle_id"] = vehicle_id
        called["new_status"] = new_status
        return updated_vehicle

    monkeypatch.setattr(
        vehicle_route,
        "_payload",
        lambda schema: payload,
    )

    monkeypatch.setattr(
        vehicle_route,
        "set_vehicle_status",
        fake_set_vehicle_status,
    )

    response = client.patch(
        "/api/ambulance/vehicles/10/status",
        json={
            "status": VehicleStatus.MAINTENANCE.value,
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 10
    assert body["data"]["status"] == (
        VehicleStatus.MAINTENANCE.value
    )

    assert called["vehicle_id"] == 10
    assert called["new_status"] == VehicleStatus.MAINTENANCE


def test_update_vehicle_status_payload_validation_error(
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
        vehicle_route.jsonify(
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
        vehicle_route,
        "_payload",
        lambda schema: validation_response,
    )

    response = client.patch(
        "/api/ambulance/vehicles/1/status",
        json={},
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"][0]["type"] == "missing"


def test_update_vehicle_status_requires_management_role(
    client,
    make_authenticated_staff,
    clinic,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.DRIVER,
    )

    response = client.patch(
        "/api/ambulance/vehicles/1/status",
        json={
            "status": VehicleStatus.MAINTENANCE.value,
        },
        headers=headers,
    )

    assert response.status_code == 403

    body = response.get_json()

    assert body["error"] == "Insufficient permissions"


def test_update_vehicle_status_allows_coordinator(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.AMBULANCE_COORDINATOR,
    )

    vehicle = make_vehicle(
        clinic_id=clinic.id,
        vehicle_id=11,
        status=VehicleStatus.AVAILABLE,
    )

    payload = FakePayload(
        status=VehicleStatus.MAINTENANCE,
    )

    monkeypatch.setattr(
        vehicle_route,
        "_payload",
        lambda schema: payload,
    )

    monkeypatch.setattr(
        vehicle_route,
        "set_vehicle_status",
        lambda vehicle_id, new_status: vehicle,
    )

    response = client.patch(
        "/api/ambulance/vehicles/11/status",
        json={
            "status": VehicleStatus.MAINTENANCE.value,
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True


# ============================================================
# SERIALIZATION
# ============================================================


def test_vehicle_data_serializes_optional_dates(app):
    vehicle = make_vehicle()

    data = vehicle_route._vehicle_data(vehicle)

    assert data["last_service_date"] is None

    assert data["created_at"] == (
        "2026-01-01T12:00:00"
    )

    assert data["updated_at"] == (
        "2026-01-01T12:00:00"
    )

    assert data["equipment_level"] == (
        vehicle.equipment_level.value
    )


def test_vehicle_data_handles_missing_optional_timestamps(app):
    vehicle = make_vehicle()

    vehicle.created_at = None
    vehicle.updated_at = None

    data = vehicle_route._vehicle_data(vehicle)

    assert data["created_at"] is None
    assert data["updated_at"] is None