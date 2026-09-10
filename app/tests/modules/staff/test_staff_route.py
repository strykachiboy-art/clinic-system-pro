from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.enums.excuse_enums import (
    ExcuseStatus,
    ExcuseType,
)
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import (
    LeaveStatus,
    LeaveType,
    StaffStatus,
)


@pytest.fixture
def staff_routes():
    import app.modules.staff.routes.staff_route as routes

    return routes


@pytest.fixture
def admin_context(make_authenticated_staff, clinic):
    return make_authenticated_staff(
        clinic,
        Role.ADMIN,
    )


@pytest.fixture
def admin_staff(admin_context):
    staff, _ = admin_context
    return staff


@pytest.fixture
def admin_headers(admin_context):
    _, headers = admin_context
    return headers


@pytest.fixture
def doctor_context(make_authenticated_staff, clinic):
    return make_authenticated_staff(
        clinic,
        Role.DOCTOR,
    )


@pytest.fixture
def doctor_staff(doctor_context):
    staff, _ = doctor_context
    return staff


@pytest.fixture
def doctor_headers(doctor_context):
    _, headers = doctor_context
    return headers


@pytest.fixture
def nurse_context(make_authenticated_staff, clinic):
    return make_authenticated_staff(
        clinic,
        Role.NURSE,
    )


@pytest.fixture
def nurse_staff(nurse_context):
    staff, _ = nurse_context
    return staff


@pytest.fixture
def nurse_headers(nurse_context):
    _, headers = nurse_context
    return headers


@pytest.fixture
def accountant_context(make_authenticated_staff, clinic):
    return make_authenticated_staff(
        clinic,
        Role.ACCOUNTANT,
    )


@pytest.fixture
def accountant_staff(accountant_context):
    staff, _ = accountant_context
    return staff


@pytest.fixture
def accountant_headers(accountant_context):
    _, headers = accountant_context
    return headers


@pytest.fixture
def receptionist_context(make_authenticated_staff, clinic):
    return make_authenticated_staff(
        clinic,
        Role.RECEPTIONIST,
    )


@pytest.fixture
def receptionist_headers(receptionist_context):
    _, headers = receptionist_context
    return headers


