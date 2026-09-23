from __future__ import annotations

import json
from pathlib import Path

import pytest

from load_tests.resilience.common.results import (
    ResilienceCaseResult,
    ResilienceRunResult,
)


def test_case_result_to_dict():
    case = ResilienceCaseResult(
        name="http_timeout",
        status="passed",
        duration_ms=42.5,
        message="Completed successfully",
        details={
            "status_code": 200,
        },
    )

    result = case.to_dict()

    assert result == {
        "name": "http_timeout",
        "status": "passed",
        "duration_ms": 42.5,
        "message": "Completed successfully",
        "details": {
            "status_code": 200,
        },
    }


@pytest.mark.parametrize(
    "status",
    [
        "passed",
        "failed",
        "skipped",
    ],
)
def test_case_result_supports_valid_statuses(status):
    case = ResilienceCaseResult(
        name="test",
        status=status,
        duration_ms=1.0,
    )

    assert case.status == status


def test_case_result_default_message_is_none():
    case = ResilienceCaseResult(
        name="test",
        status="passed",
        duration_ms=1.0,
    )

    assert case.message is None


def test_case_result_default_details_is_empty_dict():
    case = ResilienceCaseResult(
        name="test",
        status="passed",
        duration_ms=1.0,
    )

    assert case.details == {}


def test_run_result_initializes_with_empty_cases():
    result = ResilienceRunResult(
        run_id="run-001",
    )

    assert result.run_id == "run-001"
    assert result.cases == []
    assert result.total == 0
    assert result.passed == 0
    assert result.failed == 0
    assert result.skipped == 0


def test_run_result_creates_started_at():
    result = ResilienceRunResult(
        run_id="run-001",
    )

    assert isinstance(
        result.started_at,
        str,
    )
    assert result.started_at


def test_run_result_adds_case():
    result = ResilienceRunResult(
        run_id="run-001",
    )

    case = ResilienceCaseResult(
        name="network_loss",
        status="passed",
        duration_ms=10.0,
    )

    result.add(case)

    assert result.cases == [case]
    assert result.total == 1


def test_run_result_counts_passed_cases():
    result = ResilienceRunResult(
        run_id="run-001",
    )

    result.add(
        ResilienceCaseResult(
            name="case-1",
            status="passed",
            duration_ms=1.0,
        )
    )

    result.add(
        ResilienceCaseResult(
            name="case-2",
            status="passed",
            duration_ms=2.0,
        )
    )

    assert result.total == 2
    assert result.passed == 2
    assert result.failed == 0
    assert result.skipped == 0


def test_run_result_counts_failed_cases():
    result = ResilienceRunResult(
        run_id="run-001",
    )

    result.add(
        ResilienceCaseResult(
            name="case-1",
            status="failed",
            duration_ms=1.0,
            message="Failure",
        )
    )

    assert result.total == 1
    assert result.passed == 0
    assert result.failed == 1
    assert result.skipped == 0


def test_run_result_counts_skipped_cases():
    result = ResilienceRunResult(
        run_id="run-001",
    )

    result.add(
        ResilienceCaseResult(
            name="case-1",
            status="skipped",
            duration_ms=0.0,
            message="Not applicable",
        )
    )

    assert result.total == 1
    assert result.passed == 0
    assert result.failed == 0
    assert result.skipped == 1


def test_run_result_counts_mixed_cases():
    result = ResilienceRunResult(
        run_id="run-001",
    )

    result.add(
        ResilienceCaseResult(
            name="passed-case",
            status="passed",
            duration_ms=1.0,
        )
    )

    result.add(
        ResilienceCaseResult(
            name="failed-case",
            status="failed",
            duration_ms=2.0,
        )
    )

    result.add(
        ResilienceCaseResult(
            name="skipped-case",
            status="skipped",
            duration_ms=0.0,
        )
    )

    result.add(
        ResilienceCaseResult(
            name="another-passed-case",
            status="passed",
            duration_ms=3.0,
        )
    )

    assert result.total == 4
    assert result.passed == 2
    assert result.failed == 1
    assert result.skipped == 1


def test_run_result_to_dict_contains_summary():
    result = ResilienceRunResult(
        run_id="run-002",
    )

    result.add(
        ResilienceCaseResult(
            name="case-1",
            status="passed",
            duration_ms=12.5,
        )
    )

    data = result.to_dict()

    assert data["run_id"] == "run-002"
    assert "started_at" in data
    assert data["summary"] == {
        "total": 1,
        "passed": 1,
        "failed": 0,
        "skipped": 0,
    }


def test_run_result_to_dict_contains_cases():
    result = ResilienceRunResult(
        run_id="run-003",
    )

    result.add(
        ResilienceCaseResult(
            name="case-1",
            status="failed",
            duration_ms=9.25,
            message="Synthetic failure",
            details={
                "profile": "high_latency",
            },
        )
    )

    data = result.to_dict()

    assert data["cases"] == [
        {
            "name": "case-1",
            "status": "failed",
            "duration_ms": 9.25,
            "message": "Synthetic failure",
            "details": {
                "profile": "high_latency",
            },
        }
    ]


def test_run_result_to_dict_is_json_serializable():
    result = ResilienceRunResult(
        run_id="run-004",
    )

    result.add(
        ResilienceCaseResult(
            name="case-1",
            status="passed",
            duration_ms=5.0,
            details={
                "attempts": 1,
                "recovered": True,
            },
        )
    )

    serialized = json.dumps(
        result.to_dict()
    )

    assert isinstance(
        serialized,
        str,
    )


def test_run_result_save_creates_parent_directories(
    tmp_path,
):
    result = ResilienceRunResult(
        run_id="run-005",
    )

    result.add(
        ResilienceCaseResult(
            name="case-1",
            status="passed",
            duration_ms=4.0,
        )
    )

    output = (
        tmp_path
        / "nested"
        / "results"
        / "result.json"
    )

    saved_path = result.save(
        output
    )

    assert saved_path == output
    assert output.exists()
    assert output.is_file()


def test_run_result_save_writes_valid_json(
    tmp_path,
):
    result = ResilienceRunResult(
        run_id="run-006",
    )

    result.add(
        ResilienceCaseResult(
            name="packet_loss",
            status="failed",
            duration_ms=15.5,
            message="Injected packet loss",
        )
    )

    output = (
        tmp_path
        / "result.json"
    )

    result.save(output)

    loaded = json.loads(
        output.read_text(
            encoding="utf-8"
        )
    )

    assert loaded["run_id"] == "run-006"
    assert loaded["summary"]["total"] == 1
    assert loaded["summary"]["failed"] == 1
    assert loaded["cases"][0]["name"] == "packet_loss"


def test_run_result_save_preserves_details(
    tmp_path,
):
    result = ResilienceRunResult(
        run_id="run-007",
    )

    result.add(
        ResilienceCaseResult(
            name="reconnect",
            status="passed",
            duration_ms=22.0,
            details={
                "reconnected": True,
                "attempts": 1,
            },
        )
    )

    output = (
        tmp_path
        / "result.json"
    )

    result.save(output)

    loaded = json.loads(
        output.read_text(
            encoding="utf-8"
        )
    )

    assert loaded["cases"][0]["details"] == {
        "reconnected": True,
        "attempts": 1,
    }


def test_run_result_save_overwrites_existing_file(
    tmp_path,
):
    output = (
        tmp_path
        / "result.json"
    )

    output.write_text(
        '{"old": true}',
        encoding="utf-8",
    )

    result = ResilienceRunResult(
        run_id="run-008",
    )

    result.save(output)

    loaded = json.loads(
        output.read_text(
            encoding="utf-8"
        )
    )

    assert loaded["run_id"] == "run-008"
    assert "old" not in loaded


def test_multiple_cases_preserve_insertion_order():
    result = ResilienceRunResult(
        run_id="run-009",
    )

    names = [
        "first",
        "second",
        "third",
    ]

    for name in names:
        result.add(
            ResilienceCaseResult(
                name=name,
                status="passed",
                duration_ms=1.0,
            )
        )

    assert [
        case.name
        for case in result.cases
    ] == names