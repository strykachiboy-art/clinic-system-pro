from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app.core.enums.role_enums import Role
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
from app.modules.ward.services import ward_service


# ============================================================================
# ROUTE MODULE
# ============================================================================


@pytest.fixture()
def ward_routes():
    """
    Import the concrete Ward route module.

    The package:
        app.modules.ward.routes

    exposes the routes package, while the actual route implementation
    lives in the concrete route module.
    """
    import app.modules.ward.routes.ward_route as routes

    return routes


# ============================================================================
# HELPERS
# ============================================================================


def _headers(
    auth_headers_for,
    user,
    role=None,
):
    return auth_headers_for(
        user,
        role=role,
    )


def _future_expiry(
    minutes: int = 30,
) -> datetime:
    return (
        datetime.now(timezone.utc)
        .replace(tzinfo=None)
        + timedelta(minutes=minutes)
    )


def _create_ward(
    clinic,
    *,
    name="General Ward",
    ward_type=WardType.GENERAL,
    capacity=5,
):
    return ward_service.create_ward(
        clinic_id=clinic.id,
        name=name,
        ward_type=ward_type,
        capacity=capacity,
    )


def _create_bed(
    clinic,
    *,
    ward_name="General Ward",
    capacity=5,
    bed_number="B-001",
):
    ward = _create_ward(
        clinic,
        name=ward_name,
        capacity=capacity,
    )

    bed = ward_service.add_bed(
        ward_id=ward.id,
        bed_number=bed_number,
        clinic_id=clinic.id,
    )

    return ward, bed


def _create_reservation(
    clinic,
    make_patient,
    make_staff,
    *,
    expires_at=None,
    reason=None,
):
    staff = make_staff(
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
        reserved_by_id=staff.id,
        clinic_id=clinic.id,
        reason=reason,
        expires_at=expires_at,
        actor_user_id=staff.user_id,
    )

    return (
        patient,
        staff,
        bed,
        reservation,
    )


def _create_admission(
    clinic,
    make_patient,
    make_staff,
    *,
    reason=None,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    patient = make_patient(
        clinic=clinic,
    )

    _, bed = _create_bed(clinic)

    admission = ward_service.admit_patient(
        patient_id=patient.id,
        bed_id=bed.id,
        admitted_by_id=staff.id,
        clinic_id=clinic.id,
        reason=reason,
        actor_user_id=staff.user_id,
    )

    return (
        patient,
        staff,
        bed,
        admission,
    )


# ============================================================================
# AUTHENTICATION
# ============================================================================


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/wards"),
        ("GET", "/api/wards"),
        ("GET", "/api/wards/1"),
        ("GET", "/api/wards/1/occupancy"),
        ("POST", "/api/wards/1/beds"),
        ("GET", "/api/wards/1/beds"),
        ("GET", "/api/wards/beds/1"),
        ("PATCH", "/api/wards/beds/1/maintenance"),
        ("POST", "/api/wards/reservations"),
        ("GET", "/api/wards/reservations"),
        ("GET", "/api/wards/reservations/1"),
        ("GET", "/api/wards/patients/1/reservation"),
        ("GET", "/api/wards/beds/1/reservation"),
        ("POST", "/api/wards/reservations/1/cancel"),
        ("POST", "/api/wards/reservations/1/admit"),
        ("POST", "/api/wards/admissions"),
        ("GET", "/api/wards/admissions/1"),
        ("GET", "/api/wards/patients/1/admissions"),
        ("GET", "/api/wards/patients/1/current-admission"),
        ("POST", "/api/wards/admissions/1/transfer"),
        ("POST", "/api/wards/admissions/1/discharge"),
    ],
)
def test_all_ward_routes_require_authentication(
    client,
    method,
    path,
):
    response = client.open(
        path,
        method=method,
    )

    assert response.status_code in (401, 422)


# ============================================================================
# RBAC
# ============================================================================


