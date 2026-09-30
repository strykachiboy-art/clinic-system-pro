# load_tests/resilience/tests/runners/test_resilience_report.py

from __future__ import annotations

import json

import pytest

from load_tests.resilience.runners import (
    resilience_report,
)


def _sample_result():
    return {
        "run_id": "report-001",
        "started_at": (
            "2026-09-23T15:00:00+00:00"
        ),
        "summary": {
            "total": 3,
            "passed": 2,
            "failed": 1,
            "skipped": 0,
        },
        "cases": [
            {
                "name": "http::test_one",
                "status": "passed",
                "duration_ms": 10.5,
                "message": None,
                "details": {},
            },
            {
                "name": "chat::test_two",
                "status": "passed",
                "duration_ms": 15.25,
                "message": None,
                "details": {},
            },
            {
                "name": "redis::test_three",
                "status": "failed",
                "duration_ms": 20.0,
                "message": "Synthetic failure",
                "details": {},
            },
        ],
    }


def test_load_result_reads_valid_json(
    tmp_path,
):
    path = (
        tmp_path
        / "result.json"
    )

    path.write_text(
        json.dumps(
            _sample_result()
        ),
        encoding="utf-8",
    )

    result = (
        resilience_report.load_result(
            path
        )
    )

    assert result["run_id"] == (
        "report-001"
    )


def test_load_result_rejects_missing_file(
    tmp_path,
):
    with pytest.raises(
        FileNotFoundError,
        match="Resilience result not found",
    ):
        resilience_report.load_result(
            tmp_path
            / "missing.json"
        )


def test_load_result_rejects_invalid_structure(
    tmp_path,
):
    path = (
        tmp_path
        / "invalid.json"
    )

    path.write_text(
        '{"run_id": "only-run-id"}',
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=(
            "Resilience result is missing "
            "required fields"
        ),
    ):
        resilience_report.load_result(
            path
        )


def test_render_report_contains_summary():
    report = (
        resilience_report.render_report(
            _sample_result()
        )
    )

    assert (
        "CLINIC SYSTEM PRO v5 RESILIENCE REPORT"
        in report
    )

    assert "report-001" in report
    assert "Total:       3" in report
    assert "Passed:      2" in report
    assert "Failed:      1" in report
    assert "Status:      FAIL" in report
    assert "Synthetic failure" in report


def test_render_report_passes_when_no_failures():
    data = _sample_result()

    data["summary"] = {
        "total": 2,
        "passed": 2,
        "failed": 0,
        "skipped": 0,
    }

    data["cases"] = (
        data["cases"][:2]
    )

    report = (
        resilience_report.render_report(
            data
        )
    )

    assert "Status:      PASS" in report