# load_tests/resilience/runners/resilience_report.py

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_result(
    path: str | Path,
) -> dict[str, Any]:
    result_path = Path(path)

    if not result_path.is_file():
        raise FileNotFoundError(
            f"Resilience result not found: "
            f"{result_path}"
        )

    data = json.loads(
        result_path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "Resilience result must "
            "contain a JSON object"
        )

    required = {
        "run_id",
        "started_at",
        "summary",
        "cases",
    }

    missing = required.difference(
        data
    )

    if missing:
        raise ValueError(
            "Resilience result is missing "
            "required fields: "
            + ", ".join(
                sorted(missing)
            )
        )

    return data


def render_report(
    data: dict[str, Any],
) -> str:
    summary = data[
        "summary"
    ]

    total = int(
        summary.get(
            "total",
            0,
        )
    )

    passed = int(
        summary.get(
            "passed",
            0,
        )
    )

    failed = int(
        summary.get(
            "failed",
            0,
        )
    )

    skipped = int(
        summary.get(
            "skipped",
            0,
        )
    )

    status = (
        "PASS"
        if failed == 0
        else "FAIL"
    )

    lines = [
        "=" * 72,
        "CLINIC SYSTEM PRO v5 "
        "RESILIENCE REPORT",
        "=" * 72,
        f"Run ID:      {data['run_id']}",
        f"Started at:  {data['started_at']}",
        f"Status:      {status}",
        "",
        f"Total:       {total}",
        f"Passed:      {passed}",
        f"Failed:      {failed}",
        f"Skipped:     {skipped}",
        "",
        "-" * 72,
        "CASES",
        "-" * 72,
    ]

    for case in data[
        "cases"
    ]:
        name = case.get(
            "name",
            "unknown",
        )

        case_status = case.get(
            "status",
            "unknown",
        )

        duration_ms = float(
            case.get(
                "duration_ms",
                0.0,
            )
        )

        lines.append(
            f"{case_status.upper():8} "
            f"{duration_ms:10.2f} ms  "
            f"{name}"
        )

        message = case.get(
            "message"
        )

        if message:
            lines.append(
                f"         {message}"
            )

    lines.extend(
        [
            "-" * 72,
            "",
        ]
    )

    return "\n".join(lines)


def main(
    argv: list[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Render a Clinic System Pro "
            "resilience result."
        )
    )

    parser.add_argument(
        "result",
        type=Path,
    )

    args = parser.parse_args(
        argv
    )

    data = load_result(
        args.result
    )

    print(
        render_report(data)
    )

    failed = int(
        data["summary"].get(
            "failed",
            0,
        )
    )

    return (
        1
        if failed
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )