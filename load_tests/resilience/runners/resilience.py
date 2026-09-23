# load_tests/resilience/runners/resilience.py

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from load_tests.resilience.common.results import (
    ResilienceCaseResult,
    ResilienceRunResult,
)


RESILIENCE_ROOT = (
    Path(__file__).resolve().parents[1]
)

SCENARIO_TEST_ROOT = (
    RESILIENCE_ROOT
    / "tests"
    / "scenarios"
)

DEFAULT_RESULTS_DIR = (
    RESILIENCE_ROOT
    / "results"
)

SCENARIO_TEST_FILES = {
    "http": (
        "test_http_resilience.py"
    ),
    "socketio": (
        "test_socketio_resilience.py"
    ),
    "auth": (
        "test_auth_resilience.py"
    ),
    "chat": (
        "test_chat_resilience.py"
    ),
    "redis_celery": (
        "test_redis_celery_resilience.py"
    ),
}

RUN_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
)


@dataclass(frozen=True, slots=True)
class ResilienceRunnerConfig:
    scenario: str = "all"
    run_id: str | None = None
    results_dir: Path = DEFAULT_RESULTS_DIR
    python_executable: str = sys.executable


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp() -> str:
    return _utc_now().strftime(
        "%Y%m%dT%H%M%SZ"
    )


def default_run_id(
    scenario: str,
) -> str:
    return (
        f"resilience-"
        f"{scenario}-"
        f"{_timestamp()}"
    )


def _validate_scenario(
    scenario: str,
) -> str:
    normalized = scenario.strip().lower()

    allowed = {
        "all",
        *SCENARIO_TEST_FILES.keys(),
    }

    if normalized not in allowed:
        raise ValueError(
            "Unsupported resilience scenario: "
            f"{scenario}"
        )

    return normalized


def _validate_run_id(
    run_id: str,
) -> str:
    normalized = run_id.strip()

    if not normalized:
        raise ValueError(
            "Run ID cannot be empty"
        )

    if not RUN_ID_PATTERN.fullmatch(
        normalized
    ):
        raise ValueError(
            "Run ID may contain only "
            "letters, numbers, '.', '_' and '-'"
        )

    return normalized


def scenario_test_paths(
    scenario: str,
) -> tuple[Path, ...]:
    normalized = _validate_scenario(
        scenario
    )

    if normalized == "all":
        return tuple(
            (
                SCENARIO_TEST_ROOT
                / filename
            ).resolve()
            for filename in (
                SCENARIO_TEST_FILES.values()
            )
        )

    return (
        (
            SCENARIO_TEST_ROOT
            / SCENARIO_TEST_FILES[
                normalized
            ]
        ).resolve(),
    )


def build_pytest_command(
    scenario: str,
    junit_xml: Path,
    *,
    python_executable: str = sys.executable,
) -> list[str]:
    paths = scenario_test_paths(
        scenario
    )

    missing = [
        path
        for path in paths
        if not path.is_file()
    ]

    if missing:
        raise FileNotFoundError(
            "Resilience test file not found: "
            + ", ".join(
                str(path)
                for path in missing
            )
        )

    return [
        python_executable,
        "-m",
        "pytest",
        *(
            str(path)
            for path in paths
        ),
        "-q",
        "--junitxml",
        str(junit_xml),
    ]


def _node_message(
    node: ET.Element,
) -> str | None:
    message = node.attrib.get(
        "message"
    )

    text = (
        "".join(
            node.itertext()
        ).strip()
    )

    if message and text:
        return f"{message}: {text}"

    if message:
        return message

    if text:
        return text

    return None


