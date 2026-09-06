from app.core.enums.role_enums import Role


def _headers(make_authenticated_staff, clinic, role):
    _, h = make_authenticated_staff(clinic, role)
    return h


class TestReportRoutes:
    def test_create_report_requires_auth(self, client, assert_unauthorized):
        resp = client.post("/api/reports", json={"clinic_id": 1, "report_type": "patients"})
        assert_unauthorized(resp)

    def test_create_report_requires_allowed_role(self, client, clinic, make_authenticated_staff, assert_forbidden):
        # LAB_TECHNICIAN is not in REPORT_GENERATION_ROLES... actually it is,
        # so use PARAMEDIC which is not in the allowed set at all.
        headers = _headers(make_authenticated_staff, clinic, Role.PARAMEDIC)
        resp = client.post(
            "/api/reports", json={"clinic_id": clinic.id, "report_type": "patients"}, headers=headers
        )
        assert_forbidden(resp)

    def test_create_patients_csv_report_happy_path(self, client, clinic, make_patient, make_authenticated_staff):
        make_patient(clinic, first_name="Alice")
        headers = _headers(make_authenticated_staff, clinic, Role.RECEPTIONIST)

        resp = client.post(
            "/api/reports",
            json={"clinic_id": clinic.id, "report_type": "patients", "report_format": "csv"},
            headers=headers,
        )
        assert resp.status_code == 201
        body = resp.get_json()["data"]
        assert body["report_type"] == "patients"
        assert body["report_format"] == "csv"

    def test_create_report_rejects_pdf_format(self, client, clinic, make_authenticated_staff, assert_domain_error):
        headers = _headers(make_authenticated_staff, clinic, Role.ADMIN)
        resp = client.post(
            "/api/reports",
            json={"clinic_id": clinic.id, "report_type": "patients", "report_format": "pdf"},
            headers=headers,
        )
        assert_domain_error(resp, 422)

    def test_create_report_rejects_unsupported_inventory_type(
        self, client, clinic, make_authenticated_staff, assert_domain_error
    ):
        headers = _headers(make_authenticated_staff, clinic, Role.ADMIN)
        resp = client.post(
            "/api/reports",
            json={"clinic_id": clinic.id, "report_type": "inventory", "report_format": "csv"},
            headers=headers,
        )
        assert_domain_error(resp, 422)

    def test_create_report_with_filters(self, client, clinic, make_patient, make_authenticated_staff):
        make_patient(clinic)
        headers = _headers(make_authenticated_staff, clinic, Role.ADMIN)

        resp = client.post(
            "/api/reports",
            json={
                "clinic_id": clinic.id,
                "report_type": "patients",
                "report_format": "csv",
                "filters": {"date_from": "2020-01-01", "active_only": True},
            },
            headers=headers,
        )
        assert resp.status_code == 201

    def test_create_report_rejects_date_to_before_date_from(self, client, clinic, make_authenticated_staff):
        headers = _headers(make_authenticated_staff, clinic, Role.ADMIN)
        resp = client.post(
            "/api/reports",
            json={
                "clinic_id": clinic.id,
                "report_type": "patients",
                "report_format": "csv",
                "filters": {"date_from": "2020-06-01", "date_to": "2020-01-01"},
            },
            headers=headers,
        )
        # ReportFiltersSchema's field_validator rejects this before the
        # service is ever called.
        assert resp.status_code == 422

    def test_get_single_report_not_found(self, client, clinic, make_authenticated_staff, assert_domain_error):
        headers = _headers(make_authenticated_staff, clinic, Role.ADMIN)
        resp = client.get("/api/reports/999999", headers=headers)
        assert_domain_error(resp, 404)

    def test_get_single_report_happy_path(self, client, clinic, make_authenticated_staff):
        headers = _headers(make_authenticated_staff, clinic, Role.ADMIN)
        create_resp = client.post(
            "/api/reports",
            json={"clinic_id": clinic.id, "report_type": "staff", "report_format": "csv"},
            headers=headers,
        )
        report_id = create_resp.get_json()["data"]["id"]

        resp = client.get(f"/api/reports/{report_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["id"] == report_id

    def test_list_reports_scoped_and_paginated(self, client, clinic, make_authenticated_staff):
        admin_staff, headers = make_authenticated_staff(clinic, Role.ADMIN)

        for _ in range(3):
            client.post(
                "/api/reports",
                json={"clinic_id": clinic.id, "report_type": "staff", "report_format": "csv"},
                headers=headers,
            )

        resp = client.get("/api/reports?per_page=2", headers=headers)
        assert resp.status_code == 200
        body = resp.get_json()["data"]
        assert body["total"] == 3
        assert len(body["items"]) == 2