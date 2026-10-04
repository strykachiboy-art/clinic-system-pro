from __future__ import annotations

import csv
import io
from pathlib import Path

from app.core.audit.models.audit_model import AuditLog
from app.core.enums.audit_enums import AuditAction
from app.core.enums.reports_enums import (
    ReportFormat,
    ReportType,
)
from app.core.enums.role_enums import Role
from app.modules.reports.models.reports_model import GeneratedReport


def test_reporting_file_storage_e2e(
    client,
    db,
    clinic,
    make_clinic,
    make_staff,
    make_patient,
    e2e_login,
    monkeypatch,
    tmp_path,
):
    monkeypatch.chdir(tmp_path)

    admin = make_staff(
        clinic=clinic,
        role=Role.ADMIN,
        user_overrides={
            "email": "e2e-g11-report-admin@test.com",
        },
    )

    patient = make_patient(
        clinic,
        first_name="Gate",
        last_name="Eleven",
    )

    admin_login = e2e_login(
        "e2e-g11-report-admin@test.com",
    )

    admin_headers = {
        "Authorization": (
            f"Bearer {admin_login['access_token']}"
        ),
    }

    # ================================================================
    # GENERATE REPORT
    # ================================================================

    create_response = client.post(
        "/api/v1/reports",
        json={
            "report_type": ReportType.PATIENTS.value,
            "report_format": ReportFormat.CSV.value,
        },
        headers=admin_headers,
    )

    assert create_response.status_code == 201, (
        create_response.get_json()
    )

    create_body = create_response.get_json()

    assert create_body["success"] is True
    assert create_body["message"] == (
        "Report generated successfully"
    )

    report_data = create_body["data"]

    assert report_data["clinic_id"] == clinic.id
    assert report_data["generated_by_id"] == admin.id
    assert report_data["report_type"] == (
        ReportType.PATIENTS.value
    )
    assert report_data["report_format"] == (
        ReportFormat.CSV.value
    )
    assert report_data["file_url"]

    report_id = report_data["id"]

    # ================================================================
    # DATABASE PERSISTENCE
    # ================================================================

    persisted_report = db.session.get(
        GeneratedReport,
        report_id,
    )

    assert persisted_report is not None
    assert persisted_report.clinic_id == clinic.id
    assert persisted_report.generated_by_id == admin.id
    assert persisted_report.report_type is ReportType.PATIENTS
    assert persisted_report.report_format is ReportFormat.CSV
    assert persisted_report.file_url == report_data["file_url"]

    # ================================================================
    # REAL FILESYSTEM ARTIFACT
    # ================================================================

    report_path = Path(
        persisted_report.file_url
    )

    assert report_path.exists()
    assert report_path.is_file()
    assert report_path.parent == (
        tmp_path / "generated_reports"
    )

    report_bytes = report_path.read_bytes()

    assert report_bytes
    assert b"Gate" in report_bytes
    assert b"Eleven" in report_bytes

    csv_rows = list(
        csv.DictReader(
            io.StringIO(
                report_bytes.decode("utf-8")
            )
        )
    )

    assert any(
        row.get("first_name") == "Gate"
        and row.get("last_name") == "Eleven"
        for row in csv_rows
    )

    # ================================================================
    # AUDIT TRAIL
    # ================================================================

    db.session.flush()

    audit_rows = (
        db.session.execute(
            db.select(AuditLog)
            .where(
                AuditLog.entity_type == "GeneratedReport",
                AuditLog.entity_id == report_id,
            )
            .order_by(
                AuditLog.id.asc(),
            )
        )
        .scalars()
        .all()
    )

    assert len(audit_rows) == 1
    assert audit_rows[0].action is AuditAction.CREATE
    assert audit_rows[0].entity_id == report_id
    assert audit_rows[0].user_id == admin.user.id
    assert audit_rows[0].clinic_id == clinic.id

    # ================================================================
    # SINGLE REPORT RETRIEVAL
    # ================================================================

    get_response = client.get(
        f"/api/v1/reports/{report_id}",
        headers=admin_headers,
    )

    assert get_response.status_code == 200, (
        get_response.get_json()
    )

    get_body = get_response.get_json()

    assert get_body["success"] is True
    assert get_body["data"]["id"] == report_id
    assert get_body["data"]["clinic_id"] == clinic.id
    assert get_body["data"]["file_url"] == (
        persisted_report.file_url
    )

    # ================================================================
    # REPORT LISTING
    # ================================================================

    list_response = client.get(
        "/api/v1/reports?page=1&per_page=20",
        headers=admin_headers,
    )

    assert list_response.status_code == 200, (
        list_response.get_json()
    )

    list_body = list_response.get_json()

    assert list_body["success"] is True
    assert list_body["data"]["total"] >= 1

    listed_ids = {
        item["id"]
        for item in list_body["data"]["items"]
    }

    assert report_id in listed_ids

    # ================================================================
    # SECOND CLINIC
    # ================================================================

    second_clinic = make_clinic(
        name="Gate 11 Reporting Other Clinic",
    )

    second_admin = make_staff(
        clinic=second_clinic,
        role=Role.ADMIN,
        user_overrides={
            "email": "e2e-g11-report-other-admin@test.com",
        },
    )

    second_admin_login = e2e_login(
        "e2e-g11-report-other-admin@test.com",
    )

    second_admin_headers = {
        "Authorization": (
            f"Bearer {second_admin_login['access_token']}"
        ),
    }

    assert second_admin.user.clinic_id == second_clinic.id

    # ================================================================
    # CROSS-CLINIC SINGLE REPORT ACCESS MUST FAIL
    # ================================================================

    foreign_get_response = client.get(
        f"/api/v1/reports/{report_id}",
        headers=second_admin_headers,
    )

    assert foreign_get_response.status_code == 422

    foreign_get_body = foreign_get_response.get_json()

    assert foreign_get_body["success"] is False
    assert foreign_get_body["error"] == (
        "Unauthorized clinic access"
    )

    # ================================================================
    # CROSS-CLINIC LIST MUST NOT EXPOSE THE REPORT
    # ================================================================

    foreign_list_response = client.get(
        "/api/v1/reports?page=1&per_page=20",
        headers=second_admin_headers,
    )

    assert foreign_list_response.status_code == 200

    foreign_list_body = foreign_list_response.get_json()

    assert foreign_list_body["success"] is True

    foreign_ids = {
        item["id"]
        for item in foreign_list_body["data"]["items"]
    }

    assert report_id not in foreign_ids

    print(
        "PHASE8_E2E_GATE11_REPORTING_FILE_STORAGE=PASS"
    )
