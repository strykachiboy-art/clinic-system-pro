import pytest

from datetime import date, datetime

from app.core.enums.ambulance_enums import (
    EquipmentLevel,
    VehicleStatus,
)

from app.core.enums.role_enums import Role

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

from app.modules.ambulance.routes import (
    ambulance_vehicle_routes,
)

from app.modules.ambulance.schemas.ambulance_vehicle_schema import (
    AmbulanceVehicleCreateSchema,
    AmbulanceVehicleStatusSchema,
)


# ============================================================
# HELPERS
# ============================================================


def make_vehicle(
    vehicle_id=1,
    clinic_id=10,
    plate_number="AMB-001",
    equipment_level=EquipmentLevel.BLS,
    capacity=1,
    status=VehicleStatus.AVAILABLE,
    last_service_date=None,
    created_at=None,
    updated_at=None,
):
    class Vehicle:
        pass

    vehicle = Vehicle()

    vehicle.id = vehicle_id
    vehicle.clinic_id = clinic_id
    vehicle.plate_number = plate_number
    vehicle.equipment_level = equipment_level
    vehicle.capacity = capacity
    vehicle.status = status
    vehicle.last_service_date = last_service_date
    vehicle.created_at = created_at
    vehicle.updated_at = updated_at

    return vehicle


# ============================================================
# _payload
# ============================================================


def test_payload_accepts_valid_vehicle_create_payload(
    app,
):
    with app.test_request_context(
        "/api/ambulance/vehicles",
        method="POST",
        json={
            "plate_number": "AMB-001",
            "equipment_level": EquipmentLevel.BLS.value,
            "capacity": 2,
        },
    ):
        result = ambulance_vehicle_routes._payload(
            AmbulanceVehicleCreateSchema,
        )

    assert isinstance(
        result,
        AmbulanceVehicleCreateSchema,
    )

    assert result.plate_number == "AMB-001"
    assert result.equipment_level == EquipmentLevel.BLS
    assert result.capacity == 2


def test_payload_rejects_invalid_vehicle_create_payload(
    app,
):
    with app.test_request_context(
        "/api/ambulance/vehicles",
        method="POST",
        json={
            "plate_number": "",
        },
    ):
        result = ambulance_vehicle_routes._payload(
            AmbulanceVehicleCreateSchema,
        )

    assert isinstance(result, tuple)

    response, status_code = result

    assert status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Invalid request payload"


def test_payload_accepts_default_vehicle_create_values(
    app,
):
    with app.test_request_context(
        "/api/ambulance/vehicles",
        method="POST",
        json={
            "plate_number": "AMB-002",
        },
    ):
        result = ambulance_vehicle_routes._payload(
            AmbulanceVehicleCreateSchema,
        )

    assert isinstance(
        result,
        AmbulanceVehicleCreateSchema,
    )

    assert result.equipment_level == EquipmentLevel.BLS
    assert result.capacity == 1
    assert result.last_service_date is None


def test_payload_rejects_invalid_vehicle_status_payload(
    app,
):
    with app.test_request_context(
        "/api/ambulance/vehicles/1/status",
        method="PATCH",
        json={},
    ):
        result = ambulance_vehicle_routes._payload(
            AmbulanceVehicleStatusSchema,
        )

    assert isinstance(result, tuple)

    response, status_code = result

    assert status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Invalid request payload"


# ============================================================
# _vehicle_data
# ============================================================


def test_vehicle_data_serializes_vehicle():
    created_at = datetime(
        2026,
        9,
        7,
        10,
        30,
        0,
    )

    updated_at = datetime(
        2026,
        9,
        7,
        11,
        45,
        0,
    )

    service_date = date(
        2026,
        9,
        1,
    )

    vehicle = make_vehicle(
        vehicle_id=7,
        clinic_id=10,
        plate_number="AMB-007",
        equipment_level=EquipmentLevel.ALS,
        capacity=4,
        status=VehicleStatus.AVAILABLE,
        last_service_date=service_date,
        created_at=created_at,
        updated_at=updated_at,
    )

    data = ambulance_vehicle_routes._vehicle_data(
        vehicle,
    )

    assert data == {
        "id": 7,
        "clinic_id": 10,
        "plate_number": "AMB-007",
        "equipment_level": EquipmentLevel.ALS.value,
        "capacity": 4,
        "status": VehicleStatus.AVAILABLE.value,
        "last_service_date": service_date.isoformat(),
        "created_at": created_at.isoformat(),
        "updated_at": updated_at.isoformat(),
    }


