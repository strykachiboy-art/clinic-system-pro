from __future__ import annotations

import csv
import io
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.enums.reports_enums import ReportFormat, ReportType
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import (
    DomainError,
    NotFoundError,
    ValidationError,
)
from app.modules.reports.services import reports_service as service


@pytest.fixture(autouse=True)
def app_context(app):
    """Keep direct service calls inside the Flask app context."""
    with app.app_context():
        yield


def _make_report(
    *,
    report_id=1,
    clinic_id=1,
    generated_by_id=1,
    report_type=ReportType.PATIENTS,
    report_format=ReportFormat.CSV,
    filters=None,
    file_url="generated_reports/test.csv",
):
    now = datetime.now(timezone.utc)

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


def _requester(
    *,
    user_id=1,
    clinic_id=10,
    is_active=True,
    staff_id=100,
    staff_status=StaffStatus.ACTIVE,
):
    return SimpleNamespace(
        id=user_id,
        clinic_id=clinic_id,
        is_active=is_active,
        staff=SimpleNamespace(
            id=staff_id,
            clinic_id=clinic_id,
            status=staff_status,
        ),
    )


def _clinic(
    *,
    clinic_id=10,
    is_active=True,
):
    return SimpleNamespace(
        id=clinic_id,
        is_active=is_active,
    )


def _generator(
    *,
    staff_id=100,
    clinic_id=10,
    status=StaffStatus.ACTIVE,
):
    return SimpleNamespace(
        id=staff_id,
        clinic_id=clinic_id,
        status=status,
    )


class TestReportTypeCoercion:
    def test_accepts_enum(self):
        value = service._coerce_report_type(
            ReportType.PATIENTS
        )

        assert value == ReportType.PATIENTS

    def test_accepts_enum_value(self):
        value = service._coerce_report_type(
            ReportType.PATIENTS.value
        )

        assert value == ReportType.PATIENTS

    def test_rejects_invalid_value(self):
        with pytest.raises(ValidationError):
            service._coerce_report_type(
                "not-a-real-report-type"
            )

    def test_rejects_none(self):
        with pytest.raises(ValidationError):
            service._coerce_report_type(None)


class TestReportFormatCoercion:
    def test_accepts_enum(self):
        value = service._coerce_report_format(
            ReportFormat.CSV
        )

        assert value == ReportFormat.CSV

    def test_accepts_enum_value(self):
        value = service._coerce_report_format(
            ReportFormat.CSV.value
        )

        assert value == ReportFormat.CSV

    def test_rejects_invalid_value(self):
        with pytest.raises(ValidationError):
            service._coerce_report_format(
                "invalid-format"
            )

    def test_rejects_none(self):
        with pytest.raises(ValidationError):
            service._coerce_report_format(None)


class TestNormalizeFilters:
    def test_none_becomes_empty_dict(self):
        assert service._normalize_filters(None) == {}

    def test_empty_dict_remains_empty(self):
        assert service._normalize_filters({}) == {}

    @pytest.mark.parametrize(
        "value",
        [
            [],
            (),
            "filters",
            123,
            True,
        ],
    )
    def test_rejects_non_dict(self, value):
        with pytest.raises(ValidationError):
            service._normalize_filters(value)

    def test_rejects_unknown_filter(self):
        with pytest.raises(ValidationError):
            service._normalize_filters(
                {
                    "unknown": "value",
                }
            )

    def test_accepts_active_only_true(self):
        result = service._normalize_filters(
            {
                "active_only": True,
            }
        )

        assert result["active_only"] is True

    def test_accepts_active_only_false(self):
        result = service._normalize_filters(
            {
                "active_only": False,
            }
        )

        assert result["active_only"] is False

    @pytest.mark.parametrize(
        "value",
        [
            "true",
            "false",
            1,
            0,
            None,
            [],
            {},
        ],
    )
    def test_rejects_non_boolean_active_only(self, value):
        with pytest.raises(ValidationError):
            service._normalize_filters(
                {
                    "active_only": value,
                }
            )

    def test_boolean_active_only_values_are_preserved(self):
        for value in (True, False):
            result = service._normalize_filters(
                {
                    "active_only": value,
                }
            )

            assert result["active_only"] is value

    def test_accepts_date_objects(self):
        result = service._normalize_filters(
            {
                "date_from": date(2026, 1, 1),
                "date_to": date(2026, 1, 31),
            }
        )

        assert result["date_from"] == date(2026, 1, 1)
        assert result["date_to"] == date(2026, 1, 31)

    def test_accepts_iso_dates(self):
        result = service._normalize_filters(
            {
                "date_from": "2026-01-01",
                "date_to": "2026-01-31",
            }
        )

        assert result["date_from"] == date(2026, 1, 1)
        assert result["date_to"] == date(2026, 1, 31)

    def test_rejects_invalid_date_from(self):
        with pytest.raises(ValidationError):
            service._normalize_filters(
                {
                    "date_from": "not-a-date",
                }
            )

    def test_rejects_invalid_date_to(self):
        with pytest.raises(ValidationError):
            service._normalize_filters(
                {
                    "date_to": "not-a-date",
                }
            )

    def test_rejects_reversed_date_range(self):
        with pytest.raises(ValidationError):
            service._normalize_filters(
                {
                    "date_from": "2026-02-01",
                    "date_to": "2026-01-01",
                }
            )

    def test_accepts_same_start_and_end_date(self):
        result = service._normalize_filters(
            {
                "date_from": "2026-01-01",
                "date_to": "2026-01-01",
            }
        )

        assert result["date_from"] == date(2026, 1, 1)
        assert result["date_to"] == date(2026, 1, 1)

    def test_normalizes_naive_datetime_values_to_utc(self):
        start = datetime(
            2026,
            1,
            1,
            10,
            30,
        )
        end = datetime(
            2026,
            1,
            2,
            12,
            30,
        )

        result = service._normalize_filters(
            {
                "date_from": start,
                "date_to": end,
            }
        )

        assert result["date_from"] == start.replace(
            tzinfo=timezone.utc
        )

        assert result["date_to"] == end.replace(
            tzinfo=timezone.utc
        )

        assert result["date_from"].tzinfo is timezone.utc
        assert result["date_to"].tzinfo is timezone.utc

    def test_accepts_mixed_date_and_datetime_when_order_is_valid(self):
        end = datetime(
            2026,
            1,
            2,
            12,
            30,
        )

        result = service._normalize_filters(
            {
                "date_from": date(2026, 1, 1),
                "date_to": end,
            }
        )

        assert result["date_from"] == date(2026, 1, 1)

        assert result["date_to"] == end.replace(
            tzinfo=timezone.utc
        )

    def test_normalizes_timezone_aware_datetime(self):
        value = datetime(
            2026,
            1,
            1,
            10,
            30,
            tzinfo=timezone.utc,
        )

        result = service._normalize_filters(
            {
                "date_from": value,
            }
        )

        assert result["date_from"] == value
        assert result["date_from"].tzinfo is timezone.utc

    def test_normalizes_non_utc_aware_datetime(self):
        value = datetime(
            2026,
            1,
            1,
            10,
            30,
            tzinfo=timezone.utc,
        )

        result = service._normalize_filters(
            {
                "date_from": value,
            }
        )

        assert result["date_from"] == value
        assert result["date_from"].tzinfo is timezone.utc


