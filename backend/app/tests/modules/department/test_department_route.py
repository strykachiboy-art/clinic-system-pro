from __future__ import annotations

from app.core.enums.department_enums import DepartmentStatus
from app.extensions import db
from app.modules.department.models.department_model import Department


def make_department(
    clinic,
    *,
    code="CARD",
    name="Cardiology",
    status=DepartmentStatus.ACTIVE,
):
    department = Department(
        clinic_id=clinic.id,
        code=code,
        name=name,
        status=status,
    )

    db.session.add(department)
    db.session.flush()

    return department


def test_department_routes_require_auth(
    client,
):
    response = client.get(
        "/api/v1/departments"
    )

    assert response.status_code in (401, 422)


def test_department_management_is_admin_only(
    client,
    user,
    auth_headers_for,
):
    from app.core.enums.role_enums import Role

    doctor = type(user)(
        clinic_id=user.clinic_id,
        role=Role.DOCTOR,
        is_active=True,
        email="department-doctor@test.com",
    )
    doctor.set_password("supersecret")

    db.session.add(doctor)
    db.session.flush()

    headers = auth_headers_for(doctor)

    response = client.post(
        "/api/v1/departments",
        headers=headers,
        json={
            "code": "ER",
            "name": "Emergency",
        },
    )

    assert response.status_code == 403


def test_create_department_route(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/v1/departments",
        headers=auth_headers_for(user),
        json={
            "code": " cardio ",
            "name": " Cardiology ",
            "description": " Heart care ",
        },
    )

    body = response.get_json()

    assert response.status_code == 201, body
    assert body["data"]["clinic_id"] == user.clinic_id
    assert body["data"]["code"] == "CARDIO"
    assert body["data"]["name"] == "Cardiology"
    assert body["data"]["description"] == "Heart care"


def test_list_departments_route(
    client,
    user,
    auth_headers_for,
    clinic,
):
    make_department(
        clinic=clinic,
        code="CARD",
        name="Cardiology",
    )

    response = client.get(
        "/api/v1/departments",
        headers=auth_headers_for(user),
    )

    body = response.get_json()

    assert response.status_code == 200, body
    assert len(body["data"]) == 1
    assert body["data"][0]["name"] == "Cardiology"


def test_department_route_enforces_tenant_isolation(
    client,
    user,
    auth_headers_for,
    make_clinic,
):
    other_clinic = make_clinic()

    department = make_department(
        clinic=other_clinic,
        code="ER",
        name="Emergency",
    )

    response = client.get(
        f"/api/v1/departments/{department.id}",
        headers=auth_headers_for(user),
    )

    assert response.status_code == 404


def test_update_department_route(
    client,
    user,
    auth_headers_for,
    clinic,
):
    department = make_department(
        clinic=clinic,
        code="CARD",
        name="Cardiology",
    )

    response = client.patch(
        f"/api/v1/departments/{department.id}",
        headers=auth_headers_for(user),
        json={
            "name": "Cardiology & Heart Care",
        },
    )

    body = response.get_json()

    assert response.status_code == 200, body
    assert body["data"]["name"] == "Cardiology & Heart Care"


def test_department_status_route(
    client,
    user,
    auth_headers_for,
    clinic,
):
    department = make_department(
        clinic=clinic,
        code="ER",
        name="Emergency",
    )

    response = client.patch(
        f"/api/v1/departments/{department.id}/status",
        headers=auth_headers_for(user),
        json={
            "status": DepartmentStatus.INACTIVE.value,
        },
    )

    body = response.get_json()

    assert response.status_code == 200, body
    assert body["data"]["status"] == DepartmentStatus.INACTIVE.value


def test_department_route_rejects_duplicate_code(
    client,
    user,
    auth_headers_for,
    clinic,
):
    make_department(
        clinic=clinic,
        code="ER",
        name="Emergency",
    )

    second = make_department(
        clinic=clinic,
        code="CARD",
        name="Cardiology",
    )

    response = client.patch(
        f"/api/v1/departments/{second.id}",
        headers=auth_headers_for(user),
        json={
            "code": "ER",
        },
    )

    assert response.status_code == 409
