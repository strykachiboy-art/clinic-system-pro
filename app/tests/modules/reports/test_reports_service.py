from datetime import date

import pytest

from app.core.enums.reports_enums import ReportFormat, ReportType
from app.core.enums.role_enums import Role
from app.core.exceptions import NotFoundError, ValidationError
from app.modules.reports.services import reports_service as svc


class TestScopeResolution:
    def test_generate_report_requires_staff_linked_to_a_user(self, db, clinic, make_staff):
        # make_staff always links a user, so this exercises the "no
        # matching staff row for this user_id" branch via a bogus id.
        with pytest.raises(ValidationError):
            svc.generate_report(
                report_type=ReportType.PATIENTS,
                report_format=ReportFormat.CSV,
                clinic_id=clinic.id,
                requester_user_id=999999,
            )

    def test_non_admin_cannot_generate_for_other_clinic(self, db, clinic, make_clinic, make_staff):
        staff = make_staff(clinic, role=Role.DOCTOR)
        other_clinic = make_clinic(name="Other")

        with pytest.raises(ValidationError):
            svc.generate_report(
                report_type=ReportType.PATIENTS,
                report_format=ReportFormat.CSV,
                clinic_id=other_clinic.id,
                requester_user_id=staff.user_id,
            )

    def test_admin_can_generate_for_any_clinic(self, db, clinic, make_staff):
        admin = make_staff(clinic, role=Role.ADMIN)

        report = svc.generate_report(
            report_type=ReportType.PATIENTS,
            report_format=ReportFormat.CSV,
            clinic_id=clinic.id,
            requester_user_id=admin.user_id,
        )
        assert report.clinic_id == clinic.id


class TestReportGeneration:
    def test_generate_patients_csv_report(self, db, clinic, make_staff, make_patient):
        staff = make_staff(clinic, role=Role.RECEPTIONIST)
        make_patient(clinic, first_name="Alice")
        make_patient(clinic, first_name="Bob")

        report = svc.generate_report(
            report_type=ReportType.PATIENTS,
            report_format=ReportFormat.CSV,
            clinic_id=clinic.id,
            requester_user_id=staff.user_id,
        )

        assert report.report_type == ReportType.PATIENTS
        assert report.file_url is not None
        assert report.filters == {}

        with open(report.file_url, "rb") as f:
            content = f.read().decode("utf-8")
        assert "Alice" in content
        assert "Bob" in content

    def test_generate_report_rejects_unsupported_type(self, db, clinic, make_staff):
        staff = make_staff(clinic, role=Role.ADMIN)

        # ReportType.INVENTORY is explicitly in _UNSUPPORTED_TYPES
        with pytest.raises(ValidationError):
            svc.generate_report(
                report_type=ReportType.INVENTORY,
                report_format=ReportFormat.CSV,
                clinic_id=clinic.id,
                requester_user_id=staff.user_id,
            )

    def test_generate_report_rejects_pdf_format(self, db, clinic, make_staff):
        staff = make_staff(clinic, role=Role.ADMIN)

        # PDF writer is a stub that always raises; the service also
        # short-circuits on PDF before even calling the gatherer.
        with pytest.raises(ValidationError):
            svc.generate_report(
                report_type=ReportType.PATIENTS,
                report_format=ReportFormat.PDF,
                clinic_id=clinic.id,
                requester_user_id=staff.user_id,
            )

    def test_generate_report_normalizes_date_filters(self, db, clinic, make_staff, make_patient):
        staff = make_staff(clinic, role=Role.ADMIN)
        make_patient(clinic)

        report = svc.generate_report(
            report_type=ReportType.PATIENTS,
            report_format=ReportFormat.CSV,
            clinic_id=clinic.id,
            requester_user_id=staff.user_id,
            filters={"date_from": "2020-01-01", "active_only": True},
        )

        assert report.filters["date_from"] == "2020-01-01"

    def test_generate_report_rejects_invalid_date_filter(self, db, clinic, make_staff):
        staff = make_staff(clinic, role=Role.ADMIN)

        with pytest.raises(ValidationError):
            svc.generate_report(
                report_type=ReportType.PATIENTS,
                report_format=ReportFormat.CSV,
                clinic_id=clinic.id,
                requester_user_id=staff.user_id,
                filters={"date_from": "not-a-date"},
            )

    def test_generate_overview_report_aggregates_counts(self, db, clinic, make_staff, make_patient):
        staff = make_staff(clinic, role=Role.ADMIN)
        make_patient(clinic)
        make_patient(clinic)

        report = svc.generate_report(
            report_type=ReportType.OVERVIEW,
            report_format=ReportFormat.CSV,
            clinic_id=clinic.id,
            requester_user_id=staff.user_id,
        )

        with open(report.file_url, "rb") as f:
            content = f.read().decode("utf-8")
        # Overview is a single aggregate row with a "patients" column.
        assert "patients" in content


class TestReportRetrieval:
    def test_get_report_not_found(self, db, clinic, make_staff):
        staff = make_staff(clinic, role=Role.ADMIN)

        with pytest.raises(NotFoundError):
            svc.get_report(report_id=999999, requester_user_id=staff.user_id)

    def test_get_report_rejects_cross_clinic_access_for_non_admin(
        self, db, clinic, make_clinic, make_staff, make_patient
    ):
        admin = make_staff(clinic, role=Role.ADMIN)
        report = svc.generate_report(
            report_type=ReportType.PATIENTS,
            report_format=ReportFormat.CSV,
            clinic_id=clinic.id,
            requester_user_id=admin.user_id,
        )

        other_clinic = make_clinic(name="Other")
        outsider = make_staff(other_clinic, role=Role.RECEPTIONIST)

        with pytest.raises(ValidationError):
            svc.get_report(report_id=report.id, requester_user_id=outsider.user_id)

    def test_list_reports_scoped_to_own_clinic_for_non_admin(self, db, clinic, make_clinic, make_staff):
        admin = make_staff(clinic, role=Role.ADMIN)
        svc.generate_report(
            report_type=ReportType.PATIENTS, report_format=ReportFormat.CSV,
            clinic_id=clinic.id, requester_user_id=admin.user_id,
        )

        other_clinic = make_clinic(name="Other")
        other_admin = make_staff(other_clinic, role=Role.ADMIN)
        svc.generate_report(
            report_type=ReportType.PATIENTS, report_format=ReportFormat.CSV,
            clinic_id=other_clinic.id, requester_user_id=other_admin.user_id,
        )

        receptionist = make_staff(clinic, role=Role.RECEPTIONIST)
        result = svc.list_reports(requester_user_id=receptionist.user_id)

        assert result["total"] == 1
        assert result["items"][0].clinic_id == clinic.id

    def test_list_reports_pagination(self, db, clinic, make_staff):
        admin = make_staff(clinic, role=Role.ADMIN)
        for _ in range(3):
            svc.generate_report(
                report_type=ReportType.PATIENTS, report_format=ReportFormat.CSV,
                clinic_id=clinic.id, requester_user_id=admin.user_id,
            )

        page1 = svc.list_reports(requester_user_id=admin.user_id, page=1, per_page=2)
        assert len(page1["items"]) == 2
        assert page1["total"] == 3