from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.enums.reports_enums import ReportFormat, ReportType
from app.core.enums.role_enums import Role
from app.modules.reports.routes import reports_route


def _utcnow():
    return datetime.now(timezone.utc)


def _json_headers(
    make_authenticated_staff,
    clinic,
    role,
):
    staff, headers = make_authenticated_staff(
        clinic,
        role,
    )

    headers = dict(headers)
    headers["Content-Type"] = "application/json"

    return headers, staff


def _report_payload(
    report_type=ReportType.PATIENTS,
    report_format=ReportFormat.CSV,
    filters=None,
):
    payload = {
        "report_type": report_type.value,
        "report_format": report_format.value,
    }

    if filters is not None:
        payload["filters"] = filters

    return payload


def _make_report(
    *,
    report_id=1,
    clinic_id=1,
    generated_by_id=1,
    report_type=ReportType.PATIENTS,
    report_format=ReportFormat.CSV,
    filters=None,
    file_url="generated_reports/clinic_1_patients_test.csv",
):
    now = _utcnow()

    return SimpleNamespace(
        id=report_id,
        clinic_id=clinic_id,
        generated_by_id=generated_by_id,
        report_type=report_type,
        report_format=report_format,
        filters=filters,
        file_url=file_url,
        created_at=now,
        updated_at=now,
    )


class TestCreateReport:
    def test_create_report_success(
        self,
        client,
        clinic,
        make_authenticated_staff,
        monkeypatch,
    ):
        headers, staff = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.ADMIN,
        )

        report = _make_report(
            report_id=101,
            clinic_id=clinic.id,
            generated_by_id=staff.id,
        )

        create_mock = Mock(
            return_value=report,
        )

        monkeypatch.setattr(
            reports_route,
            "generate_report",
            create_mock,
        )

        response = client.post(
            "/api/reports",
            json=_report_payload(
                report_type=ReportType.PATIENTS,
                report_format=ReportFormat.CSV,
            ),
            headers=headers,
        )

        assert response.status_code == 201

        body = response.get_json()

        assert body["success"] is True
        assert body["message"] == (
            "Report generated successfully"
        )

        data = body["data"]

        assert data["id"] == 101
        assert data["clinic_id"] == clinic.id
        assert data["generated_by_id"] == staff.id
        assert data["report_type"] == (
            ReportType.PATIENTS.value
        )
        assert data["report_format"] == (
            ReportFormat.CSV.value
        )

        create_mock.assert_called_once()

        call = create_mock.call_args

        assert call.kwargs["requester_user_id"] == staff.user_id
        assert call.kwargs["clinic_id"] == clinic.id
        assert call.kwargs["report_type"] == (
            ReportType.PATIENTS
        )
        assert call.kwargs["report_format"] == (
            ReportFormat.CSV
        )
        assert call.kwargs["filters"] is None

    def test_create_report_passes_filters_to_service(
        self,
        client,
        clinic,
        make_authenticated_staff,
        monkeypatch,
    ):
        headers, staff = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.ADMIN,
        )

        filters = {
            "date_from": "2026-09-01",
            "date_to": "2026-09-08",
            "active_only": True,
        }

        report = _make_report(
            clinic_id=clinic.id,
            generated_by_id=staff.id,
            filters=filters,
        )

        create_mock = Mock(
            return_value=report,
        )

        monkeypatch.setattr(
            reports_route,
            "generate_report",
            create_mock,
        )

        response = client.post(
            "/api/reports",
            json=_report_payload(
                report_type=ReportType.PATIENTS,
                report_format=ReportFormat.CSV,
                filters=filters,
            ),
            headers=headers,
        )

        assert response.status_code == 201

        create_mock.assert_called_once()

        call = create_mock.call_args

        assert call.kwargs["requester_user_id"] == staff.user_id
        assert call.kwargs["clinic_id"] == clinic.id
        assert call.kwargs["report_type"] == (
            ReportType.PATIENTS
        )
        assert call.kwargs["report_format"] == (
            ReportFormat.CSV
        )
        assert call.kwargs["filters"] == filters

    def test_create_report_uses_authenticated_clinic(
        self,
        client,
        clinic,
        make_authenticated_staff,
        monkeypatch,
    ):
        headers, _ = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.ADMIN,
        )

        create_mock = Mock()

        monkeypatch.setattr(
            reports_route,
            "generate_report",
            create_mock,
        )

        response = client.post(
            "/api/reports",
            json={
                "report_type": ReportType.PATIENTS.value,
                "report_format": ReportFormat.CSV.value,
                "clinic_id": 999999,
            },
            headers=headers,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"

        create_mock.assert_not_called()

    def test_create_report_rejects_unknown_fields(
        self,
        client,
        clinic,
        make_authenticated_staff,
    ):
        headers, _ = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.ADMIN,
        )

        payload = _report_payload()

        payload["generated_by_id"] = 999
        payload["clinic_id"] = 999

        response = client.post(
            "/api/reports",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"

    def test_create_report_requires_report_type(
        self,
        client,
        clinic,
        make_authenticated_staff,
    ):
        headers, _ = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.ADMIN,
        )

        response = client.post(
            "/api/reports",
            json={
                "report_format": ReportFormat.CSV.value,
            },
            headers=headers,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"

    @pytest.mark.parametrize(
        "report_type",
        [
            "",
            "invalid",
            "does_not_exist",
        ],
    )
    def test_create_report_rejects_invalid_report_type(
        self,
        client,
        clinic,
        make_authenticated_staff,
        report_type,
    ):
        headers, _ = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.ADMIN,
        )

        response = client.post(
            "/api/reports",
            json={
                "report_type": report_type,
                "report_format": ReportFormat.CSV.value,
            },
            headers=headers,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"

    @pytest.mark.parametrize(
        "report_format",
        [
            "",
            "invalid",
            "docx",
            "json",
        ],
    )
    def test_create_report_rejects_invalid_report_format(
        self,
        client,
        clinic,
        make_authenticated_staff,
        report_format,
    ):
        headers, _ = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.ADMIN,
        )

        response = client.post(
            "/api/reports",
            json={
                "report_type": ReportType.PATIENTS.value,
                "report_format": report_format,
            },
            headers=headers,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"

    def test_create_report_defaults_format_to_csv(
        self,
        client,
        clinic,
        make_authenticated_staff,
        monkeypatch,
    ):
        headers, staff = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.ADMIN,
        )

        report = _make_report(
            clinic_id=clinic.id,
            generated_by_id=staff.id,
            report_format=ReportFormat.CSV,
        )

        create_mock = Mock(
            return_value=report,
        )

        monkeypatch.setattr(
            reports_route,
            "generate_report",
            create_mock,
        )

        response = client.post(
            "/api/reports",
            json={
                "report_type": ReportType.PATIENTS.value,
            },
            headers=headers,
        )

        assert response.status_code == 201

        create_mock.assert_called_once()

        assert (
            create_mock.call_args.kwargs["report_format"]
            == ReportFormat.CSV
        )

    def test_create_report_accepts_date_filters(
        self,
        client,
        clinic,
        make_authenticated_staff,
        monkeypatch,
    ):
        headers, staff = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.ADMIN,
        )

        filters = {
            "date_from": "2026-09-01",
            "date_to": "2026-09-08",
            "active_only": True,
        }

        report = _make_report(
            clinic_id=clinic.id,
            generated_by_id=staff.id,
            filters=filters,
        )

        create_mock = Mock(
            return_value=report,
        )

        monkeypatch.setattr(
            reports_route,
            "generate_report",
            create_mock,
        )

        response = client.post(
            "/api/reports",
            json=_report_payload(
                filters=filters,
            ),
            headers=headers,
        )

        assert response.status_code == 201

        assert (
            create_mock.call_args.kwargs["filters"]
            == filters
        )

    def test_create_report_rejects_unknown_filter(
        self,
        client,
        clinic,
        make_authenticated_staff,
    ):
        headers, _ = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.ADMIN,
        )

        response = client.post(
            "/api/reports",
            json=_report_payload(
                filters={
                    "date_from": "2026-09-01",
                    "unknown_filter": True,
                }
            ),
            headers=headers,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"

    def test_create_report_rejects_reversed_filter_dates(
        self,
        client,
        clinic,
        make_authenticated_staff,
    ):
        headers, _ = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.ADMIN,
        )

        response = client.post(
            "/api/reports",
            json=_report_payload(
                filters={
                    "date_from": "2026-09-08",
                    "date_to": "2026-09-01",
                }
            ),
            headers=headers,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"

    def test_create_report_rejects_invalid_active_only(
        self,
        client,
        clinic,
        make_authenticated_staff,
    ):
        headers, _ = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.ADMIN,
        )

        response = client.post(
            "/api/reports",
            json=_report_payload(
                filters={
                    "active_only": "yes",
                }
            ),
            headers=headers,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"

    def test_create_report_accepts_empty_json_body_as_validation_failure(
        self,
        client,
        clinic,
        make_authenticated_staff,
    ):
        headers, _ = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.ADMIN,
        )

        response = client.post(
            "/api/reports",
            json={},
            headers=headers,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"

    def test_create_report_handles_domain_error(
        self,
        client,
        clinic,
        make_authenticated_staff,
        monkeypatch,
    ):
        headers, _ = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.ADMIN,
        )

        from app.core.exceptions import ValidationError

        error = ValidationError(
            "Clinic is inactive"
        )

        create_mock = Mock(
            side_effect=error,
        )

        monkeypatch.setattr(
            reports_route,
            "generate_report",
            create_mock,
        )

        response = client.post(
            "/api/reports",
            json=_report_payload(),
            headers=headers,
        )

        assert response.status_code == error.status_code

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Clinic is inactive"

        create_mock.assert_called_once()

    def test_create_report_handles_unexpected_service_error(
        self,
        client,
        clinic,
        make_authenticated_staff,
        monkeypatch,
    ):
        headers, _ = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.ADMIN,
        )

        create_mock = Mock(
            side_effect=RuntimeError(
                "database exploded"
            ),
        )

        monkeypatch.setattr(
            reports_route,
            "generate_report",
            create_mock,
        )

        response = client.post(
            "/api/reports",
            json=_report_payload(),
            headers=headers,
        )

        assert response.status_code == 400

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "An unexpected error occurred"
        )

        create_mock.assert_called_once()

    def test_create_report_does_not_leak_internal_exception(
        self,
        client,
        clinic,
        make_authenticated_staff,
        monkeypatch,
    ):
        headers, _ = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.ADMIN,
        )

        create_mock = Mock(
            side_effect=RuntimeError(
                "SECRET DATABASE INFORMATION"
            ),
        )

        monkeypatch.setattr(
            reports_route,
            "generate_report",
            create_mock,
        )

        response = client.post(
            "/api/reports",
            json=_report_payload(),
            headers=headers,
        )

        assert response.status_code == 400

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "An unexpected error occurred"
        )

        assert "SECRET DATABASE INFORMATION" not in (
            response.get_data(
                as_text=True
            )
        )

    def test_create_report_serializes_response_through_schema(
        self,
        client,
        clinic,
        make_authenticated_staff,
        monkeypatch,
    ):
        headers, staff = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.ADMIN,
        )

        report = _make_report(
            report_id=55,
            clinic_id=clinic.id,
            generated_by_id=staff.id,
            report_type=ReportType.BILLING,
            report_format=ReportFormat.CSV,
            filters={
                "date_from": "2026-09-01",
                "active_only": True,
            },
            file_url=(
                "generated_reports/"
                "clinic_1_billing_test.csv"
            ),
        )

        create_mock = Mock(
            return_value=report,
        )

        monkeypatch.setattr(
            reports_route,
            "generate_report",
            create_mock,
        )

        response = client.post(
            "/api/reports",
            json=_report_payload(
                report_type=ReportType.BILLING,
                report_format=ReportFormat.CSV,
                filters={
                    "date_from": "2026-09-01",
                    "active_only": True,
                },
            ),
            headers=headers,
        )

        assert response.status_code == 201

        body = response.get_json()
        data = body["data"]

        assert data["id"] == 55
        assert data["clinic_id"] == clinic.id
        assert data["generated_by_id"] == staff.id
        assert data["report_type"] == (
            ReportType.BILLING.value
        )
        assert data["report_format"] == (
            ReportFormat.CSV.value
        )

        assert data["filters"] == {
            "date_from": "2026-09-01",
            "active_only": True,
        }

        assert data["file_url"] == (
            "generated_reports/"
            "clinic_1_billing_test.csv"
        )

        assert "created_at" in data
        assert "updated_at" in data

    def test_create_report_rejects_non_object_json(
        self,
        client,
        clinic,
        make_authenticated_staff,
    ):
        headers, _ = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.ADMIN,
        )

        response = client.post(
            "/api/reports",
            json=[],
            headers=headers,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"


class TestCreateReportAuthorization:
    @pytest.mark.parametrize(
        "role",
        [
            Role.ADMIN,
            Role.DOCTOR,
            Role.NURSE,
            Role.RECEPTIONIST,
            Role.ACCOUNTANT,
            Role.PHARMACIST,
            Role.LAB_TECHNICIAN,
        ],
    )
    def test_generation_role_is_allowed(
        self,
        client,
        clinic,
        make_authenticated_staff,
        monkeypatch,
        role,
    ):
        headers, staff = _json_headers(
            make_authenticated_staff,
            clinic,
            role,
        )

        report = _make_report(
            report_id=100,
            clinic_id=clinic.id,
            generated_by_id=staff.id,
        )

        create_mock = Mock(
            return_value=report,
        )

        monkeypatch.setattr(
            reports_route,
            "generate_report",
            create_mock,
        )

        response = client.post(
            "/api/reports",
            json=_report_payload(),
            headers=headers,
        )

        assert response.status_code == 201
        create_mock.assert_called_once()

    @pytest.mark.parametrize(
        "role",
        [
            Role.PATIENT,
        ],
    )
    def test_unauthorized_generation_role_is_rejected(
        self,
        client,
        clinic,
        make_authenticated_staff,
        monkeypatch,
        role,
    ):
        headers, _ = _json_headers(
            make_authenticated_staff,
            clinic,
            role,
        )

        create_mock = Mock()

        monkeypatch.setattr(
            reports_route,
            "generate_report",
            create_mock,
        )

        response = client.post(
            "/api/reports",
            json=_report_payload(),
            headers=headers,
        )

        assert response.status_code == 403
        create_mock.assert_not_called()


def test_create_report_route_exists(
    client,
):
    response = client.post(
        "/api/reports",
        json={},
    )

    assert response.status_code != 404