class TestSerializeFilters:
    def test_serializes_empty_filters(self):
        assert service._serialize_filters({}) == {}

    def test_serializes_date_values(self):
        result = service._serialize_filters(
            {
                "date_from": date(2026, 1, 1),
                "date_to": date(2026, 1, 31),
                "active_only": True,
            }
        )

        assert result["date_from"] == "2026-01-01"
        assert result["date_to"] == "2026-01-31"
        assert result["active_only"] is True

    def test_serializes_datetime_values(self):
        value = datetime(
            2026,
            1,
            1,
            10,
            30,
        )

        result = service._serialize_filters(
            {
                "date_from": value,
            }
        )

        assert isinstance(
            result["date_from"],
            str,
        )

        assert result["date_from"].startswith(
            "2026-01-01T10:30"
        )


class TestApplyDatetimeRange:
    class FakeQuery:
        def __init__(self):
            self.filters = []

        def filter(self, *criteria):
            self.filters.extend(criteria)
            return self

        def where(self, *criteria):
            self.filters.extend(criteria)
            return self

    def test_no_dates_returns_original_query(self):
        query = object()
        column = object()

        result = service._apply_datetime_range(
            query=query,
            column=column,
            date_from=None,
            date_to=None,
        )

        assert result is query

    def test_date_from_only_changes_query(self):
        class FakeColumn:
            def __ge__(self, other):
                return ("gte", other)

        query = self.FakeQuery()

        result = service._apply_datetime_range(
            query=query,
            column=FakeColumn(),
            date_from=date(2026, 1, 1),
            date_to=None,
        )

        assert result is query
        assert len(query.filters) == 1
        assert query.filters[0][0] == "gte"

    def test_date_to_only_changes_query(self):
        class FakeColumn:
            def __lt__(self, other):
                return ("lt", other)

            def __le__(self, other):
                return ("lte", other)

        query = self.FakeQuery()

        result = service._apply_datetime_range(
            query=query,
            column=FakeColumn(),
            date_from=None,
            date_to=date(2026, 1, 31),
        )

        assert result is query
        assert len(query.filters) == 1
        assert query.filters[0][0] in {
            "lt",
            "lte",
        }

    def test_both_dates_apply_range(self):
        class FakeColumn:
            def __ge__(self, other):
                return ("gte", other)

            def __lt__(self, other):
                return ("lt", other)

            def __le__(self, other):
                return ("lte", other)

        query = self.FakeQuery()

        result = service._apply_datetime_range(
            query=query,
            column=FakeColumn(),
            date_from=date(2026, 1, 1),
            date_to=date(2026, 1, 31),
        )

        assert result is query
        assert len(query.filters) == 2
        assert query.filters[0][0] == "gte"
        assert query.filters[1][0] in {
            "lt",
            "lte",
        }


class TestGatherers:
    @pytest.mark.parametrize(
        "report_type",
        [
            ReportType.PATIENTS,
            ReportType.STAFF,
            ReportType.APPOINTMENTS,
            ReportType.BILLING,
            ReportType.LAB,
            ReportType.PHARMACY,
            ReportType.WARD,
            ReportType.OVERVIEW,
        ],
    )
    def test_all_supported_types_have_gatherer(
        self,
        report_type,
    ):
        assert report_type in service._GATHERERS

        assert callable(
            service._GATHERERS[report_type]
        )

    def test_inventory_has_no_gatherer(self):
        assert (
            ReportType.INVENTORY
            not in service._GATHERERS
        )


