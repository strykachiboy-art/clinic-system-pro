from __future__ import annotations

import pytest

from app.core.enums.department_enums import DepartmentStatus
from app.core.enums.role_enums import Role
from app.extensions import db
from app.modules.department.models.department_model import Department


@pytest.fixture()
def admin_headers(user, auth_headers_for):
    return auth_headers_for(user)


@pytest.fixture()
def admin_staff(make_staff, clinic):
    return make_staff(
        clinic=clinic,
        role=Role.ADMIN,
    )


@pytest.fixture()
def doctor_headers(make_user, clinic, auth_headers_for):
    doctor = make_user(
        clinic=clinic,
        role=Role.DOCTOR,
    )
    return auth_headers_for(doctor)


def make_department(
    clinic,
    *,
    name="Cardiology",
    code="CARD",
):
    department = Department(
        clinic_id=clinic.id,
        name=name,
        code=code,
        status=DepartmentStatus.ACTIVE,
    )

    db.session.add(department)
    db.session.flush()

    return department


def test_update_staff_department_requires_management_role(
    client,
    doctor_headers,
):
    response = client.patch(
        "/api/v1/staff/1/department",
        headers=doctor_headers,
        json={
            "department_id": 1,
        },
    )

    assert response.status_code == 403


def test_update_staff_department_assigns_department(
    client,
    admin_headers,
    admin_staff,
    clinic,
):
    department = make_department(
        clinic=clinic,
    )

    response = client.patch(
        f"/api/v1/staff/{admin_staff.id}/department",
        headers=admin_headers,
        json={
            "department_id": department.id,
        },
    )

    body = response.get_json()

    assert response.status_code == 200, body
    assert body["data"]["department_id"] == department.id


def test_update_staff_department_switches_primary_membership(
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

    first_response = client.patch(
        f"/api/v1/staff/{admin_staff.id}/department",
        headers=admin_headers,
        json={"department_id": first.id},
    )
    assert first_response.status_code == 200

    response = client.patch(
        f"/api/v1/staff/{admin_staff.id}/department",
        headers=admin_headers,
        json={"department_id": second.id},
    )

    body = response.get_json()
    assert response.status_code == 200, body
    assert body["data"]["department_id"] == second.id


def test_update_staff_department_rejects_invalid_department(
    client,
    admin_headers,
    admin_staff,
):
    response = client.patch(
        f"/api/v1/staff/{admin_staff.id}/department",
        headers=admin_headers,
        json={
            "department_id": 999999,
        },
    )

    assert response.status_code == 404


def test_update_staff_department_can_clear(
    client,
    admin_headers,
    admin_staff,
    clinic,
):
    department = make_department(
        clinic=clinic,
        name="Emergency",
        code="ER",
    )

    admin_staff.department_id = department.id
    db.session.flush()

    response = client.patch(
        f"/api/v1/staff/{admin_staff.id}/department",
        headers=admin_headers,
        json={
            "department_id": None,
        },
    )

    body = response.get_json()

    assert response.status_code == 200, body
    assert body["data"]["department_id"] is None