def test_vehicle_data_handles_nullable_fields():
    vehicle = make_vehicle(
        equipment_level=None,
        status=None,
        last_service_date=None,
        created_at=None,
        updated_at=None,
    )

    data = ambulance_vehicle_routes._vehicle_data(
        vehicle,
    )

    assert data["equipment_level"] is None
    assert data["status"] is None
    assert data["last_service_date"] is None
    assert data["created_at"] is None
    assert data["updated_at"] is None


# ============================================================
# CREATE VEHICLE
# ============================================================


def test_create_ambulance_vehicle_success(
    app,
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        role=Role.ADMIN,
    )

    headers = auth_headers_for(user)

    vehicle = make_vehicle(
        vehicle_id=1,
        clinic_id=clinic.id,
        plate_number="AMB-001",
        equipment_level=EquipmentLevel.BLS,
        capacity=2,
        status=VehicleStatus.AVAILABLE,
    )

    captured = {}

    def fake_create_vehicle(
        clinic_id,
        **kwargs,
    ):
        captured["clinic_id"] = clinic_id
        captured["kwargs"] = kwargs
        return vehicle

    monkeypatch.setattr(
        ambulance_vehicle_routes,
        "create_vehicle",
        fake_create_vehicle,
    )

    response = client.post(
        "/api/ambulance/vehicles",
        json={
            "plate_number": "AMB-001",
            "equipment_level": EquipmentLevel.BLS.value,
            "capacity": 2,
        },
        headers=headers,
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == vehicle.id
    assert body["data"]["clinic_id"] == clinic.id
    assert body["data"]["plate_number"] == "AMB-001"
    assert (
        body["data"]["equipment_level"]
        == EquipmentLevel.BLS.value
    )
    assert body["data"]["capacity"] == 2
    assert (
        body["data"]["status"]
        == VehicleStatus.AVAILABLE.value
    )

    assert captured["clinic_id"] == clinic.id
    assert captured["kwargs"]["plate_number"] == "AMB-001"
    assert (
        captured["kwargs"]["equipment_level"]
        == EquipmentLevel.BLS
    )
    assert captured["kwargs"]["capacity"] == 2


def test_create_ambulance_vehicle_does_not_use_client_clinic_id(
    app,
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        role=Role.ADMIN,
    )

    headers = auth_headers_for(user)

    vehicle = make_vehicle(
        clinic_id=clinic.id,
    )

    captured = {}

    def fake_create_vehicle(
        clinic_id,
        **kwargs,
    ):
        captured["clinic_id"] = clinic_id
        captured["kwargs"] = kwargs
        return vehicle

    monkeypatch.setattr(
        ambulance_vehicle_routes,
        "create_vehicle",
        fake_create_vehicle,
    )

    response = client.post(
        "/api/ambulance/vehicles",
        json={
            "plate_number": "AMB-001",
            "clinic_id": 999999,
        },
        headers=headers,
    )

    assert response.status_code == 201

    assert captured["clinic_id"] == clinic.id
    assert "clinic_id" not in captured["kwargs"]


def test_create_ambulance_vehicle_invalid_payload(
    app,
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        role=Role.ADMIN,
    )

    headers = auth_headers_for(user)

    called = False

    def fake_create_vehicle(*args, **kwargs):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(
        ambulance_vehicle_routes,
        "create_vehicle",
        fake_create_vehicle,
    )

    response = client.post(
        "/api/ambulance/vehicles",
        json={
            "plate_number": "",
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Invalid request payload"

    assert called is False


def test_create_ambulance_vehicle_domain_error(
    app,
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        role=Role.ADMIN,
    )

    headers = auth_headers_for(user)

    def raise_conflict(**kwargs):
        raise ConflictError(
            "Vehicle plate number already exists"
        )

    monkeypatch.setattr(
        ambulance_vehicle_routes,
        "create_vehicle",
        raise_conflict,
    )

    response = client.post(
        "/api/ambulance/vehicles",
        json={
            "plate_number": "AMB-001",
        },
        headers=headers,
    )

    assert response.status_code == 409

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Vehicle plate number already exists"
    )


def test_create_ambulance_vehicle_requires_management_role(
    app,
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    user = make_user(
        clinic=clinic,
        role=Role.DRIVER,
    )

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/vehicles",
        json={
            "plate_number": "AMB-001",
        },
        headers=headers,
    )

    assert response.status_code in (
        401,
        403,
    )


# ============================================================
# LIST VEHICLES
# ============================================================


def test_get_ambulance_vehicles_success(
    app,
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        role=Role.AMBULANCE_DISPATCHER,
    )

    headers = auth_headers_for(user)

    vehicles = [
        make_vehicle(
            vehicle_id=1,
            clinic_id=clinic.id,
            plate_number="AMB-001",
        ),
        make_vehicle(
            vehicle_id=2,
            clinic_id=clinic.id,
            plate_number="AMB-002",
        ),
    ]

    captured = {}

    def fake_list_vehicles(
        clinic_id,
        status=None,
    ):
        captured["clinic_id"] = clinic_id
        captured["status"] = status
        return vehicles

    monkeypatch.setattr(
        ambulance_vehicle_routes,
        "list_vehicles",
        fake_list_vehicles,
    )

    response = client.get(
        "/api/ambulance/vehicles",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert len(body["data"]) == 2
    assert body["data"][0]["id"] == 1
    assert body["data"][1]["id"] == 2

    assert captured["clinic_id"] == clinic.id
    assert captured["status"] is None


def test_get_ambulance_vehicles_filters_by_status(
    app,
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        role=Role.AMBULANCE_DISPATCHER,
    )

    headers = auth_headers_for(user)

    vehicles = [
        make_vehicle(
            vehicle_id=1,
            clinic_id=clinic.id,
            status=VehicleStatus.AVAILABLE,
        ),
    ]

    captured = {}

    def fake_list_vehicles(
        clinic_id,
        status=None,
    ):
        captured["clinic_id"] = clinic_id
        captured["status"] = status
        return vehicles

    monkeypatch.setattr(
        ambulance_vehicle_routes,
        "list_vehicles",
        fake_list_vehicles,
    )

    response = client.get(
        "/api/ambulance/vehicles",
        query_string={
            "status": VehicleStatus.AVAILABLE.value,
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert captured["clinic_id"] == clinic.id
    assert captured["status"] == VehicleStatus.AVAILABLE


def test_get_ambulance_vehicles_rejects_invalid_status(
    app,
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    user = make_user(
        clinic=clinic,
        role=Role.AMBULANCE_DISPATCHER,
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/ambulance/vehicles",
        query_string={
            "status": "NOT_A_REAL_STATUS",
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Invalid vehicle status: NOT_A_REAL_STATUS"
    )


def test_get_ambulance_vehicles_domain_error(
    app,
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        role=Role.ADMIN,
    )

    headers = auth_headers_for(user)

    def raise_validation(**kwargs):
        raise ValidationError(
            "Clinic validation failed"
        )

    monkeypatch.setattr(
        ambulance_vehicle_routes,
        "list_vehicles",
        raise_validation,
    )

    response = client.get(
        "/api/ambulance/vehicles",
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Clinic validation failed"


def test_get_ambulance_vehicles_requires_view_role(
    app,
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    user = make_user(
        clinic=clinic,
        role=Role.PHARMACIST,
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/ambulance/vehicles",
        headers=headers,
    )

    assert response.status_code in (
        401,
        403,
    )


# ============================================================
# GET VEHICLE
# ============================================================


def test_get_ambulance_vehicle_success(
    app,
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        role=Role.DRIVER,
    )

    headers = auth_headers_for(user)

    vehicle = make_vehicle(
        vehicle_id=7,
        clinic_id=clinic.id,
        plate_number="AMB-007",
        equipment_level=EquipmentLevel.ALS,
        capacity=4,
    )

    monkeypatch.setattr(
        ambulance_vehicle_routes,
        "get_vehicle",
        lambda vehicle_id: vehicle,
    )

    response = client.get(
        f"/api/ambulance/vehicles/{vehicle.id}",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 7
    assert body["data"]["clinic_id"] == clinic.id
    assert body["data"]["plate_number"] == "AMB-007"
    assert (
        body["data"]["equipment_level"]
        == EquipmentLevel.ALS.value
    )
    assert body["data"]["capacity"] == 4


def test_get_ambulance_vehicle_not_found(
    app,
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        role=Role.DRIVER,
    )

    headers = auth_headers_for(user)

    def raise_not_found(vehicle_id):
        raise NotFoundError(
            "Ambulance vehicle not found"
        )

    monkeypatch.setattr(
        ambulance_vehicle_routes,
        "get_vehicle",
        raise_not_found,
    )

    response = client.get(
        "/api/ambulance/vehicles/999999",
        headers=headers,
    )

    assert response.status_code == 404

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Ambulance vehicle not found"
    )


def test_get_ambulance_vehicle_requires_view_role(
    app,
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    user = make_user(
        clinic=clinic,
        role=Role.PATIENT,
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/ambulance/vehicles/1",
        headers=headers,
    )

    assert response.status_code in (
        401,
        403,
    )


# ============================================================
# UPDATE VEHICLE STATUS
# ============================================================


def test_update_ambulance_vehicle_status_success(
    app,
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        role=Role.AMBULANCE_COORDINATOR,
    )

    headers = auth_headers_for(user)

    vehicle = make_vehicle(
        vehicle_id=5,
        clinic_id=clinic.id,
        plate_number="AMB-005",
        status=VehicleStatus.AVAILABLE,
    )

    target_status = next(
        status
        for status in VehicleStatus
        if status != VehicleStatus.AVAILABLE
    )

    captured = {}

    def fake_set_vehicle_status(
        vehicle_id,
        new_status,
    ):
        captured["vehicle_id"] = vehicle_id
        captured["new_status"] = new_status

        vehicle.status = new_status

        return vehicle

    monkeypatch.setattr(
        ambulance_vehicle_routes,
        "set_vehicle_status",
        fake_set_vehicle_status,
    )

    response = client.patch(
        f"/api/ambulance/vehicles/{vehicle.id}/status",
        json={
            "status": target_status.value,
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == vehicle.id
    assert body["data"]["status"] == target_status.value

    assert captured["vehicle_id"] == vehicle.id
    assert captured["new_status"] == target_status


def test_update_ambulance_vehicle_status_invalid_payload(
    app,
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        role=Role.ADMIN,
    )

    headers = auth_headers_for(user)

    called = False

    def fake_set_vehicle_status(*args, **kwargs):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(
        ambulance_vehicle_routes,
        "set_vehicle_status",
        fake_set_vehicle_status,
    )

    response = client.patch(
        "/api/ambulance/vehicles/1/status",
        json={},
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Invalid request payload"

    assert called is False


def test_update_ambulance_vehicle_status_domain_error(
    app,
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        role=Role.ADMIN,
    )

    headers = auth_headers_for(user)

    def raise_validation(**kwargs):
        raise ValidationError(
            "Invalid vehicle status transition"
        )

    monkeypatch.setattr(
        ambulance_vehicle_routes,
        "set_vehicle_status",
        raise_validation,
    )

    response = client.patch(
        "/api/ambulance/vehicles/1/status",
        json={
            "status": VehicleStatus.AVAILABLE.value,
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Invalid vehicle status transition"
    )


def test_update_ambulance_vehicle_status_requires_management_role(
    app,
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    user = make_user(
        clinic=clinic,
        role=Role.DRIVER,
    )

    headers = auth_headers_for(user)

    response = client.patch(
        "/api/ambulance/vehicles/1/status",
        json={
            "status": VehicleStatus.AVAILABLE.value,
        },
        headers=headers,
    )

    assert response.status_code in (
        401,
        403,
    )


# ============================================================
# AUTHENTICATION / CURRENT CLINIC
# ============================================================


def test_create_ambulance_vehicle_rejects_inactive_user(
    app,
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    user = make_user(
        clinic=clinic,
        role=Role.ADMIN,
        is_active=False,
    )

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/vehicles",
        json={
            "plate_number": "AMB-001",
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "User account is inactive"


def test_create_ambulance_vehicle_rejects_user_without_clinic(
    app,
    client,
    make_user,
    auth_headers_for,
):
    user = make_user(
        role=Role.ADMIN,
    )

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/vehicles",
        json={
            "plate_number": "AMB-001",
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Authenticated user is not associated "
        "with a clinic"
    )


def test_get_ambulance_vehicles_rejects_inactive_user(
    app,
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    user = make_user(
        clinic=clinic,
        role=Role.AMBULANCE_DISPATCHER,
        is_active=False,
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/ambulance/vehicles",
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "User account is inactive"


# ============================================================
# ROUTE REGISTRATION
# ============================================================


def test_ambulance_vehicle_routes_are_registered(
    app,
):
    rules = {
        rule.rule
        for rule in app.url_map.iter_rules()
    }

    assert "/api/ambulance/vehicles" in rules

    assert (
        "/api/ambulance/vehicles/"
        "<int:vehicle_id>"
    ) in rules

    assert (
        "/api/ambulance/vehicles/"
        "<int:vehicle_id>/status"
    ) in rules