def make_staff_object(**overrides):
    values = dict(
        id=1,
        clinic_id=1,
        user_id=10,
        first_name="John",
        last_name="Doe",
        specialty="General Medicine",
        phone="08000000000",
        email="john@example.com",
        hired_at=date(2026, 1, 1),
        status=StaffStatus.ACTIVE,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    values.update(overrides)

    return SimpleNamespace(**values)


def make_leave_object(**overrides):
    values = dict(
        id=1,
        staff_id=1,
        leave_type=LeaveType.ANNUAL,
        start_date=date(2026, 9, 10),
        end_date=date(2026, 9, 12),
        reason="Annual leave",
        status=LeaveStatus.PENDING,
        reviewed_by_user_id=None,
        reviewed_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    values.update(overrides)

    return SimpleNamespace(**values)


def make_payroll_object(**overrides):
    values = dict(
        id=1,
        staff_id=1,
        pay_period_start=date(2026, 9, 1),
        pay_period_end=date(2026, 9, 30),
        base_salary=Decimal("100000.00"),
        bonuses=Decimal("5000.00"),
        deductions=Decimal("1000.00"),
        net_pay=Decimal("104000.00"),
        paid_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    values.update(overrides)

    return SimpleNamespace(**values)


def make_excuse_object(**overrides):
    values = dict(
        id=1,
        staff_id=1,
        leave_request_id=None,
        excuse_type=ExcuseType.MEDICAL,
        status=ExcuseStatus.PENDING,
        description="Medical appointment",
        document_url=None,
        rejection_reason=None,
        reviewed_by_user_id=None,
        reviewed_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    values.update(overrides)

    return SimpleNamespace(**values)


def paginated(
    items,
    *,
    page=1,
    per_page=50,
    total=None,
):
    return {
        "items": items,
        "total": len(items) if total is None else total,
        "page": page,
        "per_page": per_page,
    }


def assert_success(response, status_code):
    body = response.get_json()

    assert response.status_code == status_code, body
    assert body is not None
    assert "data" in body

    return body


def assert_error(response, status_code):
    body = response.get_json()

    assert response.status_code == status_code, body
    assert "error" in body

    return body


def test_staff_routes_require_auth(client):
    response = client.get("/api/staff")

    assert response.status_code in (401, 422)


def test_create_staff_is_admin_only(
    client,
    doctor_headers,
):
    response = client.post(
        "/api/staff",
        headers=doctor_headers,
        json={
            "first_name": "New",
            "last_name": "Staff",
        },
    )

    assert response.status_code == 403


def test_update_staff_is_admin_only(
    client,
    doctor_headers,
):
    response = client.patch(
        "/api/staff/1",
        headers=doctor_headers,
        json={
            "first_name": "Updated",
        },
    )

    assert response.status_code == 403


def test_change_staff_status_is_admin_only(
    client,
    doctor_headers,
):
    response = client.patch(
        "/api/staff/1/status",
        headers=doctor_headers,
        json={
            "status": StaffStatus.SUSPENDED.value,
        },
    )

    assert response.status_code == 403


def test_payroll_create_is_admin_or_accountant(
    client,
    doctor_headers,
):
    response = client.post(
        "/api/staff/payroll",
        headers=doctor_headers,
        json={
            "staff_id": 1,
            "pay_period_start": "2026-09-01",
            "pay_period_end": "2026-09-30",
            "base_salary": "100000",
        },
    )

    assert response.status_code == 403


def test_payroll_generate_is_admin_or_accountant(
    client,
    doctor_headers,
):
    response = client.post(
        "/api/staff/payroll/generate",
        headers=doctor_headers,
        json={
            "pay_period_start": "2026-09-01",
            "pay_period_end": "2026-09-30",
            "salary_lookup": {
                "1": "100000",
            },
        },
    )

    assert response.status_code == 403


def test_payroll_list_is_admin_or_accountant(
    client,
    doctor_headers,
):
    response = client.get(
        "/api/staff/payroll",
        headers=doctor_headers,
    )

    assert response.status_code == 403


def test_leave_approval_is_admin_only(
    client,
    doctor_headers,
):
    response = client.post(
        "/api/staff/leave/1/approve",
        headers=doctor_headers,
        json={},
    )

    assert response.status_code == 403


def test_leave_rejection_is_admin_only(
    client,
    doctor_headers,
):
    response = client.post(
        "/api/staff/leave/1/reject",
        headers=doctor_headers,
        json={},
    )

    assert response.status_code == 403


def test_excuse_approval_is_admin_only(
    client,
    doctor_headers,
):
    response = client.post(
        "/api/staff/excuses/1/approve",
        headers=doctor_headers,
        json={},
    )

    assert response.status_code == 403


def test_excuse_rejection_is_admin_only(
    client,
    doctor_headers,
):
    response = client.post(
        "/api/staff/excuses/1/reject",
        headers=doctor_headers,
        json={},
    )

    assert response.status_code == 403


def test_create_staff_success(
    client,
    admin_headers,
    admin_staff,
    monkeypatch,
    staff_routes,
):
    service = Mock(
        return_value=make_staff_object(
            clinic_id=admin_staff.clinic_id,
            first_name="Jane",
            last_name="Smith",
            specialty="Cardiology",
            phone="08111111111",
            email="jane@example.com",
            hired_at=date(2026, 9, 1),
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "create_staff",
        service,
    )

    response = client.post(
        "/api/staff",
        headers=admin_headers,
        json={
            "first_name": "Jane",
            "last_name": "Smith",
            "specialty": "Cardiology",
            "phone": "08111111111",
            "email": "jane@example.com",
            "hired_at": "2026-09-01",
        },
    )

    body = assert_success(response, 201)

    assert body["data"]["first_name"] == "Jane"
    assert body["data"]["last_name"] == "Smith"

    kwargs = service.call_args.kwargs

    assert kwargs["clinic_id"] == admin_staff.clinic_id
    assert kwargs["first_name"] == "Jane"
    assert kwargs["last_name"] == "Smith"
    assert kwargs["specialty"] == "Cardiology"
    assert kwargs["phone"] == "08111111111"
    assert kwargs["email"] == "jane@example.com"
    assert kwargs["hired_at"] == date(2026, 9, 1)


def test_create_staff_forwards_user_id(
    client,
    admin_headers,
    admin_staff,
    clinic,
    make_user,
    monkeypatch,
    staff_routes,
):
    linked_user = make_user(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    service = Mock(
        return_value=make_staff_object(
            clinic_id=admin_staff.clinic_id,
            user_id=linked_user.id,
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "create_staff",
        service,
    )

    response = client.post(
        "/api/staff",
        headers=admin_headers,
        json={
            "user_id": linked_user.id,
            "first_name": "Doctor",
            "last_name": "One",
        },
    )

    assert response.status_code == 201
    assert (
        service.call_args.kwargs["user_id"]
        == linked_user.id
    )


def test_create_staff_missing_first_name_returns_422(
    client,
    admin_headers,
):
    response = client.post(
        "/api/staff",
        headers=admin_headers,
        json={
            "last_name": "Smith",
        },
    )

    assert response.status_code == 422


def test_create_staff_missing_last_name_returns_422(
    client,
    admin_headers,
):
    response = client.post(
        "/api/staff",
        headers=admin_headers,
        json={
            "first_name": "Jane",
        },
    )

    assert response.status_code == 422


def test_create_staff_invalid_user_id_returns_422(
    client,
    admin_headers,
):
    response = client.post(
        "/api/staff",
        headers=admin_headers,
        json={
            "user_id": 0,
            "first_name": "Jane",
            "last_name": "Smith",
        },
    )

    assert response.status_code == 422


def test_create_staff_invalid_json_returns_400(
    client,
    admin_headers,
):
    response = client.post(
        "/api/staff",
        headers=admin_headers,
        data="not-json",
        content_type="application/json",
    )

    assert response.status_code == 400


def test_list_staff_success(
    client,
    admin_headers,
    admin_staff,
    monkeypatch,
    staff_routes,
):
    staff = make_staff_object(
        clinic_id=admin_staff.clinic_id,
    )

    service = Mock(
        return_value=paginated(
            [staff],
            total=1,
            page=1,
            per_page=50,
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "list_staff",
        service,
    )

    response = client.get(
        "/api/staff",
        headers=admin_headers,
    )

    body = assert_success(response, 200)

    assert body["data"]["total"] == 1
    assert body["data"]["page"] == 1
    assert body["data"]["per_page"] == 50
    assert len(body["data"]["items"]) == 1
    assert body["data"]["items"][0]["id"] == 1

    assert (
        service.call_args.kwargs["clinic_id"]
        == admin_staff.clinic_id
    )


def test_list_staff_forwards_pagination(
    client,
    admin_headers,
    monkeypatch,
    staff_routes,
):
    service = Mock(
        return_value=paginated(
            [],
            total=100,
            page=3,
            per_page=10,
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "list_staff",
        service,
    )

    response = client.get(
        "/api/staff?page=3&per_page=10",
        headers=admin_headers,
    )

    body = assert_success(response, 200)

    assert body["data"]["page"] == 3
    assert body["data"]["per_page"] == 10
    assert body["data"]["total"] == 100

    kwargs = service.call_args.kwargs

    assert kwargs["page"] == 3
    assert kwargs["per_page"] == 10


def test_list_staff_forwards_status(
    client,
    admin_headers,
    admin_staff,
    monkeypatch,
    staff_routes,
):
    service = Mock(
        return_value=paginated(
            [],
            total=0,
            page=1,
            per_page=50,
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "list_staff",
        service,
    )

    response = client.get(
        "/api/staff",
        headers=admin_headers,
        query_string={
            "status": StaffStatus.SUSPENDED.value,
        },
    )

    assert response.status_code == 200

    assert (
        service.call_args.kwargs["status"]
        == StaffStatus.SUSPENDED
    )


def test_list_staff_forwards_search(
    client,
    admin_headers,
    monkeypatch,
    staff_routes,
):
    service = Mock(
        return_value=paginated(
            [],
            total=0,
            page=1,
            per_page=50,
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "list_staff",
        service,
    )

    response = client.get(
        "/api/staff?search=  cardiology  ",
        headers=admin_headers,
    )

    assert response.status_code == 200

    assert (
        service.call_args.kwargs["search"]
        == "  cardiology  "
    )


def test_list_staff_invalid_status_returns_422(
    client,
    admin_headers,
):
    response = client.get(
        "/api/staff?status=not-a-status",
        headers=admin_headers,
    )

    assert response.status_code == 422


def test_list_staff_search_too_long_returns_422(
    client,
    admin_headers,
):
    response = client.get(
        "/api/staff",
        headers=admin_headers,
        query_string={
            "search": "x" * 101,
        },
    )

    assert response.status_code == 422


def test_list_staff_invalid_page_returns_422(
    client,
    admin_headers,
):
    response = client.get(
        "/api/staff?page=0",
        headers=admin_headers,
    )

    assert response.status_code == 422


def test_list_staff_invalid_per_page_returns_422(
    client,
    admin_headers,
):
    response = client.get(
        "/api/staff?per_page=0",
        headers=admin_headers,
    )

    assert response.status_code == 422


def test_get_staff_success(
    client,
    doctor_headers,
    doctor_staff,
    monkeypatch,
    staff_routes,
):
    service = Mock(
        return_value=make_staff_object(
            id=doctor_staff.id,
            clinic_id=doctor_staff.clinic_id,
            user_id=doctor_staff.user_id,
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "get_staff",
        service,
    )

    response = client.get(
        f"/api/staff/{doctor_staff.id}",
        headers=doctor_headers,
    )

    body = assert_success(response, 200)

    assert body["data"]["id"] == doctor_staff.id

    assert (
        service.call_args.kwargs["clinic_id"]
        == doctor_staff.clinic_id
    )


def test_update_staff_success(
    client,
    admin_headers,
    admin_staff,
    monkeypatch,
    staff_routes,
):
    updated = make_staff_object(
        id=admin_staff.id,
        clinic_id=admin_staff.clinic_id,
        first_name="Updated",
        last_name="Staff",
    )

    service = Mock(return_value=updated)

    monkeypatch.setattr(
        staff_routes,
        "update_staff",
        service,
    )

    response = client.patch(
        f"/api/staff/{admin_staff.id}",
        headers=admin_headers,
        json={
            "first_name": "Updated",
            "last_name": "Staff",
        },
    )

    body = assert_success(response, 200)

    assert body["data"]["first_name"] == "Updated"

    kwargs = service.call_args.kwargs

    assert kwargs["staff_id"] == admin_staff.id
    assert kwargs["first_name"] == "Updated"
    assert kwargs["last_name"] == "Staff"


def test_update_staff_uses_exclude_unset(
    client,
    admin_headers,
    admin_staff,
    monkeypatch,
    staff_routes,
):
    service = Mock(
        return_value=make_staff_object(
            id=admin_staff.id,
            clinic_id=admin_staff.clinic_id,
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "update_staff",
        service,
    )

    response = client.patch(
        f"/api/staff/{admin_staff.id}",
        headers=admin_headers,
        json={
            "specialty": "Neurology",
        },
    )

    assert response.status_code == 200

    kwargs = service.call_args.kwargs

    assert kwargs["staff_id"] == admin_staff.id
    assert kwargs["specialty"] == "Neurology"

    assert "first_name" not in kwargs
    assert "last_name" not in kwargs


def test_update_staff_blank_first_name_returns_422(
    client,
    admin_headers,
):
    response = client.patch(
        "/api/staff/1",
        headers=admin_headers,
        json={
            "first_name": "",
        },
    )

    assert response.status_code == 422


def test_update_staff_blank_last_name_returns_422(
    client,
    admin_headers,
):
    response = client.patch(
        "/api/staff/1",
        headers=admin_headers,
        json={
            "last_name": "",
        },
    )

    assert response.status_code == 422


def test_change_staff_status_success(
    client,
    admin_headers,
    admin_staff,
    monkeypatch,
    staff_routes,
):
    updated = make_staff_object(
        id=admin_staff.id,
        clinic_id=admin_staff.clinic_id,
        status=StaffStatus.SUSPENDED,
    )

    service = Mock(return_value=updated)

    monkeypatch.setattr(
        staff_routes,
        "change_staff_status",
        service,
    )

    response = client.patch(
        f"/api/staff/{admin_staff.id}/status",
        headers=admin_headers,
        json={
            "status": StaffStatus.SUSPENDED.value,
        },
    )

    body = assert_success(response, 200)

    assert (
        body["data"]["status"]
        == StaffStatus.SUSPENDED.value
    )

    kwargs = service.call_args.kwargs

    assert kwargs["staff_id"] == admin_staff.id
    assert kwargs["new_status"] == StaffStatus.SUSPENDED


def test_change_staff_status_invalid_status_returns_422(
    client,
    admin_headers,
):
    response = client.patch(
        "/api/staff/1/status",
        headers=admin_headers,
        json={
            "status": "invalid",
        },
    )

    assert response.status_code == 422


def test_request_leave_success(
    client,
    doctor_headers,
    doctor_staff,
    monkeypatch,
    staff_routes,
):
    leave = make_leave_object(
        staff_id=doctor_staff.id,
        status=LeaveStatus.PENDING,
    )

    service = Mock(return_value=leave)

    monkeypatch.setattr(
        staff_routes,
        "request_leave",
        service,
    )

    response = client.post(
        "/api/staff/leave",
        headers=doctor_headers,
        json={
            "leave_type": LeaveType.ANNUAL.value,
            "start_date": "2026-09-10",
            "end_date": "2026-09-12",
            "reason": "Annual leave",
        },
    )

    body = assert_success(response, 201)

    assert (
        body["data"]["status"]
        == LeaveStatus.PENDING.value
    )

    kwargs = service.call_args.kwargs

    assert kwargs["clinic_id"] == doctor_staff.clinic_id
    assert kwargs["staff_id"] == doctor_staff.id
    assert kwargs["actor_user_id"] == doctor_staff.user_id
    assert kwargs["leave_type"] == LeaveType.ANNUAL
    assert kwargs["start_date"] == date(2026, 9, 10)
    assert kwargs["end_date"] == date(2026, 9, 12)
    assert kwargs["reason"] == "Annual leave"


def test_request_leave_invalid_date_range_returns_422(
    client,
    doctor_headers,
):
    response = client.post(
        "/api/staff/leave",
        headers=doctor_headers,
        json={
            "leave_type": LeaveType.ANNUAL.value,
            "start_date": "2026-09-20",
            "end_date": "2026-09-10",
        },
    )

    assert response.status_code == 422


def test_request_leave_missing_leave_type_returns_422(
    client,
    doctor_headers,
):
    response = client.post(
        "/api/staff/leave",
        headers=doctor_headers,
        json={
            "start_date": "2026-09-10",
            "end_date": "2026-09-12",
        },
    )

    assert response.status_code == 422


def test_list_leave_requests_admin_can_filter_by_staff(
    client,
    admin_headers,
    admin_staff,
    monkeypatch,
    staff_routes,
):
    service = Mock(
        return_value=paginated(
            [],
            total=0,
            page=1,
            per_page=50,
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "list_leave_requests",
        service,
    )

    response = client.get(
        "/api/staff/leave",
        headers=admin_headers,
        query_string={
            "staff_id": admin_staff.id,
            "status": LeaveStatus.PENDING.value,
        },
    )

    assert response.status_code == 200

    kwargs = service.call_args.kwargs

    assert kwargs["clinic_id"] == admin_staff.clinic_id
    assert kwargs["staff_id"] == admin_staff.id
    assert kwargs["status"] == LeaveStatus.PENDING


def test_list_leave_requests_forwards_pagination(
    client,
    admin_headers,
    monkeypatch,
    staff_routes,
):
    service = Mock(
        return_value=paginated(
            [],
            total=37,
            page=2,
            per_page=10,
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "list_leave_requests",
        service,
    )

    response = client.get(
        "/api/staff/leave?page=2&per_page=10",
        headers=admin_headers,
    )

    body = assert_success(response, 200)

    assert body["data"]["total"] == 37
    assert body["data"]["page"] == 2
    assert body["data"]["per_page"] == 10

    kwargs = service.call_args.kwargs

    assert kwargs["page"] == 2
    assert kwargs["per_page"] == 10


def test_list_leave_requests_non_admin_is_forced_to_own_staff(
    client,
    doctor_headers,
    doctor_staff,
    monkeypatch,
    staff_routes,
):
    service = Mock(
        return_value=paginated(
            [],
            total=0,
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "list_leave_requests",
        service,
    )

    response = client.get(
        "/api/staff/leave",
        headers=doctor_headers,
        query_string={
            "staff_id": 999999,
        },
    )

    assert response.status_code == 200

    assert (
        service.call_args.kwargs["staff_id"]
        == doctor_staff.id
    )


def test_get_own_leave_request_success(
    client,
    doctor_headers,
    doctor_staff,
    monkeypatch,
    staff_routes,
):
    leave = make_leave_object(
        id=5,
        staff_id=doctor_staff.id,
    )

    service = Mock(return_value=leave)

    monkeypatch.setattr(
        staff_routes,
        "get_leave_request",
        service,
    )

    response = client.get(
        "/api/staff/leave/5",
        headers=doctor_headers,
    )

    body = assert_success(response, 200)

    assert body["data"]["id"] == 5

    assert (
        service.call_args.kwargs["clinic_id"]
        == doctor_staff.clinic_id
    )


def test_get_foreign_leave_request_is_hidden_from_non_admin(
    client,
    doctor_headers,
    monkeypatch,
    staff_routes,
):
    foreign_leave = make_leave_object(
        id=5,
        staff_id=999999,
    )

    monkeypatch.setattr(
        staff_routes,
        "get_leave_request",
        Mock(return_value=foreign_leave),
    )

    response = client.get(
        "/api/staff/leave/5",
        headers=doctor_headers,
    )

    assert response.status_code == 404


def test_approve_leave_success(
    client,
    admin_headers,
    admin_staff,
    monkeypatch,
    staff_routes,
):
    leave = make_leave_object(
        status=LeaveStatus.APPROVED,
        reviewed_by_user_id=admin_staff.user_id,
        reviewed_at=datetime.now(timezone.utc),
    )

    service = Mock(return_value=leave)

    monkeypatch.setattr(
        staff_routes,
        "approve_leave_request",
        service,
    )

    response = client.post(
        "/api/staff/leave/1/approve",
        headers=admin_headers,
        json={},
    )

    body = assert_success(response, 200)

    assert (
        body["data"]["status"]
        == LeaveStatus.APPROVED.value
    )

    kwargs = service.call_args.kwargs

    assert kwargs["leave_id"] == 1
    assert kwargs["clinic_id"] == admin_staff.clinic_id
    assert kwargs["reviewer_user_id"] == admin_staff.user_id


def test_reject_leave_success(
    client,
    admin_headers,
    admin_staff,
    monkeypatch,
    staff_routes,
):
    leave = make_leave_object(
        status=LeaveStatus.REJECTED,
        reviewed_by_user_id=admin_staff.user_id,
        reviewed_at=datetime.now(timezone.utc),
    )

    service = Mock(return_value=leave)

    monkeypatch.setattr(
        staff_routes,
        "reject_leave_request",
        service,
    )

    response = client.post(
        "/api/staff/leave/1/reject",
        headers=admin_headers,
        json={
            "reason": "Staffing shortage",
        },
    )

    body = assert_success(response, 200)

    assert (
        body["data"]["status"]
        == LeaveStatus.REJECTED.value
    )

    kwargs = service.call_args.kwargs

    assert kwargs["leave_id"] == 1
    assert kwargs["clinic_id"] == admin_staff.clinic_id
    assert kwargs["reviewer_user_id"] == admin_staff.user_id
    assert kwargs["reason"] == "Staffing shortage"


def test_reject_leave_blank_reason_is_accepted_by_schema(
    client,
    admin_headers,
    monkeypatch,
    staff_routes,
):
    service = Mock(
        return_value=make_leave_object(
            status=LeaveStatus.REJECTED,
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "reject_leave_request",
        service,
    )

    response = client.post(
        "/api/staff/leave/1/reject",
        headers=admin_headers,
        json={
            "reason": None,
        },
    )

    assert response.status_code == 200


def test_create_excuse_success(
    client,
    doctor_headers,
    doctor_staff,
    monkeypatch,
    staff_routes,
):
    excuse = make_excuse_object(
        staff_id=doctor_staff.id,
    )

    service = Mock(return_value=excuse)

    monkeypatch.setattr(
        staff_routes,
        "create_excuse",
        service,
    )

    response = client.post(
        "/api/staff/excuses",
        headers=doctor_headers,
        json={
            "excuse_type": ExcuseType.MEDICAL.value,
            "description": "Medical appointment",
        },
    )

    body = assert_success(response, 201)

    assert body["data"]["staff_id"] == doctor_staff.id

    kwargs = service.call_args.kwargs

    assert kwargs["clinic_id"] == doctor_staff.clinic_id
    assert kwargs["staff_id"] == doctor_staff.id
    assert kwargs["excuse_type"] == ExcuseType.MEDICAL
    assert kwargs["description"] == "Medical appointment"
    assert "actor_user_id" not in kwargs


def test_create_excuse_missing_description_returns_422(
    client,
    doctor_headers,
):
    response = client.post(
        "/api/staff/excuses",
        headers=doctor_headers,
        json={
            "excuse_type": ExcuseType.MEDICAL.value,
        },
    )

    assert response.status_code == 422


def test_create_excuse_blank_description_returns_422(
    client,
    doctor_headers,
):
    response = client.post(
        "/api/staff/excuses",
        headers=doctor_headers,
        json={
            "excuse_type": ExcuseType.MEDICAL.value,
            "description": "",
        },
    )

    assert response.status_code == 422


def test_create_excuse_description_too_long_returns_422(
    client,
    doctor_headers,
):
    response = client.post(
        "/api/staff/excuses",
        headers=doctor_headers,
        json={
            "excuse_type": ExcuseType.MEDICAL.value,
            "description": "x" * 2001,
        },
    )

    assert response.status_code == 422


def test_create_excuse_invalid_type_returns_422(
    client,
    doctor_headers,
):
    response = client.post(
        "/api/staff/excuses",
        headers=doctor_headers,
        json={
            "excuse_type": "not-real",
            "description": "Valid description",
        },
    )

    assert response.status_code == 422


def test_list_excuses_admin_forwards_filters(
    client,
    admin_headers,
    admin_staff,
    monkeypatch,
    staff_routes,
):
    service = Mock(
        return_value=paginated(
            [],
            total=0,
            page=1,
            per_page=50,
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "list_excuses",
        service,
    )

    response = client.get(
        "/api/staff/excuses",
        headers=admin_headers,
        query_string={
            "staff_id": admin_staff.id,
            "leave_request_id": 3,
            "excuse_type": ExcuseType.MEDICAL.value,
            "status": ExcuseStatus.PENDING.value,
        },
    )

    assert response.status_code == 200

    kwargs = service.call_args.kwargs

    assert kwargs["clinic_id"] == admin_staff.clinic_id
    assert kwargs["staff_id"] == admin_staff.id
    assert kwargs["leave_request_id"] == 3
    assert kwargs["excuse_type"] == ExcuseType.MEDICAL
    assert kwargs["status"] == ExcuseStatus.PENDING


def test_list_excuses_forwards_pagination(
    client,
    admin_headers,
    monkeypatch,
    staff_routes,
):
    service = Mock(
        return_value=paginated(
            [],
            total=25,
            page=2,
            per_page=10,
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "list_excuses",
        service,
    )

    response = client.get(
        "/api/staff/excuses?page=2&per_page=10",
        headers=admin_headers,
    )

    body = assert_success(response, 200)

    assert body["data"]["total"] == 25
    assert body["data"]["page"] == 2
    assert body["data"]["per_page"] == 10

    kwargs = service.call_args.kwargs

    assert kwargs["page"] == 2
    assert kwargs["per_page"] == 10


def test_list_excuses_non_admin_is_forced_to_own_staff(
    client,
    doctor_headers,
    doctor_staff,
    monkeypatch,
    staff_routes,
):
    service = Mock(
        return_value=paginated(
            [],
            total=0,
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "list_excuses",
        service,
    )

    response = client.get(
        "/api/staff/excuses",
        headers=doctor_headers,
        query_string={
            "staff_id": 999999,
        },
    )

    assert response.status_code == 200

    assert (
        service.call_args.kwargs["staff_id"]
        == doctor_staff.id
    )


def test_list_my_excuses_success(
    client,
    doctor_headers,
    doctor_staff,
    monkeypatch,
    staff_routes,
):
    service = Mock(
        return_value=paginated(
            [
                make_excuse_object(
                    staff_id=doctor_staff.id,
                )
            ],
            total=1,
            page=1,
            per_page=50,
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "get_my_excuses",
        service,
    )

    response = client.get(
        "/api/staff/excuses/me",
        headers=doctor_headers,
    )

    body = assert_success(response, 200)

    assert body["data"]["total"] == 1
    assert body["data"]["page"] == 1
    assert body["data"]["per_page"] == 50
    assert (
        body["data"]["items"][0]["staff_id"]
        == doctor_staff.id
    )

    kwargs = service.call_args.kwargs

    assert kwargs["clinic_id"] == doctor_staff.clinic_id
    assert kwargs["staff_id"] == doctor_staff.id
    assert kwargs["page"] == 1
    assert kwargs["per_page"] == 50


def test_list_my_excuses_forwards_pagination(
    client,
    doctor_headers,
    doctor_staff,
    monkeypatch,
    staff_routes,
):
    service = Mock(
        return_value=paginated(
            [],
            total=17,
            page=2,
            per_page=5,
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "get_my_excuses",
        service,
    )

    response = client.get(
        "/api/staff/excuses/me?page=2&per_page=5",
        headers=doctor_headers,
    )

    body = assert_success(response, 200)

    assert body["data"]["page"] == 2
    assert body["data"]["per_page"] == 5
    assert body["data"]["total"] == 17

    kwargs = service.call_args.kwargs

    assert kwargs["page"] == 2
    assert kwargs["per_page"] == 5


def test_get_own_excuse_success(
    client,
    doctor_headers,
    doctor_staff,
    monkeypatch,
    staff_routes,
):
    excuse = make_excuse_object(
        id=7,
        staff_id=doctor_staff.id,
    )

    monkeypatch.setattr(
        staff_routes,
        "get_excuse",
        Mock(return_value=excuse),
    )

    response = client.get(
        "/api/staff/excuses/7",
        headers=doctor_headers,
    )

    body = assert_success(response, 200)

    assert body["data"]["id"] == 7


def test_get_foreign_excuse_is_hidden_from_non_admin(
    client,
    doctor_headers,
    monkeypatch,
    staff_routes,
):
    excuse = make_excuse_object(
        id=7,
        staff_id=999999,
    )

    monkeypatch.setattr(
        staff_routes,
        "get_excuse",
        Mock(return_value=excuse),
    )

    response = client.get(
        "/api/staff/excuses/7",
        headers=doctor_headers,
    )

    assert response.status_code == 404


def test_approve_excuse_success(
    client,
    admin_headers,
    admin_staff,
    monkeypatch,
    staff_routes,
):
    excuse = make_excuse_object(
        status=ExcuseStatus.APPROVED,
        reviewed_by_user_id=admin_staff.user_id,
        reviewed_at=datetime.now(timezone.utc),
    )

    service = Mock(return_value=excuse)

    monkeypatch.setattr(
        staff_routes,
        "approve_excuse",
        service,
    )

    response = client.post(
        "/api/staff/excuses/1/approve",
        headers=admin_headers,
        json={},
    )

    body = assert_success(response, 200)

    assert (
        body["data"]["status"]
        == ExcuseStatus.APPROVED.value
    )

    kwargs = service.call_args.kwargs

    assert kwargs["excuse_id"] == 1
    assert kwargs["clinic_id"] == admin_staff.clinic_id
    assert kwargs["reviewer_user_id"] == admin_staff.user_id


def test_reject_excuse_success(
    client,
    admin_headers,
    admin_staff,
    monkeypatch,
    staff_routes,
):
    excuse = make_excuse_object(
        status=ExcuseStatus.REJECTED,
        reviewed_by_user_id=admin_staff.user_id,
        reviewed_at=datetime.now(timezone.utc),
        rejection_reason="Insufficient documentation",
    )

    service = Mock(return_value=excuse)

    monkeypatch.setattr(
        staff_routes,
        "reject_excuse",
        service,
    )

    response = client.post(
        "/api/staff/excuses/1/reject",
        headers=admin_headers,
        json={
            "reason": "Insufficient documentation",
        },
    )

    body = assert_success(response, 200)

    assert (
        body["data"]["status"]
        == ExcuseStatus.REJECTED.value
    )

    kwargs = service.call_args.kwargs

    assert kwargs["excuse_id"] == 1
    assert kwargs["clinic_id"] == admin_staff.clinic_id
    assert kwargs["reviewer_user_id"] == admin_staff.user_id
    assert kwargs["reason"] == "Insufficient documentation"


def test_create_payroll_success(
    client,
    admin_headers,
    admin_staff,
    monkeypatch,
    staff_routes,
):
    payroll = make_payroll_object(
        staff_id=admin_staff.id,
    )

    service = Mock(return_value=payroll)

    monkeypatch.setattr(
        staff_routes,
        "create_payroll_record",
        service,
    )

    response = client.post(
        "/api/staff/payroll",
        headers=admin_headers,
        json={
            "staff_id": admin_staff.id,
            "pay_period_start": "2026-09-01",
            "pay_period_end": "2026-09-30",
            "base_salary": "100000",
            "bonuses": "5000",
            "deductions": "1000",
        },
    )

    body = assert_success(response, 201)

    assert body["data"]["staff_id"] == admin_staff.id

    kwargs = service.call_args.kwargs

    assert kwargs["clinic_id"] == admin_staff.clinic_id
    assert kwargs["staff_id"] == admin_staff.id
    assert kwargs["base_salary"] == Decimal("100000")
    assert kwargs["bonuses"] == Decimal("5000")
    assert kwargs["deductions"] == Decimal("1000")


def test_create_payroll_rejects_invalid_period(
    client,
    admin_headers,
    admin_staff,
):
    response = client.post(
        "/api/staff/payroll",
        headers=admin_headers,
        json={
            "staff_id": admin_staff.id,
            "pay_period_start": "2026-09-30",
            "pay_period_end": "2026-09-01",
            "base_salary": "100000",
        },
    )

    assert response.status_code == 422


def test_create_payroll_rejects_negative_salary(
    client,
    admin_headers,
    admin_staff,
):
    response = client.post(
        "/api/staff/payroll",
        headers=admin_headers,
        json={
            "staff_id": admin_staff.id,
            "pay_period_start": "2026-09-01",
            "pay_period_end": "2026-09-30",
            "base_salary": "-1",
        },
    )

    assert response.status_code == 422


def test_create_payroll_rejects_excessive_deductions(
    client,
    admin_headers,
    admin_staff,
):
    response = client.post(
        "/api/staff/payroll",
        headers=admin_headers,
        json={
            "staff_id": admin_staff.id,
            "pay_period_start": "2026-09-01",
            "pay_period_end": "2026-09-30",
            "base_salary": "100000",
            "deductions": "100001",
        },
    )

    assert response.status_code == 422


def test_generate_payroll_success(
    client,
    accountant_headers,
    accountant_staff,
    monkeypatch,
    staff_routes,
):
    payroll = [
        make_payroll_object(
            staff_id=accountant_staff.id,
        )
    ]

    service = Mock(return_value=payroll)

    monkeypatch.setattr(
        staff_routes,
        "generate_payroll_for_period",
        service,
    )

    response = client.post(
        "/api/staff/payroll/generate",
        headers=accountant_headers,
        json={
            "pay_period_start": "2026-09-01",
            "pay_period_end": "2026-09-30",
            "salary_lookup": {
                str(accountant_staff.id): "100000",
            },
        },
    )

    body = assert_success(response, 201)

    assert len(body["data"]) == 1

    kwargs = service.call_args.kwargs

    assert kwargs["clinic_id"] == accountant_staff.clinic_id
    assert (
        kwargs["salary_lookup"][accountant_staff.id]
        == Decimal("100000")
    )


def test_generate_payroll_rejects_invalid_period(
    client,
    accountant_headers,
):
    response = client.post(
        "/api/staff/payroll/generate",
        headers=accountant_headers,
        json={
            "pay_period_start": "2026-09-30",
            "pay_period_end": "2026-09-01",
            "salary_lookup": {},
        },
    )

    assert response.status_code == 422


def test_generate_payroll_rejects_negative_salary(
    client,
    accountant_headers,
):
    response = client.post(
        "/api/staff/payroll/generate",
        headers=accountant_headers,
        json={
            "pay_period_start": "2026-09-01",
            "pay_period_end": "2026-09-30",
            "salary_lookup": {
                "1": "-100",
            },
        },
    )

    assert response.status_code == 422


def test_list_payroll_success(
    client,
    accountant_headers,
    accountant_staff,
    monkeypatch,
    staff_routes,
):
    payroll = make_payroll_object(
        staff_id=accountant_staff.id,
    )

    service = Mock(
        return_value=paginated(
            [payroll],
            total=1,
            page=1,
            per_page=50,
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "list_payroll",
        service,
    )

    response = client.get(
        "/api/staff/payroll",
        headers=accountant_headers,
    )

    body = assert_success(response, 200)

    assert body["data"]["total"] == 1
    assert body["data"]["page"] == 1
    assert body["data"]["per_page"] == 50
    assert len(body["data"]["items"]) == 1
    assert (
        body["data"]["items"][0]["staff_id"]
        == accountant_staff.id
    )

    assert (
        service.call_args.kwargs["clinic_id"]
        == accountant_staff.clinic_id
    )


def test_list_payroll_forwards_pagination(
    client,
    accountant_headers,
    monkeypatch,
    staff_routes,
):
    service = Mock(
        return_value=paginated(
            [],
            total=22,
            page=2,
            per_page=10,
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "list_payroll",
        service,
    )

    response = client.get(
        "/api/staff/payroll?page=2&per_page=10",
        headers=accountant_headers,
    )

    body = assert_success(response, 200)

    assert body["data"]["total"] == 22
    assert body["data"]["page"] == 2
    assert body["data"]["per_page"] == 10

    kwargs = service.call_args.kwargs

    assert kwargs["page"] == 2
    assert kwargs["per_page"] == 10


def test_list_payroll_for_staff_success(
    client,
    accountant_headers,
    accountant_staff,
    monkeypatch,
    staff_routes,
):
    payroll = make_payroll_object(
        staff_id=accountant_staff.id,
    )

    service = Mock(
        return_value=paginated(
            [payroll],
            total=1,
            page=1,
            per_page=50,
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "list_payroll_for_staff",
        service,
    )

    response = client.get(
        "/api/staff/payroll",
        headers=accountant_headers,
        query_string={
            "staff_id": accountant_staff.id,
        },
    )

    body = assert_success(response, 200)

    assert body["data"]["total"] == 1
    assert body["data"]["page"] == 1
    assert body["data"]["per_page"] == 50
    assert len(body["data"]["items"]) == 1

    kwargs = service.call_args.kwargs

    assert kwargs["clinic_id"] == accountant_staff.clinic_id
    assert kwargs["staff_id"] == accountant_staff.id


def test_list_payroll_for_staff_forwards_pagination(
    client,
    accountant_headers,
    accountant_staff,
    monkeypatch,
    staff_routes,
):
    service = Mock(
        return_value=paginated(
            [],
            total=19,
            page=3,
            per_page=5,
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "list_payroll_for_staff",
        service,
    )

    response = client.get(
        "/api/staff/payroll",
        headers=accountant_headers,
        query_string={
            "staff_id": accountant_staff.id,
            "page": 3,
            "per_page": 5,
        },
    )

    body = assert_success(response, 200)

    assert body["data"]["total"] == 19
    assert body["data"]["page"] == 3
    assert body["data"]["per_page"] == 5

    kwargs = service.call_args.kwargs

    assert kwargs["clinic_id"] == accountant_staff.clinic_id
    assert kwargs["staff_id"] == accountant_staff.id
    assert kwargs["page"] == 3
    assert kwargs["per_page"] == 5


def test_list_payroll_invalid_staff_id_returns_422(
    client,
    accountant_headers,
):
    response = client.get(
        "/api/staff/payroll?staff_id=0",
        headers=accountant_headers,
    )

    assert response.status_code == 422


def test_list_payroll_invalid_page_returns_422(
    client,
    accountant_headers,
):
    response = client.get(
        "/api/staff/payroll?page=0",
        headers=accountant_headers,
    )

    assert response.status_code == 422


def test_list_payroll_invalid_per_page_returns_422(
    client,
    accountant_headers,
):
    response = client.get(
        "/api/staff/payroll?per_page=0",
        headers=accountant_headers,
    )

    assert response.status_code == 422


def test_get_payroll_success(
    client,
    accountant_headers,
    accountant_staff,
    monkeypatch,
    staff_routes,
):
    payroll = make_payroll_object(
        id=9,
        staff_id=accountant_staff.id,
    )

    service = Mock(return_value=payroll)

    monkeypatch.setattr(
        staff_routes,
        "get_payroll_record",
        service,
    )

    response = client.get(
        "/api/staff/payroll/9",
        headers=accountant_headers,
    )

    body = assert_success(response, 200)

    assert body["data"]["id"] == 9

    assert (
        service.call_args.kwargs["clinic_id"]
        == accountant_staff.clinic_id
    )


def test_mark_payroll_paid_success(
    client,
    accountant_headers,
    accountant_staff,
    monkeypatch,
    staff_routes,
):
    payroll = make_payroll_object(
        id=9,
        staff_id=accountant_staff.id,
        paid_at=datetime.now(timezone.utc),
    )

    service = Mock(return_value=payroll)

    monkeypatch.setattr(
        staff_routes,
        "mark_payroll_paid",
        service,
    )

    response = client.post(
        "/api/staff/payroll/9/pay",
        headers=accountant_headers,
    )

    body = assert_success(response, 200)

    assert body["data"]["paid_at"] is not None

    kwargs = service.call_args.kwargs

    assert kwargs["record_id"] == 9
    assert kwargs["clinic_id"] == accountant_staff.clinic_id


@pytest.mark.parametrize(
    (
        "service_name",
        "method",
        "url",
        "json",
    ),
    [
        (
            "create_staff",
            "post",
            "/api/staff",
            {
                "first_name": "Jane",
                "last_name": "Smith",
            },
        ),
        (
            "update_staff",
            "patch",
            "/api/staff/1",
            {
                "first_name": "Updated",
            },
        ),
        (
            "change_staff_status",
            "patch",
            "/api/staff/1/status",
            {
                "status": StaffStatus.SUSPENDED.value,
            },
        ),
    ],
)
def test_staff_domain_errors_are_returned(
    client,
    admin_headers,
    monkeypatch,
    staff_routes,
    service_name,
    method,
    url,
    json,
):
    from app.core.exceptions import ConflictError

    service = Mock(
        side_effect=ConflictError(
            "Staff operation conflict"
        )
    )

    monkeypatch.setattr(
        staff_routes,
        service_name,
        service,
    )

    response = getattr(client, method)(
        url,
        headers=admin_headers,
        json=json,
    )

    assert_error(response, 409)


def test_leave_domain_error_is_returned(
    client,
    doctor_headers,
    monkeypatch,
    staff_routes,
):
    from app.core.exceptions import ConflictError

    service = Mock(
        side_effect=ConflictError(
            "Leave conflict"
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "request_leave",
        service,
    )

    response = client.post(
        "/api/staff/leave",
        headers=doctor_headers,
        json={
            "leave_type": LeaveType.ANNUAL.value,
            "start_date": "2026-09-10",
            "end_date": "2026-09-12",
        },
    )

    assert_error(response, 409)


def test_payroll_domain_error_is_returned(
    client,
    accountant_headers,
    monkeypatch,
    staff_routes,
):
    from app.core.exceptions import ConflictError

    service = Mock(
        side_effect=ConflictError(
            "Payroll conflict"
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "create_payroll_record",
        service,
    )

    response = client.post(
        "/api/staff/payroll",
        headers=accountant_headers,
        json={
            "staff_id": 1,
            "pay_period_start": "2026-09-01",
            "pay_period_end": "2026-09-30",
            "base_salary": "100000",
        },
    )

    assert_error(response, 409)


def test_excuse_domain_error_is_returned(
    client,
    doctor_headers,
    monkeypatch,
    staff_routes,
):
    from app.core.exceptions import ConflictError

    service = Mock(
        side_effect=ConflictError(
            "Excuse conflict"
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "create_excuse",
        service,
    )

    response = client.post(
        "/api/staff/excuses",
        headers=doctor_headers,
        json={
            "excuse_type": ExcuseType.MEDICAL.value,
            "description": "Medical appointment",
        },
    )

    assert_error(response, 409)


def test_staff_serializer_serializes_enum_and_dates(
    staff_routes,
):
    staff = make_staff_object()

    result = staff_routes._serialize_staff(staff)

    assert result["id"] == staff.id
    assert result["clinic_id"] == staff.clinic_id
    assert result["status"] == StaffStatus.ACTIVE.value
    assert result["hired_at"] == "2026-01-01"
    assert result["created_at"] is not None
    assert result["updated_at"] is not None


def test_leave_serializer_serializes_enum_and_dates(
    staff_routes,
):
    leave = make_leave_object()

    result = staff_routes._serialize_leave(leave)

    assert result["id"] == leave.id
    assert result["staff_id"] == leave.staff_id
    assert result["leave_type"] == LeaveType.ANNUAL.value
    assert result["status"] == LeaveStatus.PENDING.value
    assert result["start_date"] == "2026-09-10"
    assert result["end_date"] == "2026-09-12"


def test_payroll_serializer_serializes_decimal_as_string(
    staff_routes,
):
    payroll = make_payroll_object()

    result = staff_routes._serialize_payroll(payroll)

    assert result["id"] == payroll.id
    assert result["staff_id"] == payroll.staff_id
    assert result["base_salary"] == "100000.00"
    assert result["bonuses"] == "5000.00"
    assert result["deductions"] == "1000.00"
    assert result["net_pay"] == "104000.00"


def test_excuse_serializer_serializes_enum_and_dates(
    staff_routes,
):
    excuse = make_excuse_object()

    result = staff_routes._serialize_excuse(excuse)

    assert result["id"] == excuse.id
    assert result["staff_id"] == excuse.staff_id
    assert result["description"] == excuse.description
    assert result["rejection_reason"] is None
    assert result["created_at"] is not None
    assert result["updated_at"] is not None


@pytest.mark.parametrize(
    "role",
    [
        Role.DOCTOR,
        Role.NURSE,
        Role.PHARMACIST,
        Role.LAB_TECHNICIAN,
        Role.RECEPTIONIST,
        Role.PARAMEDIC,
        Role.EMT,
        Role.DRIVER,
        Role.AMBULANCE_DISPATCHER,
        Role.AMBULANCE_COORDINATOR,
        Role.ACCOUNTANT,
        Role.OTHER,
    ],
)
def test_staff_list_allows_view_roles(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
    staff_routes,
    role,
):
    _, headers = make_authenticated_staff(
        clinic,
        role,
    )

    monkeypatch.setattr(
        staff_routes,
        "list_staff",
        Mock(
            return_value=paginated(
                [],
                total=0,
            )
        ),
    )

    response = client.get(
        "/api/staff",
        headers=headers,
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    "role",
    [
        Role.ADMIN,
        Role.ACCOUNTANT,
    ],
)
def test_payroll_list_allows_payroll_roles(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
    staff_routes,
    role,
):
    _, headers = make_authenticated_staff(
        clinic,
        role,
    )

    monkeypatch.setattr(
        staff_routes,
        "list_payroll",
        Mock(
            return_value=paginated(
                [],
                total=0,
            )
        ),
    )

    response = client.get(
        "/api/staff/payroll",
        headers=headers,
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    "role",
    [
        Role.ADMIN,
        Role.ACCOUNTANT,
    ],
)
def test_payroll_create_allows_payroll_roles(
    client,
    make_authenticated_staff,
    clinic,
    monkeypatch,
    staff_routes,
    role,
):
    staff_obj, headers = make_authenticated_staff(
        clinic,
        role,
    )

    monkeypatch.setattr(
        staff_routes,
        "create_payroll_record",
        Mock(
            return_value=make_payroll_object(
                staff_id=staff_obj.id,
            )
        ),
    )

    response = client.post(
        "/api/staff/payroll",
        headers=headers,
        json={
            "staff_id": staff_obj.id,
            "pay_period_start": "2026-09-01",
            "pay_period_end": "2026-09-30",
            "base_salary": "100000",
        },
    )

    assert response.status_code == 201


def test_get_staff_uses_authenticated_clinic(
    client,
    admin_headers,
    admin_staff,
    monkeypatch,
    staff_routes,
):
    service = Mock(
        return_value=make_staff_object(
            id=admin_staff.id,
            clinic_id=admin_staff.clinic_id,
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "get_staff",
        service,
    )

    response = client.get(
        f"/api/staff/{admin_staff.id}",
        headers=admin_headers,
    )

    assert response.status_code == 200

    assert (
        service.call_args.kwargs["clinic_id"]
        == admin_staff.clinic_id
    )


def test_create_staff_rejects_client_clinic_id(
    client,
    admin_headers,
):
    response = client.post(
        "/api/staff",
        headers=admin_headers,
        json={
            "first_name": "Jane",
            "last_name": "Smith",
            "clinic_id": 999999,
        },
    )

    assert response.status_code == 422


def test_create_staff_cannot_override_authenticated_clinic(
    client,
    admin_headers,
    admin_staff,
    monkeypatch,
    staff_routes,
):
    service = Mock(
        return_value=make_staff_object(
            clinic_id=admin_staff.clinic_id,
        )
    )

    monkeypatch.setattr(
        staff_routes,
        "create_staff",
        service,
    )

    response = client.post(
        "/api/staff",
        headers=admin_headers,
        json={
            "first_name": "Jane",
            "last_name": "Smith",
        },
    )

    assert response.status_code == 201

    kwargs = service.call_args.kwargs

    assert kwargs["clinic_id"] == admin_staff.clinic_id


def test_inactive_authenticated_user_is_rejected(
    client,
    make_authenticated_staff,
    clinic,
):
    _, headers = make_authenticated_staff(
        clinic,
        Role.DOCTOR,
        user_is_active=False,
    )

    response = client.get(
        "/api/staff",
        headers=headers,
    )

    assert response.status_code in (400, 401, 422)


def test_get_staff_invalid_negative_id_returns_404(
    client,
    admin_headers,
):
    response = client.get(
        "/api/staff/-1",
        headers=admin_headers,
    )

    assert response.status_code in (404, 405)


def test_get_leave_request_invalid_negative_id_returns_404(
    client,
    doctor_headers,
):
    response = client.get(
        "/api/staff/leave/-1",
        headers=doctor_headers,
    )

    assert response.status_code in (404, 405)


def test_get_payroll_invalid_negative_id_returns_404(
    client,
    accountant_headers,
):
    response = client.get(
        "/api/staff/payroll/-1",
        headers=accountant_headers,
    )

    assert response.status_code in (404, 405)


def test_get_excuse_invalid_negative_id_returns_404(
    client,
    doctor_headers,
):
    response = client.get(
        "/api/staff/excuses/-1",
        headers=doctor_headers,
    )

    assert response.status_code in (404, 405)