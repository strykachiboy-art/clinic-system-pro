from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable


COLUMNS = (
    "Run ID",
    "Scenario",
    "Requests",
    "Failures",
    "Avg ms",
    "p50 ms",
    "p95 ms",
    "p99 ms",
    "Max ms",
    "Avg DB ms",
    "DB q/req",
    "Avg Resp B",
    "Locust RPS",
    "Valid",
)


def _load_result(
    path: Path,
) -> dict[str, object]:
    payload = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    if (
        not isinstance(payload, dict)
        or "run_id" not in payload
        or "server" not in payload
        or "validity" not in payload
    ):
        raise ValueError(
            f"Not a baseline result JSON: {path}"
        )

    return payload


def _expand_paths(
    values: Iterable[str],
) -> list[Path]:
    paths: list[Path] = []

    for value in values:
        path = Path(value)

        if path.is_dir():
            paths.extend(
                sorted(
                    path.glob("*.json")
                )
            )
            continue

        if path.is_file():
            paths.append(path)
            continue

        matches = sorted(
            Path().glob(value)
        )

        if not matches:
            raise FileNotFoundError(
                f"Result path not found: {value}"
            )

        paths.extend(
            item
            for item in matches
            if item.suffix.lower()
            == ".json"
        )

    unique: list[Path] = []
    seen: set[Path] = set()

    for path in paths:
        resolved = path.resolve()

        if resolved in seen:
            continue

        seen.add(resolved)
        unique.append(resolved)

    return unique


def _number(
    value: object,
    digits: int = 3,
) -> str:
    if value is None:
        return "—"

    try:
        return f"{float(value):.{digits}f}"
    except (
        TypeError,
        ValueError,
    ):
        return "—"


def _integer(
    value: object,
) -> str:
    if value is None:
        return "—"

    try:
        return str(int(value))
    except (
        TypeError,
        ValueError,
    ):
        return "—"


def _row(
    payload: dict[str, object],
) -> dict[str, str]:
    server = payload.get(
        "server"
    )

    locust = payload.get(
        "locust"
    )

    validity = payload.get(
        "validity"
    )

    server = (
        server
        if isinstance(server, dict)
        else {}
    )

    locust = (
        locust
        if isinstance(locust, dict)
        else {}
    )

    validity = (
        validity
        if isinstance(validity, dict)
        else {}
    )

    return {
        "Run ID": str(
            payload.get(
                "run_id",
                "—",
            )
        ),
        "Scenario": str(
            payload.get(
                "scenario",
                "—",
            )
        ),
        "Requests": _integer(
            server.get(
                "requests"
            )
        ),
        "Failures": _integer(
            server.get(
                "failures"
            )
        ),
        "Avg ms": _number(
            server.get(
                "average_duration_ms"
            )
        ),
        "p50 ms": _number(
            server.get(
                "p50_duration_ms"
            )
        ),
        "p95 ms": _number(
            server.get(
                "p95_duration_ms"
            )
        ),
        "p99 ms": _number(
            server.get(
                "p99_duration_ms"
            )
        ),
        "Max ms": _number(
            server.get(
                "max_duration_ms"
            )
        ),
        "Avg DB ms": _number(
            server.get(
                "average_db_time_ms"
            )
        ),
        "DB q/req": _number(
            server.get(
                "average_db_queries"
            )
        ),
        "Avg Resp B": _number(
            server.get(
                "average_response_size_bytes"
            ),
            1,
        ),
        "Locust RPS": _number(
            locust.get(
                "requests_per_second"
            ),
            2,
        ),
        "Valid": (
            "YES"
            if validity.get(
                "valid"
            ) is True
            else "NO"
        ),
    }


def _markdown_table(
    rows: list[dict[str, str]],
) -> str:
    if not rows:
        return (
            "No baseline result files found."
        )

    lines = [
        "| "
        + " | ".join(COLUMNS)
        + " |",
        "|"
        + "|".join(
            "---"
            for _ in COLUMNS
        )
        + "|",
    ]

    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                row[column]
                for column in COLUMNS
            )
            + " |"
        )

    return "\n".join(lines)


