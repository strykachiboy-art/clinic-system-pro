# load_tests/resilience/tests/runners/test_resilience.py

from __future__ import annotations

import json
import subprocess
import xml.etree.ElementTree as ET

import pytest

from load_tests.resilience.runners import resilience


def _write_junit(
    path,
):
    root = ET.Element(
        "testsuite",
        {
            "name": "resilience",
            "tests": "3",
        },
    )

    ET.SubElement(
        root,
        "testcase",
        {
            "classname": "http",
            "name": "test_passed",
            "time": "0.010",
        },
    )

    failed = ET.SubElement(
        root,
        "testcase",
        {
            "classname": "chat",
            "name": "test_failed",
            "time": "0.020",
        },
    )

    ET.SubElement(
        failed,
        "failure",
        {
            "message": "Synthetic failure",
        },
    )

    skipped = ET.SubElement(
        root,
        "testcase",
        {
            "classname": "sync",
            "name": "test_skipped",
            "time": "0.000",
        },
    )

    ET.SubElement(
        skipped,
        "skipped",
        {
            "message": "Deferred",
        },
    )

    ET.ElementTree(
        root
    ).write(
        path,
        encoding="utf-8",
        xml_declaration=True,
    )


def test_validate_scenario_accepts_supported_values():
    assert (
        resilience._validate_scenario(
            "all"
        )
        == "all"
    )

    assert (
        resilience._validate_scenario(
            "HTTP"
        )
        == "http"
    )

    assert (
        resilience._validate_scenario(
            "redis_celery"
        )
        == "redis_celery"
    )


def test_validate_scenario_rejects_unknown_value():
    with pytest.raises(
        ValueError,
        match="Unsupported resilience scenario",
    ):
        resilience._validate_scenario(
            "unknown"
        )


def test_validate_run_id_rejects_unsafe_value():
    with pytest.raises(
        ValueError,
        match="Run ID may contain only",
    ):
        resilience._validate_run_id(
            "../unsafe"
        )


def test_scenario_test_paths_returns_only_selected_suite():
    paths = (
        resilience.scenario_test_paths(
            "chat"
        )
    )

    assert len(paths) == 1

    assert (
        paths[0].name
        == "test_chat_resilience.py"
    )


def test_scenario_test_paths_all_excludes_sync():
    paths = (
        resilience.scenario_test_paths(
            "all"
        )
    )

    names = {
        path.name
        for path in paths
    }

    assert names == {
        "test_http_resilience.py",
        "test_socketio_resilience.py",
        "test_auth_resilience.py",
        "test_chat_resilience.py",
        "test_redis_celery_resilience.py",
    }

    assert (
        "test_sync_resilience.py"
        not in names
    )


def test_build_pytest_command_for_chat():
    command = (
        resilience.build_pytest_command(
            "chat",
            path := (
                resilience.RESILIENCE_ROOT
                / "results"
                / "runner.junit.xml"
            ),
        )
    )

    assert command[:3] == [
        resilience.sys.executable,
        "-m",
        "pytest",
    ]

    assert any(
        "test_chat_resilience.py" in item
        for item in command
    )

    assert "--junitxml" in command

    assert str(path) in command


def test_parse_junit_report_reads_pass_fail_skip(
    tmp_path,
):
    junit_xml = (
        tmp_path
        / "result.xml"
    )

    _write_junit(
        junit_xml
    )

    cases = (
        resilience.parse_junit_report(
            junit_xml
        )
    )

    assert len(cases) == 3

    assert cases[0].status == "passed"
    assert cases[0].duration_ms == 10.0

    assert cases[1].status == "failed"
    assert cases[1].message == (
        "Synthetic failure"
    )

    assert cases[2].status == "skipped"
    assert cases[2].message == (
        "Deferred"
    )


def test_run_resilience_saves_result(
    tmp_path,
    monkeypatch,
):
    def fake_run(
        command,
        check,
    ):
        junit_xml = (
            tmp_path
            / "run-001.junit.xml"
        )

        _write_junit(
            junit_xml
        )

        return subprocess.CompletedProcess(
            command,
            0,
        )

    monkeypatch.setattr(
        resilience.subprocess,
        "run",
        fake_run,
    )

    result = (
        resilience.run_resilience(
            resilience.ResilienceRunnerConfig(
                scenario="chat",
                run_id="run-001",
                results_dir=tmp_path,
            )
        )
    )

    assert result.run_id == "run-001"
    assert result.total == 3
    assert result.passed == 1
    assert result.failed == 1
    assert result.skipped == 1

    output = (
        tmp_path
        / "run-001.json"
    )

    assert output.exists()

    saved = json.loads(
        output.read_text(
            encoding="utf-8"
        )
    )

    assert saved["run_id"] == (
        "run-001"
    )


def test_run_resilience_records_collection_failure(
    tmp_path,
    monkeypatch,
):
    def fake_run(
        command,
        check,
    ):
        return subprocess.CompletedProcess(
            command,
            2,
        )

    monkeypatch.setattr(
        resilience.subprocess,
        "run",
        fake_run,
    )

    result = (
        resilience.run_resilience(
            resilience.ResilienceRunnerConfig(
                scenario="chat",
                run_id="run-collection-failure",
                results_dir=tmp_path,
            )
        )
    )

    assert result.total == 1
    assert result.failed == 1
    assert (
        result.cases[0].name
        == "__pytest_collection__"
    )