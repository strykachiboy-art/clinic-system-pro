from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.enums.reports_enums import (
    ReportFormat,
    ReportType,
)
from app.core.enums.role_enums import Role
from app.core.exceptions import (
    DomainError,
    NotFoundError,
    ValidationError,
)
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


# ============================================================================
# Create report
# ============================================================================

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
            "/api/v1/reports",
            json=_report_payload(),
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
            "/api/v1/reports",
            json=_report_payload(
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
            "/api/v1/reports",
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
            "/api/v1/reports",
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
            "/api/v1/reports",
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
            "/api/v1/reports",
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
            "/api/v1/reports",
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
            "/api/v1/reports",
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
            "/api/v1/reports",
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
            "/api/v1/reports",
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
            "/api/v1/reports",
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
            "/api/v1/reports",
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
            "/api/v1/reports",
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
            "/api/v1/reports",
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
            "/api/v1/reports",
            json=_report_payload(),
            headers=headers,
        )

        assert response.status_code == 500

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
            "/api/v1/reports",
            json=_report_payload(),
            headers=headers,
        )

        assert response.status_code == 500

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
            "/api/v1/reports",
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
            "/api/v1/reports",
            json=[],
            headers=headers,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"


# ============================================================================
# Create report authorization
# ============================================================================

class TestCreateReportAuthorization:
    @pytest.mark.parametrize(
        "role",
        [
            Role.SUPER_ADMIN,
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
            "/api/v1/reports",
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
            "/api/v1/reports",
            json=_report_payload(),
            headers=headers,
        )

        assert response.status_code == 403
        create_mock.assert_not_called()


# ============================================================================
# List reports
# ============================================================================

class TestGetReports:
    def test_get_reports_success(
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

        list_mock = Mock(
            return_value={
                "items": [
                    report,
                ],
                "total": 1,
                "page": 1,
                "per_page": 20,
            },
        )

        monkeypatch.setattr(
            reports_route,
            "list_reports",
            list_mock,
        )

        response = client.get(
            "/api/v1/reports",
            headers=headers,
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"]["total"] == 1
        assert body["data"]["page"] == 1
        assert body["data"]["per_page"] == 20
        assert len(body["data"]["items"]) == 1

        item = body["data"]["items"][0]

        assert item["id"] == 101
        assert item["clinic_id"] == clinic.id

        list_mock.assert_called_once()

        call = list_mock.call_args

        assert call.kwargs["requester_user_id"] == staff.user_id
        assert call.kwargs["clinic_id"] == clinic.id
        assert call.kwargs["generated_by_id"] is None
        assert call.kwargs["report_type"] is None
        assert call.kwargs["report_format"] is None
        assert call.kwargs["date_from"] is None
        assert call.kwargs["date_to"] is None
        assert call.kwargs["page"] == 1
        assert call.kwargs["per_page"] == 20

    def test_get_reports_passes_query_filters(
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

        list_mock = Mock(
            return_value={
                "items": [],
                "total": 0,
                "page": 2,
                "per_page": 10,
            },
        )

        monkeypatch.setattr(
            reports_route,
            "list_reports",
            list_mock,
        )

        response = client.get(
            "/api/v1/reports",
            query_string={
                "report_type": ReportType.PATIENTS.value,
                "report_format": ReportFormat.CSV.value,
                "date_from": "2026-09-01",
                "date_to": "2026-09-08",
                "generated_by_id": str(
                    staff.user_id
                ),
                "page": "2",
                "per_page": "10",
            },
            headers=headers,
        )

        assert response.status_code == 200

        list_mock.assert_called_once()

        call = list_mock.call_args

        assert call.kwargs["requester_user_id"] == staff.user_id
        assert call.kwargs["clinic_id"] == clinic.id
        assert call.kwargs["report_type"] == ReportType.PATIENTS
        assert call.kwargs["report_format"] == ReportFormat.CSV
        assert call.kwargs["date_from"] == datetime(
            2026,
            9,
            1,
        ).date()
        assert call.kwargs["date_to"] == datetime(
            2026,
            9,
            8,
        ).date()
        assert call.kwargs["generated_by_id"] == staff.user_id
        assert call.kwargs["page"] == 2
        assert call.kwargs["per_page"] == 10

    def test_get_reports_rejects_invalid_report_type(
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

        response = client.get(
            "/api/v1/reports",
            query_string={
                "report_type": "invalid",
            },
            headers=headers,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"

    def test_get_reports_rejects_invalid_report_format(
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

        response = client.get(
            "/api/v1/reports",
            query_string={
                "report_format": "invalid",
            },
            headers=headers,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"

    def test_get_reports_rejects_invalid_date_range(
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

        response = client.get(
            "/api/v1/reports",
            query_string={
                "date_from": "2026-09-08",
                "date_to": "2026-09-01",
            },
            headers=headers,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"

    def test_get_reports_rejects_invalid_pagination(
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

        response = client.get(
            "/api/v1/reports",
            query_string={
                "page": "0",
            },
            headers=headers,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"

    def test_get_reports_handles_domain_error(
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

        error = ValidationError(
            "Unauthorized clinic access"
        )

        list_mock = Mock(
            side_effect=error,
        )

        monkeypatch.setattr(
            reports_route,
            "list_reports",
            list_mock,
        )

        response = client.get(
            "/api/v1/reports",
            headers=headers,
        )

        assert response.status_code == error.status_code

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "Unauthorized clinic access"
        )

    def test_get_reports_handles_unexpected_service_error(
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

        list_mock = Mock(
            side_effect=RuntimeError(
                "unexpected database failure"
            ),
        )

        monkeypatch.setattr(
            reports_route,
            "list_reports",
            list_mock,
        )

        response = client.get(
            "/api/v1/reports",
            headers=headers,
        )

        assert response.status_code == 500

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "An unexpected error occurred"
        )

        assert "unexpected database failure" not in (
            response.get_data(
                as_text=True
            )
        )

    def test_get_reports_serializes_items_through_schema(
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
        )

        list_mock = Mock(
            return_value={
                "items": [
                    report,
                ],
                "total": 1,
                "page": 1,
                "per_page": 20,
            },
        )

        monkeypatch.setattr(
            reports_route,
            "list_reports",
            list_mock,
        )

        response = client.get(
            "/api/v1/reports",
            headers=headers,
        )

        assert response.status_code == 200

        body = response.get_json()
        item = body["data"]["items"][0]

        assert item["id"] == 55
        assert item["clinic_id"] == clinic.id
        assert item["generated_by_id"] == staff.id
        assert item["report_type"] == (
            ReportType.BILLING.value
        )
        assert item["report_format"] == (
            ReportFormat.CSV.value
        )

        assert item["filters"] == {
            "date_from": "2026-09-01",
            "active_only": True,
        }

    def test_get_reports_non_admin_is_scoped_to_authenticated_clinic(
        self,
        client,
        clinic,
        make_authenticated_staff,
        monkeypatch,
    ):
        headers, staff = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.DOCTOR,
        )

        list_mock = Mock(
            return_value={
                "items": [],
                "total": 0,
                "page": 1,
                "per_page": 20,
            },
        )

        monkeypatch.setattr(
            reports_route,
            "list_reports",
            list_mock,
        )

        response = client.get(
            "/api/v1/reports",
            headers=headers,
        )

        assert response.status_code == 200

        assert (
            list_mock.call_args.kwargs["clinic_id"]
            == clinic.id
        )

        assert (
            list_mock.call_args.kwargs[
                "requester_user_id"
            ]
            == staff.user_id
        )

    def test_get_reports_super_admin_is_system_wide(
        self,
        client,
        clinic,
        make_authenticated_staff,
        monkeypatch,
    ):
        headers, staff = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.SUPER_ADMIN,
        )

        list_mock = Mock(
            return_value={
                "items": [],
                "total": 0,
                "page": 1,
                "per_page": 20,
            },
        )

        monkeypatch.setattr(
            reports_route,
            "list_reports",
            list_mock,
        )

        response = client.get(
            "/api/v1/reports",
            headers=headers,
        )

        assert response.status_code == 200

        list_mock.assert_called_once()

        assert (
            list_mock.call_args.kwargs[
                "requester_user_id"
            ]
            == staff.user_id
        )

        assert (
            list_mock.call_args.kwargs[
                "clinic_id"
            ]
            is None
        )


class TestGetReportsAuthorization:
    @pytest.mark.parametrize(
        "role",
        [
            Role.SUPER_ADMIN,
            Role.ADMIN,
            Role.DOCTOR,
            Role.NURSE,
            Role.RECEPTIONIST,
            Role.ACCOUNTANT,
            Role.PHARMACIST,
            Role.LAB_TECHNICIAN,
        ],
    )
    def test_view_role_is_allowed(
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

        list_mock = Mock(
            return_value={
                "items": [],
                "total": 0,
                "page": 1,
                "per_page": 20,
            },
        )

        monkeypatch.setattr(
            reports_route,
            "list_reports",
            list_mock,
        )

        response = client.get(
            "/api/v1/reports",
            headers=headers,
        )

        assert response.status_code == 200
        list_mock.assert_called_once()

    def test_patient_cannot_view_reports(
        self,
        client,
        clinic,
        make_authenticated_staff,
        monkeypatch,
    ):
        headers, _ = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.PATIENT,
        )

        list_mock = Mock()

        monkeypatch.setattr(
            reports_route,
            "list_reports",
            list_mock,
        )

        response = client.get(
            "/api/v1/reports",
            headers=headers,
        )

        assert response.status_code == 403
        list_mock.assert_not_called()


# ============================================================================
# Get single report
# ============================================================================

class TestGetSingleReport:
    def test_get_single_report_success(
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

        get_mock = Mock(
            return_value=report,
        )

        monkeypatch.setattr(
            reports_route,
            "get_report",
            get_mock,
        )

        response = client.get(
            "/api/v1/reports/101",
            headers=headers,
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"]["id"] == 101
        assert body["data"]["clinic_id"] == clinic.id
        assert body["data"]["generated_by_id"] == staff.id

        get_mock.assert_called_once()

        call = get_mock.call_args

        assert call.kwargs["report_id"] == 101
        assert (
            call.kwargs["requester_user_id"]
            == staff.user_id
        )

    @pytest.mark.parametrize(
        "report_id",
        [
            1,
            10,
            999999,
        ],
    )
    def test_get_single_report_passes_path_id_to_service(
        self,
        client,
        clinic,
        make_authenticated_staff,
        monkeypatch,
        report_id,
    ):
        headers, staff = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.DOCTOR,
        )

        report = _make_report(
            report_id=report_id,
            clinic_id=clinic.id,
            generated_by_id=staff.id,
        )

        get_mock = Mock(
            return_value=report,
        )

        monkeypatch.setattr(
            reports_route,
            "get_report",
            get_mock,
        )

        response = client.get(
            f"/api/v1/reports/{report_id}",
            headers=headers,
        )

        assert response.status_code == 200

        assert (
            get_mock.call_args.kwargs[
                "report_id"
            ]
            == report_id
        )

        assert (
            get_mock.call_args.kwargs[
                "requester_user_id"
            ]
            == staff.user_id
        )

    def test_get_single_report_handles_not_found(
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

        error = NotFoundError(
            "Report 999 not found"
        )

        get_mock = Mock(
            side_effect=error,
        )

        monkeypatch.setattr(
            reports_route,
            "get_report",
            get_mock,
        )

        response = client.get(
            "/api/v1/reports/999",
            headers=headers,
        )

        assert response.status_code == error.status_code

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "Report 999 not found"
        )

    def test_get_single_report_handles_domain_error(
        self,
        client,
        clinic,
        make_authenticated_staff,
        monkeypatch,
    ):
        headers, _ = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.DOCTOR,
        )

        error = ValidationError(
            "Unauthorized report access"
        )

        get_mock = Mock(
            side_effect=error,
        )

        monkeypatch.setattr(
            reports_route,
            "get_report",
            get_mock,
        )

        response = client.get(
            "/api/v1/reports/123",
            headers=headers,
        )

        assert response.status_code == error.status_code

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "Unauthorized report access"
        )

    def test_get_single_report_handles_unexpected_service_error(
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

        get_mock = Mock(
            side_effect=RuntimeError(
                "private database failure"
            ),
        )

        monkeypatch.setattr(
            reports_route,
            "get_report",
            get_mock,
        )

        response = client.get(
            "/api/v1/reports/123",
            headers=headers,
        )

        assert response.status_code == 500

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "An unexpected error occurred"
        )

        assert "private database failure" not in (
            response.get_data(
                as_text=True
            )
        )

    def test_get_single_report_serializes_response_through_schema(
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
            report_id=77,
            clinic_id=clinic.id,
            generated_by_id=staff.id,
            report_type=ReportType.LAB,
            report_format=ReportFormat.PDF,
            filters={
                "date_from": "2026-09-01",
            },
            file_url=(
                "generated_reports/"
                "clinic_1_lab_test.pdf"
            ),
        )

        get_mock = Mock(
            return_value=report,
        )

        monkeypatch.setattr(
            reports_route,
            "get_report",
            get_mock,
        )

        response = client.get(
            "/api/v1/reports/77",
            headers=headers,
        )

        assert response.status_code == 200

        body = response.get_json()
        data = body["data"]

        assert data["id"] == 77
        assert data["clinic_id"] == clinic.id
        assert data["generated_by_id"] == staff.id
        assert data["report_type"] == (
            ReportType.LAB.value
        )
        assert data["report_format"] == (
            ReportFormat.PDF.value
        )
        assert data["filters"] == {
            "date_from": "2026-09-01",
        }
        assert data["file_url"] == (
            "generated_reports/"
            "clinic_1_lab_test.pdf"
        )

        assert "created_at" in data
        assert "updated_at" in data

    def test_get_single_report_super_admin_can_request_cross_clinic_report(
        self,
        client,
        clinic,
        make_authenticated_staff,
        monkeypatch,
    ):
        headers, staff = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.SUPER_ADMIN,
        )

        report = _make_report(
            report_id=200,
            clinic_id=999,
            generated_by_id=300,
        )

        get_mock = Mock(
            return_value=report,
        )

        monkeypatch.setattr(
            reports_route,
            "get_report",
            get_mock,
        )

        response = client.get(
            "/api/v1/reports/200",
            headers=headers,
        )

        assert response.status_code == 200

        assert (
            get_mock.call_args.kwargs[
                "report_id"
            ]
            == 200
        )

        assert (
            get_mock.call_args.kwargs[
                "requester_user_id"
            ]
            == staff.user_id
        )


class TestGetSingleReportAuthorization:
    @pytest.mark.parametrize(
        "role",
        [
            Role.SUPER_ADMIN,
            Role.ADMIN,
            Role.DOCTOR,
            Role.NURSE,
            Role.RECEPTIONIST,
            Role.ACCOUNTANT,
            Role.PHARMACIST,
            Role.LAB_TECHNICIAN,
        ],
    )
    def test_view_role_can_access_single_report_route(
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
            report_id=10,
            clinic_id=clinic.id,
            generated_by_id=staff.id,
        )

        get_mock = Mock(
            return_value=report,
        )

        monkeypatch.setattr(
            reports_route,
            "get_report",
            get_mock,
        )

        response = client.get(
            "/api/v1/reports/10",
            headers=headers,
        )

        assert response.status_code == 200
        get_mock.assert_called_once()

    def test_patient_cannot_access_single_report(
        self,
        client,
        clinic,
        make_authenticated_staff,
        monkeypatch,
    ):
        headers, _ = _json_headers(
            make_authenticated_staff,
            clinic,
            Role.PATIENT,
        )

        get_mock = Mock()

        monkeypatch.setattr(
            reports_route,
            "get_report",
            get_mock,
        )

        response = client.get(
            "/api/v1/reports/10",
            headers=headers,
        )

        assert response.status_code == 403
        get_mock.assert_not_called()


# ============================================================================
# Authentication helper hardening
# ============================================================================

class TestAuthenticatedUserHelpers:
    @pytest.mark.parametrize(
        "identity",
        [
            "1",
            1,
        ],
    )
    def test_parse_authenticated_user_id_accepts_positive_integer_identity(
        self,
        identity,
    ):
        assert (
            reports_route._parse_authenticated_user_id(
                identity
            )
            == 1
        )

    @pytest.mark.parametrize(
        "identity",
        [
            "",
            " ",
            "abc",
            "1.0",
            "1abc",
            0,
            -1,
            True,
            False,
            1.0,
            None,
            [],
            {},
        ],
    )
    def test_parse_authenticated_user_id_rejects_invalid_identity(
        self,
        identity,
    ):
        with pytest.raises(ValidationError):
            reports_route._parse_authenticated_user_id(
                identity
            )

    def test_get_current_user_rejects_unresolvable_user(
        self,
        monkeypatch,
    ):
        monkeypatch.setattr(
            reports_route,
            "get_jwt_identity",
            lambda: "999999",
        )

        monkeypatch.setattr(
            reports_route.db.session,
            "get",
            lambda *args, **kwargs: None,
        )

        with pytest.raises(ValidationError):
            reports_route._get_current_user()

    def test_get_current_user_rejects_inactive_user(
        self,
        monkeypatch,
    ):
        user = SimpleNamespace(
            id=1,
            clinic_id=10,
            is_active=False,
        )

        monkeypatch.setattr(
            reports_route,
            "get_jwt_identity",
            lambda: "1",
        )

        monkeypatch.setattr(
            reports_route.db.session,
            "get",
            lambda *args, **kwargs: user,
        )

        with pytest.raises(ValidationError):
            reports_route._get_current_user()

    def test_get_current_user_returns_active_user(
        self,
        monkeypatch,
    ):
        user = SimpleNamespace(
            id=1,
            clinic_id=10,
            is_active=True,
        )

        monkeypatch.setattr(
            reports_route,
            "get_jwt_identity",
            lambda: "1",
        )

        monkeypatch.setattr(
            reports_route.db.session,
            "get",
            lambda *args, **kwargs: user,
        )

        result = reports_route._get_current_user()

        assert result is user

    def test_get_current_user_id_uses_valid_user_object(
        self,
    ):
        user = SimpleNamespace(
            id=10,
        )

        assert (
            reports_route._get_current_user_id(
                user
            )
            == 10
        )

    @pytest.mark.parametrize(
        "user_id",
        [
            0,
            -1,
            True,
            "10",
            10.0,
            None,
        ],
    )
    def test_get_current_user_id_rejects_invalid_user_object_id(
        self,
        user_id,
    ):
        user = SimpleNamespace(
            id=user_id,
        )

        with pytest.raises(ValidationError):
            reports_route._get_current_user_id(
                user
            )

    def test_get_current_user_id_rejects_invalid_identity(
        self,
        monkeypatch,
    ):
        monkeypatch.setattr(
            reports_route,
            "get_jwt_identity",
            lambda: "invalid",
        )

        with pytest.raises(ValidationError):
            reports_route._get_current_user_id()

    def test_get_current_clinic_id_returns_valid_clinic(
        self,
    ):
        user = SimpleNamespace(
            clinic_id=10,
        )

        assert (
            reports_route._get_current_clinic_id(
                user
            )
            == 10
        )

    @pytest.mark.parametrize(
        "clinic_id",
        [
            None,
            0,
            -1,
            True,
            False,
            "10",
            10.0,
            "0010",
        ],
    )
    def test_get_current_clinic_id_rejects_non_strict_values(
        self,
        clinic_id,
    ):
        user = SimpleNamespace(
            clinic_id=clinic_id,
        )

        with pytest.raises(DomainError):
            reports_route._get_current_clinic_id(
                user
            )


# ============================================================================
# Route existence
# ============================================================================

class TestRouteExistence:
    def test_create_report_route_exists(
        self,
        client,
    ):
        response = client.post(
            "/api/v1/reports",
            json={},
        )

        assert response.status_code != 404

    def test_get_reports_route_exists(
        self,
        client,
    ):
        response = client.get(
            "/api/v1/reports",
        )

        assert response.status_code != 404

    def test_get_single_report_route_exists(
        self,
        client,
    ):
        response = client.get(
            "/api/v1/reports/1",
        )

        assert response.status_code != 404

    def test_non_integer_report_id_does_not_match_single_report_route(
        self,
        client,
    ):
        response = client.get(
            "/api/v1/reports/not-an-integer",
        )

        assert response.status_code == 404