def _print_route_breakdown(
    payloads: list[dict[str, object]],
) -> None:
    for payload in payloads:
        server = payload.get(
            "server"
        )

        if not isinstance(
            server,
            dict,
        ):
            continue

        breakdown = server.get(
            "route_breakdown"
        )

        if (
            not isinstance(
                breakdown,
                list,
            )
            or not breakdown
        ):
            continue

        print("")
        print(
            "=== Route Breakdown: "
            f"{payload.get('run_id', 'unknown')} ==="
        )
        print("")

        print(
            "| Method | Route | Requests | "
            "Failures | Avg ms | p95 ms | "
            "p99 ms | Avg DB ms | DB q/req |"
        )

        print(
            "|---|---|---:|---:|---:|"
            "---:|---:|---:|---:|"
        )

        for item in breakdown:
            if not isinstance(
                item,
                dict,
            ):
                continue

            print(
                "| "
                f"{item.get('method', '—')} | "
                f"{item.get('route', '—')} | "
                f"{_integer(item.get('requests'))} | "
                f"{_integer(item.get('failures'))} | "
                f"{_number(item.get('average_duration_ms'))} | "
                f"{_number(item.get('p95_duration_ms'))} | "
                f"{_number(item.get('p99_duration_ms'))} | "
                f"{_number(item.get('average_db_time_ms'))} | "
                f"{_number(item.get('average_db_queries'))} |"
            )


def _print_details(
    payloads: list[dict[str, object]],
) -> None:
    for payload in payloads:
        print("")
        print(
            f"=== {payload.get('run_id', 'unknown')} ==="
        )

        print(
            f"Scenario: "
            f"{payload.get('scenario', '—')}"
        )

        print(
            f"Generated: "
            f"{payload.get('generated_at', '—')}"
        )

        server = payload.get(
            "server"
        )

        if isinstance(
            server,
            dict,
        ):
            print(
                "Status distribution: "
                f"{server.get('status_distribution', {})}"
            )

            print(
                "Average DB time: "
                f"{_number(server.get('average_db_time_ms'))} ms"
            )

            print(
                "Maximum DB time: "
                f"{_number(server.get('max_db_time_ms'))} ms"
            )

            print(
                "Average DB queries/request: "
                f"{_number(server.get('average_db_queries'))}"
            )

            print(
                "Average response size: "
                f"{_number(server.get('average_response_size_bytes'), 1)} B"
            )

        validity = payload.get(
            "validity"
        )

        if isinstance(
            validity,
            dict,
        ):
            print(
                "Validity checks: "
                f"{validity.get('checks', {})}"
            )


def _write_outputs(
    rows: list[dict[str, str]],
    payloads: list[dict[str, object]],
    *,
    markdown_path: Path | None,
    json_path: Path | None,
) -> None:
    markdown = _markdown_table(
        rows
    )

    if markdown_path:
        markdown_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        markdown_path.write_text(
            markdown
            + "\n",
            encoding="utf-8",
        )

    if json_path:
        json_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        json_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "results": payloads,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render Clinic System Pro baseline "
            "JSON results as a comparison report."
        )
    )

    parser.add_argument(
        "results",
        nargs="*",
        help=(
            "Result JSON files, directories, or "
            "glob patterns. Defaults to "
            "load_tests/results."
        ),
    )

    parser.add_argument(
        "--details",
        action="store_true",
        help=(
            "Print per-run status and "
            "validity details."
        ),
    )

    parser.add_argument(
        "--routes",
        action="store_true",
        help=(
            "Print the route-level "
            "performance breakdown."
        ),
    )

    parser.add_argument(
        "--markdown",
        default=None,
        help=(
            "Write the comparison table "
            "to a Markdown file."
        ),
    )

    parser.add_argument(
        "--json",
        dest="json_output",
        default=None,
        help=(
            "Write the combined report "
            "to a JSON file."
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    values = (
        args.results
        or [
            str(
                Path("load_tests")
                / "results"
            )
        ]
    )

    paths = _expand_paths(
        values
    )

    if not paths:
        print(
            "No baseline result files found."
        )
        return 1

    payloads = [
        _load_result(path)
        for path in paths
    ]

    rows = [
        _row(payload)
        for payload in payloads
    ]

    print("")
    print(
        "=== Clinic System Pro "
        "Baseline Report ==="
    )
    print("")
    print(
        _markdown_table(rows)
    )

    if args.details:
        _print_details(
            payloads
        )

    if args.routes:
        _print_route_breakdown(
            payloads
        )

    markdown_path = (
        Path(
            args.markdown
        ).resolve()
        if args.markdown
        else None
    )

    json_path = (
        Path(
            args.json_output
        ).resolve()
        if args.json_output
        else None
    )

    _write_outputs(
        rows,
        payloads,
        markdown_path=markdown_path,
        json_path=json_path,
    )

    if markdown_path:
        print("")
        print(
            f"Markdown report: "
            f"{markdown_path}"
        )

    if json_path:
        print(
            f"JSON report:     "
            f"{json_path}"
        )

    invalid = [
        payload
        for payload in payloads
        if not (
            isinstance(
                payload.get(
                    "validity"
                ),
                dict,
            )
            and payload[
                "validity"
            ].get(
                "valid"
            )
            is True
        )
    ]

    if invalid:
        print("")
        print(
            f"Invalid baselines: "
            f"{len(invalid)}"
        )
        return 2

    print("")
    print(
        f"Valid baselines: "
        f"{len(payloads)}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())