class TestCSVWriter:
    def test_writes_csv_bytes(self):
        rows = [
            {
                "id": 1,
                "name": "Alice",
            },
            {
                "id": 2,
                "name": "Bob",
            },
        ]

        output = service._write_csv(rows)

        assert isinstance(output, bytes)
        assert b"Alice" in output
        assert b"Bob" in output

    def test_empty_rows_produce_bytes(self):
        output = service._write_csv([])

        assert isinstance(output, bytes)
        assert len(output) > 0

    def test_csv_output_is_parseable(self):
        rows = [
            {
                "id": 1,
                "name": "Alice",
            }
        ]

        output = service._write_csv(rows)

        decoded = output.decode("utf-8")

        reader = list(
            csv.DictReader(
                io.StringIO(decoded)
            )
        )

        assert len(reader) == 1
        assert reader[0]["name"] == "Alice"


class TestXLSXWriter:
    def test_writes_xlsx_bytes(self):
        rows = [
            {
                "id": 1,
                "name": "Alice",
            },
            {
                "id": 2,
                "name": "Bob",
            },
        ]

        output = service._write_xlsx(rows)

        assert isinstance(output, bytes)
        assert len(output) > 0
        assert output[:2] == b"PK"

    def test_empty_rows_produce_bytes(self):
        output = service._write_xlsx([])

        assert isinstance(output, bytes)
        assert len(output) > 0
        assert output[:2] == b"PK"


class TestPDFWriter:
    def test_writes_pdf_bytes(self):
        rows = [
            {
                "id": 1,
                "name": "Alice",
            }
        ]

        output = service._write_pdf(rows)

        assert isinstance(output, bytes)
        assert output.startswith(b"%PDF")

    def test_empty_rows_produce_pdf(self):
        output = service._write_pdf([])

        assert isinstance(output, bytes)
        assert output.startswith(b"%PDF")


class TestWriterRegistry:
    @pytest.mark.parametrize(
        "report_format",
        [
            ReportFormat.CSV,
            ReportFormat.XLSX,
            ReportFormat.PDF,
        ],
    )
    def test_writer_registered(
        self,
        report_format,
    ):
        assert report_format in service._WRITERS

        assert callable(
            service._WRITERS[report_format]
        )


class TestSaveReportFile:
    def test_saves_file_and_returns_url(
        self,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)

        data = b"hello report"

        result = service._save_report_file(
            clinic_id=10,
            report_type=ReportType.PATIENTS,
            report_format=ReportFormat.CSV,
            content=data,
        )

        assert result is not None
        assert result.endswith(".csv")

        storage = (
            tmp_path
            / service.DEFAULT_STORAGE_DIR
        )

        assert storage.exists()

        files = list(
            storage.iterdir()
        )

        assert len(files) == 1
        assert files[0].read_bytes() == data

    @pytest.mark.parametrize(
        ("report_format", "extension"),
        [
            (
                ReportFormat.CSV,
                ".csv",
            ),
            (
                ReportFormat.XLSX,
                ".xlsx",
            ),
            (
                ReportFormat.PDF,
                ".pdf",
            ),
        ],
    )
    def test_generated_file_uses_expected_extension(
        self,
        tmp_path,
        monkeypatch,
        report_format,
        extension,
    ):
        monkeypatch.chdir(tmp_path)

        result = service._save_report_file(
            clinic_id=10,
            report_type=ReportType.PATIENTS,
            report_format=report_format,
            content=b"abc",
        )

        assert result.endswith(extension)

    def test_storage_directory_is_created_when_missing(
        self,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)

        storage = (
            tmp_path
            / service.DEFAULT_STORAGE_DIR
        )

        assert not storage.exists()

        service._save_report_file(
            clinic_id=10,
            report_type=ReportType.PATIENTS,
            report_format=ReportFormat.CSV,
            content=b"abc",
        )

        assert storage.exists()
        assert storage.is_dir()


class TestDeleteReportFile:
    def test_delete_existing_file(
        self,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)

        storage = (
            tmp_path
            / service.DEFAULT_STORAGE_DIR
        )

        storage.mkdir()

        target = storage / "report.csv"
        target.write_bytes(b"data")

        service._delete_report_file(
            str(target)
        )

        assert not target.exists()

    def test_delete_missing_file_is_safe(
        self,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)

        missing = (
            tmp_path
            / service.DEFAULT_STORAGE_DIR
            / "missing.csv"
        )

        service._delete_report_file(
            str(missing)
        )

        assert not missing.exists()

    def test_delete_none_is_safe(self):
        service._delete_report_file(None)


class TestAuthorization:
    def test_get_requester_rejects_missing_user(
        self,
        monkeypatch,
    ):
        monkeypatch.setattr(
            service.db.session,
            "get",
            lambda *args, **kwargs: None,
        )

        with pytest.raises(ValidationError):
            service._get_requester(999999)

    def test_get_clinic_rejects_missing_clinic(
        self,
        monkeypatch,
    ):
        monkeypatch.setattr(
            service.db.session,
            "get",
            lambda *args, **kwargs: None,
        )

        with pytest.raises(DomainError):
            service._get_clinic(999999)

    def test_get_requester_rejects_non_positive_id(self):
        with pytest.raises(ValidationError):
            service._get_requester(0)

    def test_get_requester_rejects_negative_id(self):
        with pytest.raises(ValidationError):
            service._get_requester(-1)

    def test_get_requester_rejects_boolean_id(self):
        with pytest.raises(ValidationError):
            service._get_requester(True)

    def test_get_clinic_rejects_non_positive_id(self):
        with pytest.raises(DomainError):
            service._get_clinic(0)

    def test_get_clinic_rejects_negative_id(self):
        with pytest.raises(DomainError):
            service._get_clinic(-1)

    @pytest.mark.parametrize(
        "clinic_id",
        [
            0,
            -1,
        ],
    )
    def test_list_reports_rejects_invalid_clinic_id(
        self,
        clinic_id,
    ):
        with pytest.raises(ValidationError):
            service.list_reports(
                requester_user_id=1,
                clinic_id=clinic_id,
            )

    @pytest.mark.parametrize(
        "requester_user_id",
        [
            0,
            -1,
        ],
    )
    def test_list_reports_rejects_invalid_requester_id(
        self,
        requester_user_id,
    ):
        with pytest.raises(ValidationError):
            service.list_reports(
                requester_user_id=requester_user_id,
                clinic_id=1,
            )


class TestGetReport:
    def test_rejects_non_positive_report_id(self):
        with pytest.raises(ValidationError):
            service.get_report(
                report_id=0,
                requester_user_id=1,
            )

    def test_rejects_negative_report_id(self):
        with pytest.raises(ValidationError):
            service.get_report(
                report_id=-1,
                requester_user_id=1,
            )

    def test_rejects_boolean_report_id(self):
        with pytest.raises(ValidationError):
            service.get_report(
                report_id=True,
                requester_user_id=1,
            )

    def test_rejects_invalid_requester_id(self):
        with pytest.raises(ValidationError):
            service.get_report(
                report_id=1,
                requester_user_id=0,
            )

    def test_rejects_negative_requester_id(self):
        with pytest.raises(ValidationError):
            service.get_report(
                report_id=1,
                requester_user_id=-1,
            )

    def test_rejects_boolean_requester_id(self):
        with pytest.raises(ValidationError):
            service.get_report(
                report_id=1,
                requester_user_id=True,
            )

    def test_missing_report_raises_not_found_error(
        self,
        monkeypatch,
    ):
        requester = _requester()

        def fake_get(model, object_id):
            if (
                model is service.User
                and object_id == requester.id
            ):
                return requester

            return None

        monkeypatch.setattr(
            service.db.session,
            "get",
            fake_get,
        )

        with pytest.raises(NotFoundError):
            service.get_report(
                report_id=1,
                requester_user_id=requester.id,
            )

    def test_returns_report_for_authorized_user(
        self,
        monkeypatch,
    ):
        requester = _requester(
            user_id=1,
            clinic_id=10,
            staff_id=100,
        )

        report = _make_report(
            report_id=1,
            clinic_id=10,
            generated_by_id=1,
        )

        def fake_get(model, object_id):
            if (
                model is service.User
                and object_id == requester.id
            ):
                return requester

            if (
                model is service.GeneratedReport
                and object_id == report.id
            ):
                return report

            return None

        monkeypatch.setattr(
            service.db.session,
            "get",
            fake_get,
        )

        result = service.get_report(
            report_id=report.id,
            requester_user_id=requester.id,
        )

        assert result is report

    def test_rejects_cross_clinic_report(
        self,
        monkeypatch,
    ):
        requester = _requester(
            user_id=1,
            clinic_id=10,
        )

        report = _make_report(
            report_id=1,
            clinic_id=20,
        )

        def fake_get(model, object_id):
            if (
                model is service.User
                and object_id == requester.id
            ):
                return requester

            if (
                model is service.GeneratedReport
                and object_id == report.id
            ):
                return report

            return None

        monkeypatch.setattr(
            service.db.session,
            "get",
            fake_get,
        )

        with pytest.raises(DomainError):
            service.get_report(
                report_id=report.id,
                requester_user_id=requester.id,
            )


class TestListReportsValidation:
    def test_rejects_invalid_page(self):
        with pytest.raises(ValidationError):
            service.list_reports(
                requester_user_id=1,
                clinic_id=1,
                page=0,
                per_page=20,
            )

    def test_rejects_negative_page(self):
        with pytest.raises(ValidationError):
            service.list_reports(
                requester_user_id=1,
                clinic_id=1,
                page=-1,
                per_page=20,
            )

    def test_rejects_boolean_page(self):
        with pytest.raises(ValidationError):
            service.list_reports(
                requester_user_id=1,
                clinic_id=1,
                page=True,
                per_page=20,
            )

    def test_rejects_invalid_per_page(self):
        with pytest.raises(ValidationError):
            service.list_reports(
                requester_user_id=1,
                clinic_id=1,
                page=1,
                per_page=0,
            )

    def test_rejects_excessive_per_page(self):
        with pytest.raises(ValidationError):
            service.list_reports(
                requester_user_id=1,
                clinic_id=1,
                page=1,
                per_page=101,
            )

    def test_rejects_boolean_per_page(self):
        with pytest.raises(ValidationError):
            service.list_reports(
                requester_user_id=1,
                clinic_id=1,
                page=1,
                per_page=True,
            )

    def test_rejects_invalid_requester(self):
        with pytest.raises(ValidationError):
            service.list_reports(
                requester_user_id=0,
                clinic_id=1,
            )

    def test_rejects_invalid_clinic(self):
        with pytest.raises(ValidationError):
            service.list_reports(
                requester_user_id=1,
                clinic_id=0,
            )

    def test_rejects_negative_clinic(self):
        with pytest.raises(ValidationError):
            service.list_reports(
                requester_user_id=1,
                clinic_id=-1,
            )

    def test_rejects_reversed_dates(self):
        with pytest.raises(ValidationError):
            service.list_reports(
                requester_user_id=1,
                clinic_id=1,
                date_from=date(
                    2026,
                    2,
                    1,
                ),
                date_to=date(
                    2026,
                    1,
                    1,
                ),
            )

    def test_rejects_invalid_generated_by_id(self):
        with pytest.raises(ValidationError):
            service.list_reports(
                requester_user_id=1,
                clinic_id=1,
                generated_by_id=0,
            )

    def test_rejects_negative_generated_by_id(self):
        with pytest.raises(ValidationError):
            service.list_reports(
                requester_user_id=1,
                clinic_id=1,
                generated_by_id=-1,
            )

    def test_rejects_boolean_generated_by_id(self):
        with pytest.raises(ValidationError):
            service.list_reports(
                requester_user_id=1,
                clinic_id=1,
                generated_by_id=True,
            )

    def test_rejects_invalid_report_type(self):
        with pytest.raises(ValidationError):
            service.list_reports(
                requester_user_id=1,
                clinic_id=1,
                report_type="invalid",
            )

    def test_rejects_invalid_report_format(self):
        with pytest.raises(ValidationError):
            service.list_reports(
                requester_user_id=1,
                clinic_id=1,
                report_format="invalid",
            )

    def test_accepts_enum_report_type_when_requester_is_valid(
        self,
        monkeypatch,
    ):
        requester = _requester(
            user_id=1,
            clinic_id=10,
        )

        monkeypatch.setattr(
            service,
            "_get_requester",
            lambda user_id: requester,
        )

        monkeypatch.setattr(
            service,
            "_resolve_clinic_scope",
            lambda *args, **kwargs: 10,
        )

        assert service._coerce_report_type(
            ReportType.PATIENTS
        ) == ReportType.PATIENTS