def parse_junit_report(
    junit_xml: Path,
) -> list[ResilienceCaseResult]:
    if not junit_xml.is_file():
        raise FileNotFoundError(
            "JUnit XML report not found: "
            f"{junit_xml}"
        )

    root = ET.parse(
        junit_xml
    ).getroot()

    cases: list[
        ResilienceCaseResult
    ] = []

    for testcase in root.iter(
        "testcase"
    ):
        name = testcase.attrib.get(
            "name",
            "unknown",
        )

        classname = testcase.attrib.get(
            "classname",
            "",
        )

        node_name = (
            f"{classname}::{name}"
            if classname
            else name
        )

        raw_time = testcase.attrib.get(
            "time",
            "0",
        )

        try:
            duration_ms = (
                float(raw_time)
                * 1000.0
            )
        except (
            TypeError,
            ValueError,
        ):
            duration_ms = 0.0

        failure = testcase.find(
            "failure"
        )

        error = testcase.find(
            "error"
        )

        skipped = testcase.find(
            "skipped"
        )

        if failure is not None:
            status = "failed"
            message = _node_message(
                failure
            )

        elif error is not None:
            status = "failed"
            message = _node_message(
                error
            )

        elif skipped is not None:
            status = "skipped"
            message = _node_message(
                skipped
            )

        else:
            status = "passed"
            message = None

        details = {
            "classname": classname,
        }

        if failure is not None:
            details["failure_type"] = (
                failure.attrib.get(
                    "type"
                )
            )

        if error is not None:
            details["error_type"] = (
                error.attrib.get(
                    "type"
                )
            )

        cases.append(
            ResilienceCaseResult(
                name=node_name,
                status=status,
                duration_ms=duration_ms,
                message=message,
                details=details,
            )
        )

    return cases


def run_resilience(
    config: ResilienceRunnerConfig,
) -> ResilienceRunResult:
    scenario = _validate_scenario(
        config.scenario
    )

    run_id = _validate_run_id(
        config.run_id
        if config.run_id is not None
        else default_run_id(scenario)
    )

    results_dir = (
        Path(config.results_dir)
        .resolve()
    )

    results_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    junit_xml = (
        results_dir
        / f"{run_id}.junit.xml"
    )

    command = build_pytest_command(
        scenario,
        junit_xml,
        python_executable=(
            config.python_executable
        ),
    )

    completed = subprocess.run(
        command,
        check=False,
    )

    result = ResilienceRunResult(
        run_id=run_id,
    )

    if junit_xml.is_file():
        cases = parse_junit_report(
            junit_xml
        )

        for case in cases:
            case.details.update(
                {
                    "scenario": scenario,
                    "pytest_return_code": (
                        completed.returncode
                    ),
                }
            )

            result.add(case)

    if (
        not result.cases
        and completed.returncode != 0
    ):
        result.add(
            ResilienceCaseResult(
                name="__pytest_collection__",
                status="failed",
                duration_ms=0.0,
                message=(
                    "Pytest exited with "
                    "a non-zero status "
                    "before test cases "
                    "were reported"
                ),
                details={
                    "scenario": scenario,
                    "pytest_return_code": (
                        completed.returncode
                    ),
                },
            )
        )

    output_path = (
        results_dir
        / f"{run_id}.json"
    )

    result.save(
        output_path
    )

    return result


def _print_summary(
    result: ResilienceRunResult,
    output_path: Path,
) -> None:
    print()
    print(
        "=" * 72
    )
    print(
        "CLINIC SYSTEM PRO v5 "
        "RESILIENCE RUN"
    )
    print(
        "=" * 72
    )

    print(
        f"Run ID:       {result.run_id}"
    )

    print(
        f"Total cases:  {result.total}"
    )

    print(
        f"Passed:       {result.passed}"
    )

    print(
        f"Failed:       {result.failed}"
    )

    print(
        f"Skipped:      {result.skipped}"
    )

    print(
        f"Result file:  {output_path}"
    )

    print(
        "=" * 72
    )


def main(
    argv: list[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run Clinic System Pro "
            "resilience scenarios."
        )
    )

    parser.add_argument(
        "--scenario",
        default="all",
        choices=[
            "all",
            *SCENARIO_TEST_FILES.keys(),
        ],
    )

    parser.add_argument(
        "--run-id",
    )

    parser.add_argument(
        "--results-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
    )

    args = parser.parse_args(
        argv
    )

    config = ResilienceRunnerConfig(
        scenario=args.scenario,
        run_id=args.run_id,
        results_dir=args.results_dir,
    )

    result = run_resilience(
        config
    )

    output_path = (
        Path(config.results_dir)
        / f"{result.run_id}.json"
    )

    _print_summary(
        result,
        output_path,
    )

    return (
        1
        if result.failed
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )