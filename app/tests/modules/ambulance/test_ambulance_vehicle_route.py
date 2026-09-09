# app/tests/modules/ambulance/test_ambulance_vehicle_routes.py

from datetime import date, datetime
from unittest.mock import Mock
import pytest

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

    return type(
        "Pagination",
        (),
        {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
            "has_next": page < pages,
            "has_prev": page > 1,
        },
    )()


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


@pytest.mark.parametrize(
    "equipment_level",
    [
        EquipmentLevel.BLS,
        EquipmentLevel.ALS,
        EquipmentLevel.CCT,
    ],
)
def test_payload_accepts_all_equipment_levels(
    app,
    equipment_level,
):
    with app.test_request_context(
        "/api/ambulance/vehicles",
        method="POST",
        json={
            "plate_number": "AMB-001",
            "equipment_level": equipment_level.value,
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
    assert result.equipment_level == equipment_level


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


def test_payload_rejects_unknown_create_fields(
    app,
):
    with app.test_request_context(
        "/api/ambulance/vehicles",
        method="POST",
        json={
            "plate_number": "AMB-001",
            "clinic_id": 999,
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


def test_payload_rejects_non_object_json(
    app,
):
    with app.test_request_context(
        "/api/ambulance/vehicles",
        method="POST",
        data="[]",
        content_type="application/json",
    ):
        result = ambulance_vehicle_routes._payload(
            AmbulanceVehicleCreateSchema,
        )

    assert isinstance(result, tuple)

    response, status_code = result

    assert status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Request body must be a JSON object"
    )


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


@pytest.mark.parametrize(
    "equipment_level",
    [
        EquipmentLevel.BLS,
        EquipmentLevel.ALS,
        EquipmentLevel.CCT,
    ],
)
def test_create_ambulance_vehicle_passes_equipment_level(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
    equipment_level,
):
    user = make_user(
        clinic=clinic,
        role=Role.ADMIN,
    )

    vehicle = make_vehicle(
        clinic_id=clinic.id,
        equipment_level=equipment_level,
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

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/vehicles",
        json={
            "plate_number": "AMB-001",
            "equipment_level": equipment_level.value,
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert captured["kwargs"]["equipment_level"] == (
        equipment_level
    )


def test_create_ambulance_vehicle_does_not_use_client_clinic_id(
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

    called = False

    def fake_create_vehicle(
        clinic_id,
        **kwargs,
    ):
        nonlocal called
        called = True

        assert clinic_id == clinic.id
        assert "clinic_id" not in kwargs

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

    assert response.status_code == 422
    assert called is False


def test_create_ambulance_vehicle_invalid_payload(
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

    assert response.status_code == 403


# ============================================================
# LIST VEHICLES
# ============================================================


def test_get_ambulance_vehicles_success(
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

    pagination = make_pagination(
        vehicles,
        page=1,
        per_page=50,
        total=2,
    )

    captured = {}

    def fake_list_vehicles(
        clinic_id,
        status=None,
        page=1,
        per_page=50,
    ):
        captured["clinic_id"] = clinic_id
        captured["status"] = status
        captured["page"] = page
        captured["per_page"] = per_page
        return pagination

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

    assert captured["clinic_id"] == clinic.id
    assert captured["status"] is None
    assert captured["page"] == 1
    assert captured["per_page"] == 50


def test_get_ambulance_vehicles_supports_pagination(
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

    vehicle = make_vehicle(
        vehicle_id=51,
        clinic_id=clinic.id,
        plate_number="AMB-051",
    )

    pagination = make_pagination(
        [vehicle],
        page=2,
        per_page=25,
        total=51,
    )

    service = Mock(return_value=pagination)

    monkeypatch.setattr(
        ambulance_vehicle_routes,
        "list_vehicles",
        service,
    )

    response = client.get(
        "/api/ambulance/vehicles",
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


def test_get_ambulance_vehicles_empty_page(
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

    pagination = make_pagination(
        [],
        page=3,
        per_page=50,
        total=100,
    )

    monkeypatch.setattr(
        ambulance_vehicle_routes,
        "list_vehicles",
        Mock(return_value=pagination),
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/ambulance/vehicles",
        query_string={
            "page": "3",
            "per_page": "50",
        },
        headers=headers,
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert data["items"] == []
    assert data["total"] == 100
    assert data["page"] == 3
    assert data["per_page"] == 50
    assert data["pages"] == 2
    assert data["has_next"] is False
    assert data["has_prev"] is True


def test_get_ambulance_vehicles_filters_by_status(
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

    vehicle = make_vehicle(
        vehicle_id=1,
        clinic_id=clinic.id,
        status=VehicleStatus.AVAILABLE,
    )

    pagination = make_pagination(
        [vehicle],
        total=1,
    )

    service = Mock(return_value=pagination)

    monkeypatch.setattr(
        ambulance_vehicle_routes,
        "list_vehicles",
        service,
    )

    response = client.get(
        "/api/ambulance/vehicles",
        query_string={
            "status": VehicleStatus.AVAILABLE.value,
        },
        headers=headers,
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert data["items"][0]["id"] == 1

    service.assert_called_once_with(
        clinic_id=clinic.id,
        status=VehicleStatus.AVAILABLE,
        page=1,
        per_page=50,
    )


def test_get_ambulance_vehicles_rejects_empty_status(
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
            "status": "   ",
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Vehicle status cannot be empty"
    )


def test_get_ambulance_vehicles_rejects_invalid_status(
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
        "Invalid vehicle status: "
        "NOT_A_REAL_STATUS"
    )


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
def test_get_ambulance_vehicles_rejects_invalid_pagination(
    client,
    clinic,
    make_user,
    auth_headers_for,
    query_string,
):
    user = make_user(
        clinic=clinic,
        role=Role.AMBULANCE_DISPATCHER,
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/ambulance/vehicles",
        query_string=query_string,
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_get_ambulance_vehicles_domain_error(
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

    assert response.status_code == 403


# ============================================================
# GET VEHICLE
# ============================================================


def test_get_ambulance_vehicle_success(
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

    service = Mock(return_value=vehicle)

    monkeypatch.setattr(
        ambulance_vehicle_routes,
        "get_vehicle",
        service,
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

    service.assert_called_once_with(vehicle.id)


def test_get_ambulance_vehicle_not_found(
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

    assert response.status_code == 403


# ============================================================
# UPDATE VEHICLE STATUS
# ============================================================


def test_update_ambulance_vehicle_status_success(
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

    target_status = VehicleStatus.MAINTENANCE

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


def test_update_ambulance_vehicle_status_rejects_unknown_fields(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    user = make_user(
        clinic=clinic,
        role=Role.ADMIN,
    )

    headers = auth_headers_for(user)

    response = client.patch(
        "/api/ambulance/vehicles/1/status",
        json={
            "status": VehicleStatus.AVAILABLE.value,
            "clinic_id": 999,
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Invalid request payload"


def test_update_ambulance_vehicle_status_domain_error(
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

    assert response.status_code == 403


# ============================================================
# AUTHENTICATION
# ============================================================


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/ambulance/vehicles"),
        ("GET", "/api/ambulance/vehicles"),
        ("GET", "/api/ambulance/vehicles/1"),
        ("PATCH", "/api/ambulance/vehicles/1/status"),
    ],
)
def test_ambulance_vehicle_routes_require_authentication(
    client,
    method,
    path,
):
    response = client.open(
        path,
        method=method,
    )

    assert response.status_code in (401, 403)


def test_create_ambulance_vehicle_rejects_inactive_user(
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


def test_update_ambulance_vehicle_status_rejects_inactive_user(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        role=Role.ADMIN,
        is_active=False,
    )

    vehicle = make_vehicle(
        vehicle_id=1,
        clinic_id=clinic.id,
        status=VehicleStatus.AVAILABLE,
    )

    service = Mock(return_value=vehicle)

    monkeypatch.setattr(
        ambulance_vehicle_routes,
        "set_vehicle_status",
        service,
    )

    headers = auth_headers_for(user)

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
    assert body["error"] == "User account is inactive"

    service.assert_not_called()
    

def test_create_ambulance_vehicle_rejects_user_without_clinic(
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


# ============================================================
# CLINIC ISOLATION
# ============================================================


def test_create_ambulance_vehicle_uses_authenticated_clinic(
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

    vehicle = make_vehicle(
        clinic_id=clinic.id,
    )

    service = Mock(return_value=vehicle)

    monkeypatch.setattr(
        ambulance_vehicle_routes,
        "create_vehicle",
        service,
    )

    headers = auth_headers_for(user)

    response = client.post(
        "/api/ambulance/vehicles",
        json={
            "plate_number": "AMB-001",
        },
        headers=headers,
    )

    assert response.status_code == 201

    assert service.call_args.kwargs["clinic_id"] == (
        clinic.id
    )
    assert service.call_args.kwargs["clinic_id"] != 999


def test_get_ambulance_vehicles_uses_authenticated_clinic(
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

    pagination = make_pagination([])

    service = Mock(return_value=pagination)

    monkeypatch.setattr(
        ambulance_vehicle_routes,
        "list_vehicles",
        service,
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/ambulance/vehicles?clinic_id=999",
        headers=headers,
    )

    assert response.status_code == 200

    service.assert_called_once_with(
        clinic_id=clinic.id,
        status=None,
        page=1,
        per_page=50,
    )


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