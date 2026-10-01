from __future__ import annotations

import pytest

from app.core.enums.department_enums import DepartmentStatus
from app.core.enums.role_enums import Role
from app.extensions import db
from app.modules.department.models.department_model import Department


def make_department(
    clinic,
    *,
    name="Cardiology",
    code="CARD",
    status=DepartmentStatus.ACTIVE,
):
    department = Department(
        clinic_id=clinic.id,
        name=name,
        code=code,
        status=status,
    )

    db.session.add(department)
    db.session.flush()

    return department


@pytest.fixture()
def admin_headers(
    user,
    auth_headers_for,
):
    return auth_headers_for(user)


@pytest.fixture()
def doctor_headers(
    make_user,
    clinic,
    auth_headers_for,
):
    doctor = make_user(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    return auth_headers_for(
        doctor
    )


@pytest.fixture()
def admin_staff(
    make_staff,
    clinic,
):
    return make_staff(
        clinic=clinic,
        role=Role.ADMIN,
    )


def test_assign_staff_department_route(
    client,
    admin_headers,
    admin_staff,
    clinic,
):
    department = make_department(
        clinic
    )

    response = client.post(
        f"/api/v1/staff-departments/staff/"
        f"{admin_staff.id}/department/{department.id}",
        headers=admin_headers,
        json={
            "department_id": department.id,
            "is_primary": True,
        },
    )

    body = response.get_json()

    assert response.status_code == 201, body
    assert body["data"]["staff_id"] == admin_staff.id
    assert body["data"]["department_id"] == department.id
    assert body["data"]["is_primary"] is True
    assert body["data"]["status"] == "active"


def test_assign_staff_department_requires_management_role(
    client,
    doctor_headers,
    admin_staff,
    clinic,
):
    department = make_department(
        clinic
    )

    response = client.post(
        f"/api/v1/staff-departments/staff/"
        f"{admin_staff.id}/department/{department.id}",
        headers=doctor_headers,
        json={
            "department_id": department.id,
        },
    )

    assert response.status_code == 403


def test_list_staff_departments_route(
    client,
    admin_headers,
    admin_staff,
    clinic,
):
    department = make_department(
        clinic
    )

    client.post(
        f"/api/v1/staff-departments/staff/"
        f"{admin_staff.id}/department/{department.id}",
        headers=admin_headers,
        json={
            "department_id": department.id,
        },
    )

    response = client.get(
        f"/api/v1/staff-departments/staff/"
        f"{admin_staff.id}",
        headers=admin_headers,
    )

    body = response.get_json()

    assert response.status_code == 200, body
    assert len(body["data"]) == 1
    assert (
        body["data"][0]["department_id"]
        == department.id
    )


def test_list_department_staff_route(
    client,
    admin_headers,
    admin_staff,
    clinic,
):
    department = make_department(
        clinic
    )

    client.post(
        f"/api/v1/staff-departments/staff/"
        f"{admin_staff.id}/department/{department.id}",
        headers=admin_headers,
        json={
            "department_id": department.id,
        },
    )

    response = client.get(
        f"/api/v1/staff-departments/department/"
        f"{department.id}",
        headers=admin_headers,
    )

    body = response.get_json()

    assert response.status_code == 200, body
    assert len(body["data"]) == 1
    assert (
        body["data"][0]["staff_id"]
        == admin_staff.id
    )


def test_set_primary_department_route(
    client,
    admin_headers,
    admin_staff,
    clinic,
):
    first = make_department(
        clinic,
        name="Cardiology",
        code="CARD",
    )

    second = make_department(
        clinic,
        name="Emergency",
        code="ER",
    )

    client.post(
        f"/api/v1/staff-departments/staff/"
        f"{admin_staff.id}/department/{first.id}",
        headers=admin_headers,
        json={
            "department_id": first.id,
        },
    )

    client.post(
        f"/api/v1/staff-departments/staff/"
        f"{admin_staff.id}/department/{second.id}",
        headers=admin_headers,
        json={
            "department_id": second.id,
        },
    )

    response = client.post(
        f"/api/v1/staff-departments/staff/"
        f"{admin_staff.id}/department/{second.id}/primary",
        headers=admin_headers,
    )

    body = response.get_json()

    assert response.status_code == 200, body
    assert (
        body["data"]["department_id"]
        == second.id
    )
    assert body["data"]["is_primary"] is True


def test_remove_staff_department_route_ends_membership(
    client,
    admin_headers,
    admin_staff,
    clinic,
):
    department = make_department(
        clinic
    )

    client.post(
        f"/api/v1/staff-departments/staff/"
        f"{admin_staff.id}/department/{department.id}",
        headers=admin_headers,
        json={
            "department_id": department.id,
        },
    )

    response = client.delete(
        f"/api/v1/staff-departments/staff/"
        f"{admin_staff.id}/department/{department.id}",
        headers=admin_headers,
    )

    body = response.get_json()

    assert response.status_code == 200, body
    assert body["data"]["status"] == "ended"
    assert body["data"]["is_primary"] is False


def test_list_staff_departments_can_include_ended(
    client,
    admin_headers,
    admin_staff,
    clinic,
):
    department = make_department(
        clinic
    )

    client.post(
        f"/api/v1/staff-departments/staff/"
        f"{admin_staff.id}/department/{department.id}",
        headers=admin_headers,
        json={
            "department_id": department.id,
        },
    )

    client.delete(
        f"/api/v1/staff-departments/staff/"
        f"{admin_staff.id}/department/{department.id}",
        headers=admin_headers,
    )

    response = client.get(
        f"/api/v1/staff-departments/staff/"
        f"{admin_staff.id}?include_ended=true",
        headers=admin_headers,
    )

    body = response.get_json()

    assert response.status_code == 200, body
    assert len(body["data"]) == 1
    assert body["data"][0]["status"] == "ended"


def test_assign_department_route_enforces_body_url_match(
    client,
    admin_headers,
    admin_staff,
    clinic,
):
    department = make_department(
        clinic
    )

    response = client.post(
        f"/api/v1/staff-departments/staff/"
        f"{admin_staff.id}/department/{department.id}",
        headers=admin_headers,
        json={
            "department_id": department.id + 999,
        },
    )

    assert response.status_code == 422


def test_staff_department_route_enforces_tenant_isolation(
    client,
    admin_headers,
    admin_staff,
    make_clinic,
    make_staff,
    db,
):
    other_clinic = make_clinic()

    other_staff = make_staff(
        clinic=other_clinic
    )

    other_department = make_department(
        other_clinic,
        name="Emergency",
        code="ER",
    )

    response = client.post(
        f"/api/v1/staff-departments/staff/"
        f"{admin_staff.id}/department/"
        f"{other_department.id}",
        headers=admin_headers,
        json={
            "department_id": other_department.id,
        },
    )

    assert response.status_code == 404

    response = client.get(
        f"/api/v1/staff-departments/staff/"
        f"{other_staff.id}",
        headers=admin_headers,
    )

    assert response.status_code == 404