def test_receptionist_can_view_wards(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    user = make_user(
        clinic,
        role=Role.RECEPTIONIST,
    )

    _create_ward(clinic)

    response = client.get(
        "/api/wards",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    "method,path,payload",
    [
        (
            "POST",
            "/api/wards",
            {
                "name": "Restricted Ward",
                "capacity": 5,
            },
        ),
        (
            "POST",
            "/api/wards/1/beds",
            {
                "bed_number": "B-001",
            },
        ),
        (
            "PATCH",
            "/api/wards/beds/1/maintenance",
            {
                "under_maintenance": True,
            },
        ),
        (
            "POST",
            "/api/wards/reservations",
            {
                "patient_id": 1,
                "bed_id": 1,
            },
        ),
        (
            "POST",
            "/api/wards/admissions",
            {
                "patient_id": 1,
                "bed_id": 1,
            },
        ),
        (
            "POST",
            "/api/wards/admissions/1/transfer",
            {
                "to_bed_id": 2,
            },
        ),
        (
            "POST",
            "/api/wards/admissions/1/discharge",
            {},
        ),
    ],
)
def test_receptionist_cannot_perform_management_or_clinical_actions(
    client,
    clinic,
    make_user,
    auth_headers_for,
    method,
    path,
    payload,
):
    user = make_user(
        clinic,
        role=Role.RECEPTIONIST,
    )

    response = client.open(
        path,
        method=method,
        json=payload,
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 403


# ============================================================================
# CREATE WARD
# ============================================================================


def test_create_ward_route_success(
    client,
    clinic,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/wards",
        json={
            "name": "  Surgical Ward  ",
            "ward_type": WardType.GENERAL.value,
            "capacity": 10,
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["message"] == (
        "Ward created successfully"
    )

    ward = body["ward"]

    assert ward["name"] == "Surgical Ward"
    assert ward["capacity"] == 10
    assert ward["ward_type"] == WardType.GENERAL.value


def test_create_ward_route_rejects_client_clinic_override(
    client,
    clinic,
    make_clinic,
    user,
    auth_headers_for,
):
    foreign_clinic = make_clinic()

    response = client.post(
        "/api/wards",
        json={
            "name": "Ward",
            "capacity": 5,
            "clinic_id": foreign_clinic.id,
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["error"] == "Validation failed"
    assert body["details"]


def test_create_ward_route_rejects_invalid_payload(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/wards",
        json={
            "name": "",
            "capacity": -1,
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["error"] == "Validation failed"
    assert body["details"]


def test_create_ward_route_rejects_unknown_fields(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/wards",
        json={
            "name": "Ward",
            "capacity": 5,
            "unexpected": "blocked",
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 422


def test_create_ward_route_maps_domain_error(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    ward_routes,
):
    monkeypatch.setattr(
        ward_routes,
        "create_ward",
        Mock(
            side_effect=ConflictError(
                "Ward already exists"
            )
        ),
    )

    response = client.post(
        "/api/wards",
        json={
            "name": "Duplicate Ward",
            "capacity": 5,
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 409
    assert response.get_json()["error"] == (
        "Ward already exists"
    )


# ============================================================================
# LIST WARDS
# ============================================================================


def test_list_wards_route_success(
    client,
    clinic,
    user,
    auth_headers_for,
):
    _create_ward(
        clinic,
        name="General Ward",
    )

    _create_ward(
        clinic,
        name="Surgical Ward",
    )

    response = client.get(
        "/api/wards",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    names = {
        item["name"]
        for item in body
    }

    assert "General Ward" in names
    assert "Surgical Ward" in names


def test_list_wards_route_filters_by_type(
    client,
    clinic,
    user,
    auth_headers_for,
):
    _create_ward(
        clinic,
        name="General Ward",
        ward_type=WardType.GENERAL,
    )

    response = client.get(
        (
            "/api/wards"
            f"?ward_type={WardType.GENERAL.value}"
        ),
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body

    assert all(
        item["ward_type"]
        == WardType.GENERAL.value
        for item in body
    )


def test_list_wards_route_rejects_invalid_type(
    client,
    user,
    auth_headers_for,
):
    response = client.get(
        "/api/wards?ward_type=NOT_REAL",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 422

    assert "Invalid ward type" in (
        response.get_json()["error"]
    )


# ============================================================================
# GET WARD
# ============================================================================


def test_get_ward_route_success(
    client,
    clinic,
    user,
    auth_headers_for,
):
    ward = _create_ward(
        clinic,
        name="Recovery Ward",
        capacity=8,
    )

    response = client.get(
        f"/api/wards/{ward.id}",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["name"] == "Recovery Ward"
    assert body["capacity"] == 8
    assert body["ward_type"] == (
        WardType.GENERAL.value
    )


def test_get_ward_route_missing(
    client,
    user,
    auth_headers_for,
):
    response = client.get(
        "/api/wards/999999",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 404

    assert "Ward 999999 not found" in (
        response.get_json()["error"]
    )


def test_get_ward_route_enforces_clinic_isolation(
    client,
    clinic,
    make_clinic,
    make_user,
    auth_headers_for,
):
    foreign_clinic = make_clinic()

    foreign_ward = _create_ward(
        foreign_clinic,
        name="Foreign Ward",
    )

    local_user = make_user(
        clinic,
        role=Role.ADMIN,
    )

    response = client.get(
        f"/api/wards/{foreign_ward.id}",
        headers=_headers(
            auth_headers_for,
            local_user,
        ),
    )

    assert response.status_code == 404


# ============================================================================
# OCCUPANCY
# ============================================================================


def test_get_ward_occupancy_route_success(
    client,
    clinic,
    user,
    auth_headers_for,
):
    ward, _ = _create_bed(
        clinic,
        capacity=2,
    )

    response = client.get(
        f"/api/wards/{ward.id}/occupancy",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["ward_id"] == ward.id
    assert body["clinic_id"] == clinic.id
    assert body["capacity"] == 2
    assert body["total_beds"] == 1


def test_get_ward_occupancy_route_missing_ward(
    client,
    user,
    auth_headers_for,
):
    response = client.get(
        "/api/wards/999999/occupancy",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 404


# ============================================================================
# ADD BED
# ============================================================================


def test_add_bed_route_success(
    client,
    clinic,
    user,
    auth_headers_for,
):
    ward = _create_ward(
        clinic,
        capacity=3,
    )

    response = client.post(
        f"/api/wards/{ward.id}/beds",
        json={
            "bed_number": "  B-101  ",
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["message"] == (
        "Bed added successfully"
    )

    assert body["bed"]["ward_id"] == ward.id
    assert body["bed"]["bed_number"] == "B-101"
    assert body["bed"]["status"] == (
        BedStatus.AVAILABLE.value
    )


def test_add_bed_route_rejects_invalid_payload(
    client,
    clinic,
    user,
    auth_headers_for,
):
    ward = _create_ward(clinic)

    response = client.post(
        f"/api/wards/{ward.id}/beds",
        json={
            "bed_number": "",
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 422


def test_add_bed_route_missing_ward(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/wards/999999/beds",
        json={
            "bed_number": "B-001",
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 404


# ============================================================================
# LIST / GET BEDS
# ============================================================================


def test_list_beds_route_success(
    client,
    clinic,
    user,
    auth_headers_for,
):
    ward = _create_ward(
        clinic,
        capacity=2,
    )

    ward_service.add_bed(
        ward.id,
        "B-002",
        clinic.id,
    )

    ward_service.add_bed(
        ward.id,
        "B-001",
        clinic.id,
    )

    response = client.get(
        f"/api/wards/{ward.id}/beds",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert [
        item["bed_number"]
        for item in body
    ] == [
        "B-001",
        "B-002",
    ]


def test_list_beds_route_filters_status(
    client,
    clinic,
    user,
    auth_headers_for,
):
    ward = _create_ward(
        clinic,
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

    response = client.get(
        (
            f"/api/wards/{ward.id}/beds"
            f"?status={BedStatus.MAINTENANCE.value}"
        ),
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    ids = {
        item["id"]
        for item in body
    }

    assert maintenance.id in ids
    assert available.id not in ids


def test_list_beds_route_rejects_invalid_status(
    client,
    clinic,
    user,
    auth_headers_for,
):
    ward = _create_ward(clinic)

    response = client.get(
        (
            f"/api/wards/{ward.id}/beds"
            "?status=INVALID"
        ),
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 422

    assert "Invalid bed status" in (
        response.get_json()["error"]
    )


def test_get_bed_route_success(
    client,
    clinic,
    user,
    auth_headers_for,
):
    ward, bed = _create_bed(
        clinic,
        bed_number="B-100",
    )

    response = client.get(
        f"/api/wards/beds/{bed.id}",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body == {
        "id": bed.id,
        "ward_id": ward.id,
        "bed_number": "B-100",
        "status": BedStatus.AVAILABLE.value,
    }


def test_get_bed_route_missing(
    client,
    user,
    auth_headers_for,
):
    response = client.get(
        "/api/wards/beds/999999",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 404


# ============================================================================
# BED MAINTENANCE
# ============================================================================


def test_set_bed_maintenance_route_success(
    client,
    clinic,
    user,
    auth_headers_for,
):
    _, bed = _create_bed(clinic)

    response = client.patch(
        f"/api/wards/beds/{bed.id}/maintenance",
        json={
            "under_maintenance": True,
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["message"] == (
        "Bed maintenance status updated"
    )
    assert body["bed"]["id"] == bed.id
    assert body["bed"]["status"] == (
        BedStatus.MAINTENANCE.value
    )


def test_set_bed_maintenance_route_restores_bed(
    client,
    clinic,
    user,
    auth_headers_for,
):
    _, bed = _create_bed(clinic)

    ward_service.set_bed_maintenance(
        bed.id,
        True,
        clinic.id,
    )

    response = client.patch(
        f"/api/wards/beds/{bed.id}/maintenance",
        json={
            "under_maintenance": False,
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200

    assert (
        response.get_json()["bed"]["status"]
        == BedStatus.AVAILABLE.value
    )


def test_set_bed_maintenance_route_rejects_invalid_payload(
    client,
    clinic,
    user,
    auth_headers_for,
):
    _, bed = _create_bed(clinic)

    response = client.patch(
        f"/api/wards/beds/{bed.id}/maintenance",
        json={
            "under_maintenance": "not-a-boolean",
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 422


# ============================================================================
# RESERVATIONS
# ============================================================================


def test_reserve_bed_route_success(
    client,
    clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    patient = make_patient(
        clinic=clinic,
    )

    _, bed = _create_bed(clinic)

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.post(
        "/api/wards/reservations",
        json={
            "patient_id": patient.id,
            "bed_id": bed.id,
            "reason": "Expected admission",
            "expires_at": _future_expiry().isoformat(),
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["message"] == (
        "Bed reserved successfully"
    )

    reservation = body["reservation"]

    assert reservation["patient_id"] == patient.id
    assert reservation["bed_id"] == bed.id
    assert reservation["status"] == (
        ReservationStatus.PENDING.value
    )


def test_reserve_bed_route_rejects_invalid_payload(
    client,
    clinic,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/wards/reservations",
        json={
            "patient_id": 0,
            "bed_id": 0,
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 422


def test_reserve_bed_route_rejects_client_staff_override(
    client,
    clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    patient = make_patient(
        clinic=clinic,
    )

    _, bed = _create_bed(clinic)

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.post(
        "/api/wards/reservations",
        json={
            "patient_id": patient.id,
            "bed_id": bed.id,
            "reserved_by_id": 999999,
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 422


def test_list_reservations_route_success(
    client,
    clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    patient, staff, bed, reservation = (
        _create_reservation(
            clinic,
            make_patient,
            make_staff,
        )
    )

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.get(
        "/api/wards/reservations",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200

    ids = {
        item["id"]
        for item in response.get_json()
    }

    assert reservation.id in ids
    assert patient.id
    assert bed.id


def test_list_reservations_route_filters_status(
    client,
    clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    _, staff, _, reservation = (
        _create_reservation(
            clinic,
            make_patient,
            make_staff,
        )
    )

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.get(
        (
            "/api/wards/reservations"
            f"?status={ReservationStatus.PENDING.value}"
        ),
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200

    assert any(
        item["id"] == reservation.id
        for item in response.get_json()
    )


def test_list_reservations_route_rejects_invalid_status(
    client,
    user,
    auth_headers_for,
):
    response = client.get(
        "/api/wards/reservations?status=INVALID",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 422

    assert "Invalid reservation status" in (
        response.get_json()["error"]
    )


def test_list_reservations_route_rejects_invalid_patient_id(
    client,
    user,
    auth_headers_for,
):
    response = client.get(
        "/api/wards/reservations?patient_id=0",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 422


def test_list_reservations_route_rejects_invalid_bed_id(
    client,
    user,
    auth_headers_for,
):
    response = client.get(
        "/api/wards/reservations?bed_id=0",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 422


def test_get_reservation_route_success(
    client,
    clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    _, staff, _, reservation = (
        _create_reservation(
            clinic,
            make_patient,
            make_staff,
        )
    )

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.get(
        f"/api/wards/reservations/{reservation.id}",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["id"] == reservation.id


def test_get_reservation_route_missing(
    client,
    user,
    auth_headers_for,
):
    response = client.get(
        "/api/wards/reservations/999999",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 404


# ============================================================================
# ACTIVE RESERVATION LOOKUPS
# ============================================================================


def test_get_patient_active_reservation_route_success(
    client,
    clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    patient, staff, _, reservation = (
        _create_reservation(
            clinic,
            make_patient,
            make_staff,
        )
    )

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.get(
        f"/api/wards/patients/{patient.id}/reservation",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200
    assert (
        response.get_json()["id"]
        == reservation.id
    )


def test_get_patient_active_reservation_route_returns_404_when_missing(
    client,
    clinic,
    make_patient,
    user,
    auth_headers_for,
):
    patient = make_patient(
        clinic=clinic,
    )

    response = client.get(
        f"/api/wards/patients/{patient.id}/reservation",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 404

    assert response.get_json()["message"] == (
        "No active reservation found"
    )


def test_get_patient_active_reservation_route_rejects_invalid_id(
    client,
    user,
    auth_headers_for,
):
    response = client.get(
        "/api/wards/patients/0/reservation",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 422


def test_get_bed_active_reservation_route_success(
    client,
    clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    _, staff, bed, reservation = (
        _create_reservation(
            clinic,
            make_patient,
            make_staff,
        )
    )

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.get(
        f"/api/wards/beds/{bed.id}/reservation",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200

    assert (
        response.get_json()["id"]
        == reservation.id
    )


def test_get_bed_active_reservation_route_returns_404_when_missing(
    client,
    clinic,
    user,
    auth_headers_for,
):
    _, bed = _create_bed(clinic)

    response = client.get(
        f"/api/wards/beds/{bed.id}/reservation",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 404


def test_get_bed_active_reservation_route_rejects_invalid_id(
    client,
    user,
    auth_headers_for,
):
    response = client.get(
        "/api/wards/beds/0/reservation",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 422


# ============================================================================
# CANCEL RESERVATION
# ============================================================================


def test_cancel_reservation_route_success(
    client,
    clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    _, staff, _, reservation = (
        _create_reservation(
            clinic,
            make_patient,
            make_staff,
        )
    )

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.post(
        (
            f"/api/wards/reservations/"
            f"{reservation.id}/cancel"
        ),
        json={
            "reason": "Patient no longer requires bed",
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["message"] == (
        "Bed reservation cancelled successfully"
    )

    assert (
        body["reservation"]["status"]
        == ReservationStatus.CANCELLED.value
    )


def test_cancel_reservation_route_rejects_invalid_payload(
    client,
    clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    _, staff, _, reservation = (
        _create_reservation(
            clinic,
            make_patient,
            make_staff,
        )
    )

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.post(
        (
            f"/api/wards/reservations/"
            f"{reservation.id}/cancel"
        ),
        json={
            "reason": "x" * 256,
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 422


# ============================================================================
# ADMISSION
# ============================================================================


def test_admit_patient_route_success(
    client,
    clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    patient = make_patient(
        clinic=clinic,
    )

    _, bed = _create_bed(clinic)

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.post(
        "/api/wards/admissions",
        json={
            "patient_id": patient.id,
            "bed_id": bed.id,
            "reason": "Observation",
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["message"] == (
        "Patient admitted successfully"
    )

    admission = body["admission"]

    assert admission["patient_id"] == patient.id
    assert admission["bed_id"] == bed.id
    assert admission["status"] == (
        AdmissionStatus.ADMITTED.value
    )


def test_admit_patient_route_rejects_invalid_payload(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/wards/admissions",
        json={
            "patient_id": 0,
            "bed_id": 0,
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 422


def test_admit_patient_route_rejects_client_staff_override(
    client,
    clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    patient = make_patient(
        clinic=clinic,
    )

    _, bed = _create_bed(clinic)

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.post(
        "/api/wards/admissions",
        json={
            "patient_id": patient.id,
            "bed_id": bed.id,
            "admitted_by_id": 999999,
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 422


def test_get_admission_route_success(
    client,
    clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    patient, staff, bed, admission = (
        _create_admission(
            clinic,
            make_patient,
            make_staff,
        )
    )

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.get(
        f"/api/wards/admissions/{admission.id}",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["id"] == admission.id
    assert body["patient_id"] == patient.id
    assert body["bed_id"] == bed.id
    assert body["status"] == (
        AdmissionStatus.ADMITTED.value
    )


def test_get_admission_route_missing(
    client,
    user,
    auth_headers_for,
):
    response = client.get(
        "/api/wards/admissions/999999",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 404


# ============================================================================
# PATIENT ADMISSIONS
# ============================================================================


def test_list_patient_admissions_route_success(
    client,
    clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    patient, staff, _, first = (
        _create_admission(
            clinic,
            make_patient,
            make_staff,
            reason="First admission",
        )
    )

    ward_service.discharge_patient(
        first.id,
        clinic.id,
        actor_user_id=staff.user_id,
    )

    _, second_bed = _create_bed(
        clinic,
        ward_name="Second Ward",
    )

    second = ward_service.admit_patient(
        patient_id=patient.id,
        bed_id=second_bed.id,
        admitted_by_id=staff.id,
        clinic_id=clinic.id,
        actor_user_id=staff.user_id,
        reason="Second admission",
    )

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.get(
        f"/api/wards/patients/{patient.id}/admissions",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200

    ids = {
        item["id"]
        for item in response.get_json()
    }

    assert first.id in ids
    assert second.id in ids


def test_list_patient_admissions_route_rejects_invalid_patient_id(
    client,
    user,
    auth_headers_for,
):
    response = client.get(
        "/api/wards/patients/0/admissions",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 422


def test_current_patient_admission_route_success(
    client,
    clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    patient, staff, _, admission = (
        _create_admission(
            clinic,
            make_patient,
            make_staff,
        )
    )

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.get(
        (
            f"/api/wards/patients/"
            f"{patient.id}/current-admission"
        ),
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["id"] == admission.id
    assert body["status"] == (
        AdmissionStatus.ADMITTED.value
    )


def test_current_patient_admission_route_returns_404_when_missing(
    client,
    clinic,
    make_patient,
    user,
    auth_headers_for,
):
    patient = make_patient(
        clinic=clinic,
    )

    response = client.get(
        (
            f"/api/wards/patients/"
            f"{patient.id}/current-admission"
        ),
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 404

    assert response.get_json()["message"] == (
        "No active admission found"
    )


def test_current_patient_admission_route_rejects_invalid_patient_id(
    client,
    user,
    auth_headers_for,
):
    response = client.get(
        "/api/wards/patients/0/current-admission",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 422


# ============================================================================
# ADMISSION FROM RESERVATION
# ============================================================================


def test_admit_from_reservation_route_success(
    client,
    clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    patient, staff, bed, reservation = (
        _create_reservation(
            clinic,
            make_patient,
            make_staff,
            expires_at=_future_expiry(),
            reason="Reserved admission",
        )
    )

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.post(
        (
            f"/api/wards/reservations/"
            f"{reservation.id}/admit"
        ),
        json={
            "reason": "Final admission",
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["message"] == (
        "Patient admitted from reservation"
    )

    admission = body["admission"]

    assert admission["patient_id"] == patient.id
    assert admission["bed_id"] == bed.id
    assert admission["reservation_id"] == (
        reservation.id
    )
    assert admission["status"] == (
        AdmissionStatus.ADMITTED.value
    )


def test_admit_from_reservation_route_missing_reservation(
    client,
    clinic,
    make_staff,
    auth_headers_for,
):
    # The route requires an authenticated user linked to Staff.
    # A generic user can reach the route but _current_staff_id()
    # returns ValidationError (422) before the service lookup.
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.post(
        "/api/wards/reservations/999999/admit",
        json={
            "reason": "Admission",
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 404


def test_admit_from_reservation_route_rejects_invalid_payload(
    client,
    clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    _, staff, _, reservation = (
        _create_reservation(
            clinic,
            make_patient,
            make_staff,
            expires_at=_future_expiry(),
        )
    )

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.post(
        (
            f"/api/wards/reservations/"
            f"{reservation.id}/admit"
        ),
        json={
            "reason": "x" * 256,
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 422


# ============================================================================
# TRANSFER
# ============================================================================


def test_transfer_bed_route_success(
    client,
    clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    patient, staff, source_bed, admission = (
        _create_admission(
            clinic,
            make_patient,
            make_staff,
        )
    )

    _, destination_bed = _create_bed(
        clinic,
        ward_name="Transfer Ward",
        bed_number="B-002",
    )

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.post(
        (
            f"/api/wards/admissions/"
            f"{admission.id}/transfer"
        ),
        json={
            "to_bed_id": destination_bed.id,
            "reason": "Clinical transfer",
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["message"] == (
        "Patient transferred successfully"
    )

    transfer = body["transfer"]

    assert transfer["admission_id"] == admission.id
    assert transfer["from_bed_id"] == source_bed.id
    assert transfer["to_bed_id"] == (
        destination_bed.id
    )

    assert patient.id == admission.patient_id


def test_transfer_bed_route_rejects_invalid_payload(
    client,
    clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    _, staff, _, admission = _create_admission(
        clinic,
        make_patient,
        make_staff,
    )

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.post(
        (
            f"/api/wards/admissions/"
            f"{admission.id}/transfer"
        ),
        json={
            "to_bed_id": 0,
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 422


def test_transfer_bed_route_missing_admission(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/wards/admissions/999999/transfer",
        json={
            "to_bed_id": 1,
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 404


# ============================================================================
# DISCHARGE
# ============================================================================


def test_discharge_patient_route_success(
    client,
    clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    patient, staff, bed, admission = (
        _create_admission(
            clinic,
            make_patient,
            make_staff,
            reason="Observation",
        )
    )

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.post(
        (
            f"/api/wards/admissions/"
            f"{admission.id}/discharge"
        ),
        json={
            "reason": "Patient recovered",
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["message"] == (
        "Patient discharged successfully"
    )

    result = body["admission"]

    assert result["id"] == admission.id
    assert result["patient_id"] == patient.id
    assert result["bed_id"] == bed.id
    assert result["status"] == (
        AdmissionStatus.DISCHARGED.value
    )


def test_discharge_patient_route_allows_no_reason(
    client,
    clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    _, staff, _, admission = _create_admission(
        clinic,
        make_patient,
        make_staff,
    )

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.post(
        (
            f"/api/wards/admissions/"
            f"{admission.id}/discharge"
        ),
        json={},
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200

    assert (
        response.get_json()["admission"]["status"]
        == AdmissionStatus.DISCHARGED.value
    )


def test_discharge_patient_route_missing_admission(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/wards/admissions/999999/discharge",
        json={},
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 404


def test_discharge_patient_route_rejects_invalid_payload(
    client,
    clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    _, staff, _, admission = _create_admission(
        clinic,
        make_patient,
        make_staff,
    )

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.post(
        (
            f"/api/wards/admissions/"
            f"{admission.id}/discharge"
        ),
        json={
            "reason": "x" * 256,
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 422


# ============================================================================
# CLINIC ISOLATION
# ============================================================================


def test_get_bed_route_rejects_foreign_clinic_bed(
    client,
    clinic,
    make_clinic,
    make_user,
    auth_headers_for,
):
    foreign_clinic = make_clinic()

    _, foreign_bed = _create_bed(
        foreign_clinic,
        ward_name="Foreign Ward",
    )

    local_user = make_user(
        clinic,
        role=Role.ADMIN,
    )

    response = client.get(
        f"/api/wards/beds/{foreign_bed.id}",
        headers=_headers(
            auth_headers_for,
            local_user,
        ),
    )

    assert response.status_code == 404


def test_list_reservations_uses_authenticated_clinic(
    client,
    clinic,
    make_clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    foreign_clinic = make_clinic()

    _, _, _, local_reservation = (
        _create_reservation(
            clinic,
            make_patient,
            make_staff,
        )
    )

    _, _, _, foreign_reservation = (
        _create_reservation(
            foreign_clinic,
            make_patient,
            make_staff,
        )
    )

    local_staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    user = db.session.get(
        type(local_staff.user),
        local_staff.user_id,
    )

    response = client.get(
        (
            "/api/wards/reservations"
            f"?clinic_id={foreign_clinic.id}"
        ),
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200

    ids = {
        item["id"]
        for item in response.get_json()
    }

    assert local_reservation.id in ids
    assert foreign_reservation.id not in ids


# ============================================================================
# AUTH HELPERS / ACCOUNT STATE
# ============================================================================


def test_route_rejects_inactive_authenticated_user(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    inactive_user = make_user(
        clinic,
        role=Role.ADMIN,
        is_active=False,
    )

    response = client.get(
        "/api/wards",
        headers=_headers(
            auth_headers_for,
            inactive_user,
        ),
    )

    assert response.status_code == 422

    assert response.get_json()["error"] == (
        "User account is inactive"
    )


def test_reservation_route_requires_linked_staff(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    user_without_staff = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        "/api/wards/reservations",
        json={
            "patient_id": 1,
            "bed_id": 1,
        },
        headers=_headers(
            auth_headers_for,
            user_without_staff,
        ),
    )

    assert response.status_code == 422

    assert response.get_json()["error"] == (
        "Authenticated user is not linked to a staff record"
    )


# ============================================================================
# ROUTE / SERVICE ERROR MAPPING
# ============================================================================


def test_get_ward_route_maps_not_found_error(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    ward_routes,
):
    monkeypatch.setattr(
        ward_routes,
        "get_ward",
        Mock(
            side_effect=NotFoundError(
                "Ward 123 not found"
            )
        ),
    )

    response = client.get(
        "/api/wards/123",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == (
        "Ward 123 not found"
    )


def test_add_bed_route_maps_conflict_error(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    ward_routes,
):
    monkeypatch.setattr(
        ward_routes,
        "add_bed",
        Mock(
            side_effect=ConflictError(
                "Ward has reached capacity"
            )
        ),
    )

    response = client.post(
        "/api/wards/1/beds",
        json={
            "bed_number": "B-001",
        },
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 409

    assert response.get_json()["error"] == (
        "Ward has reached capacity"
    )


def test_get_ward_route_maps_validation_error(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    ward_routes,
):
    monkeypatch.setattr(
        ward_routes,
        "get_ward",
        Mock(
            side_effect=ValidationError(
                "Invalid ward"
            )
        ),
    )

    response = client.get(
        "/api/wards/1",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 422

    assert response.get_json()["error"] == (
        "Invalid ward"
    )


# ============================================================================
# RESPONSE SHAPES
# ============================================================================


def test_reservation_response_contains_expected_fields(
    client,
    clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    patient, staff, bed, reservation = (
        _create_reservation(
            clinic,
            make_patient,
            make_staff,
            expires_at=_future_expiry(),
        )
    )

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.get(
        f"/api/wards/reservations/{reservation.id}",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["id"] == reservation.id
    assert body["patient_id"] == patient.id
    assert body["bed_id"] == bed.id
    assert "reserved_by_id" in body
    assert "status" in body
    assert "reason" in body
    assert "reserved_at" in body
    assert "expires_at" in body


def test_admission_response_contains_expected_fields(
    client,
    clinic,
    make_patient,
    make_staff,
    auth_headers_for,
):
    patient, staff, bed, admission = (
        _create_admission(
            clinic,
            make_patient,
            make_staff,
        )
    )

    user = db.session.get(
        type(staff.user),
        staff.user_id,
    )

    response = client.get(
        f"/api/wards/admissions/{admission.id}",
        headers=_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["id"] == admission.id
    assert body["patient_id"] == patient.id
    assert body["bed_id"] == bed.id
    assert body["admitted_by_id"] == staff.id
    assert body["status"] == (
        AdmissionStatus.ADMITTED.value
    )
    assert "admitted_at" in body
    assert "discharged_at" in body