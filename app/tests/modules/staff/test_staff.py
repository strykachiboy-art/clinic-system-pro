from datetime import date, timedelta
from decimal import Decimal

from app.core.enums.role_enums import Role


def _headers(make_authenticated_staff, clinic, role):
    _, h = make_authenticated_staff(clinic, role)
    return h


class TestStaffRoutes:
    def test_create_staff_requires_admin(self, client, clinic, make_authenticated_staff, assert_forbidden):
        nurse_headers = _headers(make_authenticated_staff, clinic, Role.NURSE)
        resp = client.post(
            "/api/staff",
            json={"clinic_id": clinic.id, "first_name": "A", "last_name": "B"},
            headers=nurse_headers,
        )
        assert_forbidden(resp)

    def test_create_staff_happy_path(self, client, clinic, make_authenticated_staff):
        headers = _headers(make_authenticated_staff, clinic, Role.ADMIN)
        resp = client.post(
            "/api/staff",
            json={"clinic_id": clinic.id, "first_name": "Ada", "last_name": "Lovelace"},
            headers=headers,
        )
        assert resp.status_code == 201
        body = resp.get_json()
        # This route's success shape is {"message": ..., "data": ...} —
        # no "success" key, unlike pharmacy's routes.
        assert "message" in body
        assert body["data"]["first_name"] == "Ada"

    def test_list_staff_viewable_by_receptionist(self, client, clinic, make_staff, make_authenticated_staff):
        make_staff(clinic, first_name="X")
        headers = _headers(make_authenticated_staff, clinic, Role.RECEPTIONIST)

        resp = client.get(f"/api/staff?clinic_id={clinic.id}", headers=headers)
        assert resp.status_code == 200
        assert len(resp.get_json()["data"]) >= 1

    def test_get_staff_not_found(self, client, clinic, make_authenticated_staff, assert_domain_error):
        headers = _headers(make_authenticated_staff, clinic, Role.ADMIN)
        resp = client.get("/api/staff/999999", headers=headers)
        assert_domain_error(resp, 404)

    def test_update_staff_requires_admin(self, client, clinic, staff, make_authenticated_staff, assert_forbidden):
        headers = _headers(make_authenticated_staff, clinic, Role.DOCTOR)
        resp = client.patch(f"/api/staff/{staff.id}", json={"first_name": "New"}, headers=headers)
        assert_forbidden(resp)

    def test_change_staff_status(self, client, clinic, staff, make_authenticated_staff):
        headers = _headers(make_authenticated_staff, clinic, Role.ADMIN)
        resp = client.patch(
            f"/api/staff/{staff.id}/status", json={"status": "suspended"}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["status"] == "suspended"


class TestLeaveRoutes:
    def test_request_leave_happy_path(self, client, clinic, staff, make_authenticated_staff):
        headers = _headers(make_authenticated_staff, clinic, Role.DOCTOR)
        resp = client.post(
            "/api/staff/leaves",
            json={
                "staff_id": staff.id,
                "leave_type": "annual",
                "start_date": str(date.today() + timedelta(days=5)),
                "end_date": str(date.today() + timedelta(days=10)),
            },
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.get_json()["data"]["status"] == "pending"

    def test_request_leave_rejects_end_before_start_at_schema_layer(
        self, client, clinic, staff, make_authenticated_staff,
    ):
        headers = _headers(make_authenticated_staff, clinic, Role.DOCTOR)
        resp = client.post(
            "/api/staff/leaves",
            json={
                "staff_id": staff.id,
                "leave_type": "annual",
                "start_date": str(date.today() + timedelta(days=10)),
                "end_date": str(date.today() + timedelta(days=5)),
            },
            headers=headers,
        )
        # LeaveRequestCreateSchema has a model_validator for this ->
        # rejected before the service is ever called.
        assert resp.status_code == 422

    def test_approve_leave_requires_admin(self, client, clinic, staff, make_staff, make_authenticated_staff, assert_forbidden):
        reviewer = make_staff(clinic)
        doctor_headers = _headers(make_authenticated_staff, clinic, Role.DOCTOR)

        create_resp = client.post(
            "/api/staff/leaves",
            json={
                "staff_id": staff.id,
                "leave_type": "sick",
                "start_date": str(date.today()),
                "end_date": str(date.today() + timedelta(days=1)),
            },
            headers=doctor_headers,
        )
        leave_id = create_resp.get_json()["data"]["id"]

        # Doctors can request/view leave (STAFF_VIEW_ROLES) but approving
        # is admin-only (LEAVE_MANAGEMENT_ROLES).
        resp = client.post(
            f"/api/staff/leaves/{leave_id}/approve",
            json={"reviewed_by_id": reviewer.id},
            headers=doctor_headers,
        )
        assert_forbidden(resp)

    def test_approve_leave_happy_path(self, client, clinic, staff, make_staff, make_authenticated_staff):
        reviewer = make_staff(clinic)
        admin_headers = _headers(make_authenticated_staff, clinic, Role.ADMIN)

        create_resp = client.post(
            "/api/staff/leaves",
            json={
                "staff_id": staff.id,
                "leave_type": "sick",
                "start_date": str(date.today()),
                "end_date": str(date.today() + timedelta(days=1)),
            },
            headers=admin_headers,
        )
        leave_id = create_resp.get_json()["data"]["id"]

        resp = client.post(
            f"/api/staff/leaves/{leave_id}/approve",
            json={"reviewed_by_id": reviewer.id},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["status"] == "approved"


class TestPayrollRoutes:
    def test_payroll_requires_accountant_or_admin(self, client, clinic, staff, make_authenticated_staff, assert_forbidden):
        nurse_headers = _headers(make_authenticated_staff, clinic, Role.NURSE)
        resp = client.post(
            "/api/staff/payroll",
            json={
                "staff_id": staff.id,
                "pay_period_start": "2026-01-01",
                "pay_period_end": "2026-01-31",
                "base_salary": "1000",
            },
            headers=nurse_headers,
        )
        assert_forbidden(resp)

    def test_create_and_pay_payroll_record(self, client, clinic, staff, make_authenticated_staff):
        headers = _headers(make_authenticated_staff, clinic, Role.ACCOUNTANT)

        create_resp = client.post(
            "/api/staff/payroll",
            json={
                "staff_id": staff.id,
                "pay_period_start": "2026-01-01",
                "pay_period_end": "2026-01-31",
                "base_salary": "1000",
                "bonuses": "50",
            },
            headers=headers,
        )
        assert create_resp.status_code == 201
        record_id = create_resp.get_json()["data"]["id"]
        assert create_resp.get_json()["data"]["net_pay"] == "1050.00"

        pay_resp = client.post(f"/api/staff/payroll/{record_id}/pay", headers=headers)
        assert pay_resp.status_code == 200
        assert pay_resp.get_json()["data"]["paid_at"] is not None

    def test_list_payroll_requires_staff_id_query_param(self, client, clinic, make_authenticated_staff):
        headers = _headers(make_authenticated_staff, clinic, Role.ACCOUNTANT)
        resp = client.get("/api/staff/payroll", headers=headers)
        # This one is NOT a pydantic/domain error -- staff_route.py
        # returns a bare {"error": ...} 422 directly, no "success" key,
        # different again from both other error shapes.
        assert resp.status_code == 422
        assert "error" in resp.get_json()

    def test_generate_payroll_for_period(self, client, clinic, make_staff, make_authenticated_staff):
        s1 = make_staff(clinic)
        headers = _headers(make_authenticated_staff, clinic, Role.ADMIN)

        resp = client.post(
            "/api/staff/payroll/generate",
            json={
                "clinic_id": clinic.id,
                "pay_period_start": "2026-03-01",
                "pay_period_end": "2026-03-31",
                "salary_lookup": {str(s1.id): "1500"},
            },
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.get_json()["count"] == 1