class TestGenerateReportValidation:
    @pytest.mark.parametrize(
        "requester_user_id",
        [
            0,
            -1,
        ],
    )
    def test_rejects_invalid_requester_id(
        self,
        requester_user_id,
    ):
        with pytest.raises(ValidationError):
            service.generate_report(
                requester_user_id=requester_user_id,
                clinic_id=1,
                report_type=ReportType.PATIENTS,
                report_format=ReportFormat.CSV,
            )

    def test_rejects_boolean_requester_id(self):
        with pytest.raises(ValidationError):
            service.generate_report(
                requester_user_id=True,
                clinic_id=1,
                report_type=ReportType.PATIENTS,
                report_format=ReportFormat.CSV,
            )

    @pytest.mark.parametrize(
        "clinic_id",
        [
            0,
            -1,
        ],
    )
    def test_rejects_invalid_clinic_id(
        self,
        clinic_id,
    ):
        with pytest.raises(ValidationError):
            service.generate_report(
                requester_user_id=1,
                clinic_id=clinic_id,
                report_type=ReportType.PATIENTS,
                report_format=ReportFormat.CSV,
            )

    def test_rejects_boolean_clinic_id(self):
        with pytest.raises(ValidationError):
            service.generate_report(
                requester_user_id=1,
                clinic_id=True,
                report_type=ReportType.PATIENTS,
                report_format=ReportFormat.CSV,
            )

    def test_rejects_invalid_report_type(self):
        with pytest.raises(ValidationError):
            service.generate_report(
                requester_user_id=1,
                clinic_id=1,
                report_type="invalid",
                report_format=ReportFormat.CSV,
            )

    def test_rejects_invalid_report_format(self):
        with pytest.raises(ValidationError):
            service.generate_report(
                requester_user_id=1,
                clinic_id=1,
                report_type=ReportType.PATIENTS,
                report_format="invalid",
            )

    def test_inventory_is_explicitly_unsupported(
        self,
        monkeypatch,
    ):
        requester = _requester(
            user_id=1,
            clinic_id=10,
        )

        clinic = _clinic(
            clinic_id=10,
            is_active=True,
        )

        monkeypatch.setattr(
            service,
            "_get_requester",
            lambda user_id: requester,
        )

        monkeypatch.setattr(
            service,
            "_get_clinic",
            lambda clinic_id: clinic,
        )

        with pytest.raises(
            (
                ValidationError,
                DomainError,
            )
        ):
            service.generate_report(
                requester_user_id=1,
                clinic_id=10,
                report_type=ReportType.INVENTORY,
                report_format=ReportFormat.CSV,
            )


class TestGenerateReportOrchestration:
    def _patch_common(
        self,
        monkeypatch,
        *,
        requester=None,
        clinic=None,
        generator=None,
    ):
        requester = requester or _requester()
        clinic = clinic or _clinic()

        generator = generator or _generator(
            staff_id=requester.staff.id,
            clinic_id=clinic.id,
        )

        monkeypatch.setattr(
            service,
            "_get_requester",
            lambda requester_user_id: requester,
        )

        monkeypatch.setattr(
            service,
            "_get_clinic",
            lambda clinic_id: clinic,
        )

        monkeypatch.setattr(
            service,
            "_validate_report_generator",
            lambda requester, clinic_id: generator,
        )

        monkeypatch.setattr(
            service,
            "_require_active_clinic",
            lambda clinic_id: None,
        )

        monkeypatch.setattr(
            service,
            "_delete_report_file",
            lambda *args, **kwargs: None,
        )

        monkeypatch.setattr(
            service,
            "create_audit_log",
            lambda *args, **kwargs: None,
        )

        monkeypatch.setattr(
            service.db.session,
            "add",
            lambda obj: None,
        )

        monkeypatch.setattr(
            service.db.session,
            "flush",
            lambda: None,
        )

        return requester, clinic, generator

    def test_successful_generation(
        self,
        monkeypatch,
    ):
        requester, clinic, generator = (
            self._patch_common(
                monkeypatch
            )
        )

        monkeypatch.setattr(
            service,
            "_gather_patients",
            lambda *args, **kwargs: [
                {
                    "id": 1,
                    "name": "Alice",
                }
            ],
        )

        monkeypatch.setattr(
            service,
            "_save_report_file",
            lambda *args, **kwargs:
                "generated_reports/test.csv",
        )

        monkeypatch.setattr(
            service,
            "GeneratedReport",
            lambda **kwargs: SimpleNamespace(
                id=99,
                clinic_id=kwargs["clinic_id"],
                generated_by_id=kwargs[
                    "generated_by_id"
                ],
                report_type=kwargs[
                    "report_type"
                ],
                report_format=kwargs[
                    "report_format"
                ],
                filters=kwargs["filters"],
                file_url=kwargs["file_url"],
            ),
        )

        result = service.generate_report(
            requester_user_id=requester.id,
            clinic_id=clinic.id,
            report_type=ReportType.PATIENTS,
            report_format=ReportFormat.CSV,
            filters={
                "active_only": True,
            },
        )

        assert result is not None
        assert result.clinic_id == clinic.id
        assert result.generated_by_id == generator.id
        assert result.report_type == ReportType.PATIENTS
        assert result.report_format == ReportFormat.CSV
        assert result.filters["active_only"] is True
        assert result.file_url.endswith(".csv")

    def test_generation_normalizes_filters(
        self,
        monkeypatch,
    ):
        requester, clinic, generator = (
            self._patch_common(
                monkeypatch
            )
        )

        captured = {}

        monkeypatch.setattr(
            service,
            "_gather_patients",
            lambda *args, **kwargs: [],
        )

        monkeypatch.setattr(
            service,
            "_save_report_file",
            lambda *args, **kwargs:
                "generated_reports/test.csv",
        )

        def fake_report(**kwargs):
            captured.update(kwargs)

            return SimpleNamespace(
                id=99,
                **kwargs,
            )

        monkeypatch.setattr(
            service,
            "GeneratedReport",
            fake_report,
        )

        service.generate_report(
            requester_user_id=requester.id,
            clinic_id=clinic.id,
            report_type=ReportType.PATIENTS,
            report_format=ReportFormat.CSV,
            filters={
                "date_from": "2026-01-01",
                "date_to": "2026-01-31",
                "active_only": True,
            },
        )

        assert captured["filters"]["active_only"] is True
        assert captured["filters"]["date_from"] == "2026-01-01"
        assert captured["filters"]["date_to"] == "2026-01-31"
        assert captured["generated_by_id"] == generator.id

    def test_generation_rejects_invalid_filters(
        self,
        monkeypatch,
    ):
        requester, clinic, _ = (
            self._patch_common(
                monkeypatch
            )
        )

        with pytest.raises(ValidationError):
            service.generate_report(
                requester_user_id=requester.id,
                clinic_id=clinic.id,
                report_type=ReportType.PATIENTS,
                report_format=ReportFormat.CSV,
                filters={
                    "active_only": "yes",
                },
            )

    def test_generation_rejects_unknown_filter(
        self,
        monkeypatch,
    ):
        requester, clinic, _ = (
            self._patch_common(
                monkeypatch
            )
        )

        with pytest.raises(ValidationError):
            service.generate_report(
                requester_user_id=requester.id,
                clinic_id=clinic.id,
                report_type=ReportType.PATIENTS,
                report_format=ReportFormat.CSV,
                filters={
                    "unexpected": True,
                },
            )

    def test_generation_rejects_reversed_filters(
        self,
        monkeypatch,
    ):
        requester, clinic, _ = (
            self._patch_common(
                monkeypatch
            )
        )

        with pytest.raises(ValidationError):
            service.generate_report(
                requester_user_id=requester.id,
                clinic_id=clinic.id,
                report_type=ReportType.PATIENTS,
                report_format=ReportFormat.CSV,
                filters={
                    "date_from": "2026-02-01",
                    "date_to": "2026-01-01",
                },
            )

    def test_generation_uses_registered_gatherer(
        self,
        monkeypatch,
    ):
        requester, clinic, _ = (
            self._patch_common(
                monkeypatch
            )
        )

        called = {
            "value": False,
        }

        def fake_gather(*args, **kwargs):
            called["value"] = True
            return []

        monkeypatch.setitem(
            service._GATHERERS,
            ReportType.PATIENTS,
            fake_gather,
        )

        monkeypatch.setattr(
            service,
            "_save_report_file",
            lambda *args, **kwargs:
                "generated_reports/test.csv",
        )

        monkeypatch.setattr(
            service,
            "GeneratedReport",
            lambda **kwargs: SimpleNamespace(
                id=99,
                **kwargs,
            ),
        )

        service.generate_report(
            requester_user_id=requester.id,
            clinic_id=clinic.id,
            report_type=ReportType.PATIENTS,
            report_format=ReportFormat.CSV,
        )

        assert called["value"] is True

    def test_generation_passes_normalized_filters_to_gatherer(
        self,
        monkeypatch,
    ):
        requester, clinic, _ = (
            self._patch_common(
                monkeypatch
            )
        )

        captured = {}

        def fake_gather(*args, **kwargs):
            captured["clinic_id"] = args[0]
            captured["filters"] = args[1]
            captured["kwargs"] = kwargs
            return []

        monkeypatch.setitem(
            service._GATHERERS,
            ReportType.PATIENTS,
            fake_gather,
        )

        monkeypatch.setattr(
            service,
            "_save_report_file",
            lambda *args, **kwargs:
                "generated_reports/test.csv",
        )

        monkeypatch.setattr(
            service,
            "GeneratedReport",
            lambda **kwargs: SimpleNamespace(
                id=99,
                **kwargs,
            ),
        )

        service.generate_report(
            requester_user_id=requester.id,
            clinic_id=clinic.id,
            report_type=ReportType.PATIENTS,
            report_format=ReportFormat.CSV,
            filters={
                "active_only": False,
                "date_from": "2026-01-01",
                "date_to": "2026-01-31",
            },
        )

        assert captured
        assert captured["clinic_id"] == clinic.id
        assert captured["filters"]["active_only"] is False
        assert (
            captured["filters"]["date_from"]
            == date(2026, 1, 1)
        )
        assert (
            captured["filters"]["date_to"]
            == date(2026, 1, 31)
        )
        assert captured["kwargs"] == {}


SUPPORTED_REPORT_TYPES = [
    ReportType.OVERVIEW,
    ReportType.PATIENTS,
    ReportType.STAFF,
    ReportType.APPOINTMENTS,
    ReportType.BILLING,
    ReportType.LAB,
    ReportType.PHARMACY,
    ReportType.WARD,
]


class TestFormatCompatibility:
    @pytest.mark.parametrize(
        "report_type",
        SUPPORTED_REPORT_TYPES,
    )
    def test_supported_types_are_csv_compatible(
        self,
        report_type,
    ):
        assert (
            report_type
            in service.SUPPORTED_CSV_TYPES
        )

    @pytest.mark.parametrize(
        "report_type",
        SUPPORTED_REPORT_TYPES,
    )
    def test_supported_types_are_xlsx_compatible(
        self,
        report_type,
    ):
        assert (
            report_type
            in service.SUPPORTED_XLSX_TYPES
        )

    @pytest.mark.parametrize(
        "report_type",
        SUPPORTED_REPORT_TYPES,
    )
    def test_supported_types_are_pdf_compatible(
        self,
        report_type,
    ):
        assert (
            report_type
            in service.SUPPORTED_PDF_TYPES
        )

    def test_inventory_is_marked_unsupported(self):
        assert (
            ReportType.INVENTORY
            in service.UNSUPPORTED_TYPES
        )


class TestValueHelpers:
    def test_decimal_value_preserves_decimal_precision(self):
        result = service._decimal_value(
            Decimal("123.45")
        )

        assert isinstance(
            result,
            Decimal,
        )

        assert result == Decimal(
            "123.45"
        )

    @pytest.mark.parametrize(
        "value",
        [
            "123.45",
            123,
            123.45,
        ],
    )
    def test_decimal_value_converts_numeric_values_to_decimal(
        self,
        value,
    ):
        result = service._decimal_value(
            value
        )

        assert isinstance(
            result,
            Decimal,
        )

    def test_decimal_value_none_returns_zero(self):
        result = service._decimal_value(None)

        assert isinstance(
            result,
            Decimal,
        )

        assert result == Decimal("0")

    def test_iso_date(self):
        result = service._iso(
            date(2026, 1, 1)
        )

        assert result == "2026-01-01"

    def test_iso_datetime(self):
        value = datetime(
            2026,
            1,
            1,
            12,
            30,
        )

        result = service._iso(value)

        assert isinstance(
            result,
            str,
        )

        assert result.startswith(
            "2026-01-01T12:30"
        )

    def test_iso_none(self):
        result = service._iso(None)

        assert result is None

    def test_enum_value_helper(self):
        result = service._enum_value(
            ReportType.PATIENTS
        )

        assert (
            result
            == ReportType.PATIENTS.value
        )

    def test_enum_value_plain_value(self):
        assert (
            service._enum_value(
                "patients"
            )
            == "patients"
        )


class TestRegistryIntegrity:
    def test_all_csv_types_have_gatherers(self):
        for report_type in (
            service.SUPPORTED_CSV_TYPES
        ):
            assert (
                report_type
                in service._GATHERERS
            )

            assert callable(
                service._GATHERERS[
                    report_type
                ]
            )

    def test_all_xlsx_types_have_gatherers(self):
        for report_type in (
            service.SUPPORTED_XLSX_TYPES
        ):
            assert (
                report_type
                in service._GATHERERS
            )

            assert callable(
                service._GATHERERS[
                    report_type
                ]
            )

    def test_all_pdf_types_have_gatherers(self):
        for report_type in (
            service.SUPPORTED_PDF_TYPES
        ):
            assert (
                report_type
                in service._GATHERERS
            )

            assert callable(
                service._GATHERERS[
                    report_type
                ]
            )

    def test_all_formats_have_writers(self):
        for report_format in (
            ReportFormat.CSV,
            ReportFormat.XLSX,
            ReportFormat.PDF,
        ):
            assert (
                report_format
                in service._WRITERS
            )

            assert callable(
                service._WRITERS[
                    report_format
                ]
            )

    def test_unsupported_types_are_not_registered(self):
        for report_type in (
            service.UNSUPPORTED_TYPES
        ):
            assert (
                report_type
                not in service._GATHERERS
            )


class TestStorageSafety:
    def test_failed_atomic_replace_cleans_temp_file(
        self,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)

        def fail_replace(*args, **kwargs):
            raise OSError(
                "replace failed"
            )

        monkeypatch.setattr(
            service.os,
            "replace",
            fail_replace,
        )

        with pytest.raises(OSError):
            service._save_report_file(
                clinic_id=10,
                report_type=ReportType.PATIENTS,
                report_format=ReportFormat.CSV,
                content=b"test",
            )

        storage = (
            tmp_path
            / service.DEFAULT_STORAGE_DIR
        )

        assert storage.exists()

        leftovers = list(
            storage.iterdir()
        )

        assert leftovers == []

    def test_successful_save_does_not_leave_tmp_files(
        self,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)

        service._save_report_file(
            clinic_id=10,
            report_type=ReportType.PATIENTS,
            report_format=ReportFormat.CSV,
            content=b"test",
        )

        storage = (
            tmp_path
            / service.DEFAULT_STORAGE_DIR
        )

        assert storage.exists()

        files = list(
            storage.iterdir()
        )

        assert len(files) == 1
        assert files[0].suffix == ".csv"

        assert not any(
            path.name.endswith(".tmp")
            for path in files
        )


class TestDateSemantics:
    def test_date_from_is_preserved_as_date(self):
        value = service._normalize_filters(
            {
                "date_from": "2026-01-01",
            }
        )

        assert (
            value["date_from"]
            == date(2026, 1, 1)
        )

    def test_date_to_is_preserved_as_inclusive_date(self):
        value = service._normalize_filters(
            {
                "date_to": "2026-01-31",
            }
        )

        assert (
            value["date_to"]
            == date(2026, 1, 31)
        )

    def test_same_day_range_is_valid(self):
        result = service._normalize_filters(
            {
                "date_from": date(
                    2026,
                    1,
                    1,
                ),
                "date_to": date(
                    2026,
                    1,
                    1,
                ),
            }
        )

        assert (
            result["date_from"]
            == result["date_to"]
        )

    def test_one_sided_date_from_is_valid(self):
        result = service._normalize_filters(
            {
                "date_from": date(
                    2026,
                    1,
                    1,
                ),
            }
        )

        assert (
            result["date_from"]
            == date(2026, 1, 1)
        )

        assert (
            "date_to"
            not in result
        )

    def test_one_sided_date_to_is_valid(self):
        result = service._normalize_filters(
            {
                "date_to": date(
                    2026,
                    1,
                    31,
                ),
            }
        )

        assert (
            result["date_to"]
            == date(2026, 1, 31)
        )

        assert (
            "date_from"
            not in result
        )


class TestRouteServiceContract:
    def test_filter_schema_values_are_service_compatible(self):
        filters = {
            "date_from": date(
                2026,
                1,
                1,
            ),
            "date_to": date(
                2026,
                1,
                31,
            ),
            "active_only": True,
        }

        result = service._normalize_filters(
            filters
        )

        assert result == filters

    def test_serialized_filter_payload_is_json_safe(self):
        filters = {
            "date_from": date(
                2026,
                1,
                1,
            ),
            "date_to": date(
                2026,
                1,
                31,
            ),
            "active_only": True,
        }

        result = service._serialize_filters(
            filters
        )

        assert result == {
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "active_only": True,
        }


class TestStorageConfiguration:
    def test_default_storage_directory_is_defined(self):
        assert service.DEFAULT_STORAGE_DIR

        assert isinstance(
            service.DEFAULT_STORAGE_DIR,
            str,
        )

    def test_default_storage_directory_is_relative(self):
        assert not os.path.isabs(
            service.DEFAULT_STORAGE_DIR
        )

    def test_storage_directory_resolver_returns_absolute_path(
        self,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)

        storage = Path(
            service._get_storage_directory()
        )

        assert storage.is_absolute()

        assert storage == (
            tmp_path
            / service.DEFAULT_STORAGE_DIR
        )


class TestPaginationContract:
    def test_default_page_is_expected(self):
        assert service.DEFAULT_PAGE == 1

    def test_default_per_page_is_expected(self):
        assert service.DEFAULT_PER_PAGE == 20

    def test_max_per_page_is_expected(self):
        assert service.MAX_PER_PAGE == 100

    @pytest.mark.parametrize(
        ("page", "per_page"),
        [
            (1, 1),
            (1, 20),
            (1, 100),
            (2, 50),
            (10, 100),
        ],
    )
    def test_valid_pagination_values(
        self,
        page,
        per_page,
    ):
        assert service._validate_pagination(
            page,
            per_page,
        ) == (
            page,
            per_page,
        )

    @pytest.mark.parametrize(
        ("page", "per_page"),
        [
            (0, 20),
            (-1, 20),
            (1, 0),
            (1, -1),
            (1, 101),
        ],
    )
    def test_invalid_pagination_values(
        self,
        page,
        per_page,
    ):
        with pytest.raises(ValidationError):
            service._validate_pagination(
                page,
                per_page,
            )

    def test_boolean_page_is_rejected(self):
        with pytest.raises(ValidationError):
            service._validate_pagination(
                True,
                20,
            )

    def test_boolean_per_page_is_rejected(self):
        with pytest.raises(ValidationError):
            service._validate_pagination(
                1,
                True,
            )


def test_supported_report_types_are_not_empty():
    assert service.SUPPORTED_CSV_TYPES
    assert service.SUPPORTED_XLSX_TYPES
    assert service.SUPPORTED_PDF_TYPES


def test_supported_type_sets_are_consistent():
    assert (
        service.SUPPORTED_CSV_TYPES
        == service.SUPPORTED_XLSX_TYPES
    )

    assert (
        service.SUPPORTED_CSV_TYPES
        == service.SUPPORTED_PDF_TYPES
    )


def test_unsupported_inventory_is_explicit():
    assert (
        ReportType.INVENTORY
        in service.UNSUPPORTED_TYPES
    )

    assert (
        ReportType.INVENTORY
        not in service._GATHERERS
    )