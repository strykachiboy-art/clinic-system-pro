from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from sqlalchemy import event


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app import create_app
from app.extensions import db
from app.core.auth.user.models.user_model import User
from app.modules.dashboard.services.dashboard_service import get_dashboard


DEFAULT_ENV = "development"
DEFAULT_ACTOR_ID = 5
DEFAULT_TOP = 8
DEFAULT_EXPLAIN_TIMEOUT_MS = 30000

DEFAULT_RESULTS_DIR = (
    PROJECT_ROOT / "load_tests" / "results"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Capture the exact SQL emitted by the real Dashboard "
            "service call and EXPLAIN ANALYZE the slowest queries."
        )
    )

    parser.add_argument(
        "--actor-id",
        type=int,
        default=DEFAULT_ACTOR_ID,
    )

    parser.add_argument(
        "--env",
        default=os.getenv(
            "FLASK_ENV",
            DEFAULT_ENV,
        ),
    )

    parser.add_argument(
        "--top",
        type=int,
        default=DEFAULT_TOP,
    )

    parser.add_argument(
        "--explain-timeout-ms",
        type=int,
        default=DEFAULT_EXPLAIN_TIMEOUT_MS,
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
    )

    args = parser.parse_args()

    if args.top <= 0:
        parser.error("--top must be greater than 0")

    if args.explain_timeout_ms <= 0:
        parser.error(
            "--explain-timeout-ms must be greater than 0"
        )

    return args


def _safe_repr(value: Any) -> str:
    try:
        return repr(value)
    except Exception:
        return f"<unrepresentable {type(value).__name__}>"


def _is_explainable_statement(statement: str) -> bool:
    normalized = statement.lstrip().upper()

    return normalized.startswith(
        (
            "SELECT ",
            "SELECT\n",
            "WITH ",
            "WITH\n",
        )
    )


def _parse_plan_times(
    plan_lines: list[str],
) -> tuple[float | None, float | None]:
    planning_ms = None
    execution_ms = None

    for line in plan_lines:
        stripped = line.strip()

        if stripped.startswith("Planning Time:"):
            raw = (
                stripped
                .split(":", 1)[1]
                .strip()
                .removesuffix(" ms")
            )

            try:
                planning_ms = float(raw)
            except ValueError:
                pass

        elif stripped.startswith("Execution Time:"):
            raw = (
                stripped
                .split(":", 1)[1]
                .strip()
                .removesuffix(" ms")
            )

            try:
                execution_ms = float(raw)
            except ValueError:
                pass

    return planning_ms, execution_ms


def _run_explain(
    *,
    engine,
    statement: str,
    parameters: Any,
    timeout_ms: int,
) -> dict[str, Any]:
    raw_connection = engine.raw_connection()

    cursor = None

    try:
        cursor = raw_connection.cursor()

        cursor.execute(
            f"SET statement_timeout = {int(timeout_ms)}"
        )

        explain_statement = (
            "EXPLAIN "
            "(ANALYZE, BUFFERS, VERBOSE, FORMAT TEXT) "
            + statement
        )

        started = time.perf_counter()

        cursor.execute(
            explain_statement,
            parameters,
        )

        elapsed_ms = (
            time.perf_counter() - started
        ) * 1000

        rows = cursor.fetchall()

        plan_lines = [
            str(row[0])
            for row in rows
        ]

        planning_ms, execution_ms = _parse_plan_times(
            plan_lines
        )

        return {
            "success": True,
            "explain_elapsed_ms": round(
                elapsed_ms,
                3,
            ),
            "planning_time_ms": planning_ms,
            "execution_time_ms": execution_ms,
            "plan": plan_lines,
        }

    except Exception as exc:
        return {
            "success": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            try:
                raw_connection.rollback()
            except Exception:
                pass

            raw_connection.close()


def profile_dashboard(
    *,
    app,
    actor_id: int,
    top: int,
    explain_timeout_ms: int,
    output_dir: Path,
) -> None:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    with app.app_context():
        actor = db.session.get(
            User,
            actor_id,
        )

        if actor is None:
            raise RuntimeError(
                f"User with ID {actor_id} does not exist."
            )

        print("=" * 100)
        print("DASHBOARD EXACT-SQL EXPLAIN PROFILER")
        print("=" * 100)
        print(
            f"Actor ID:             {actor_id}"
        )
        print(
            f"Actor role:           "
            f"{getattr(actor.role, 'value', actor.role)}"
        )
        print(
            f"Clinic ID:            {actor.clinic_id}"
        )
        print(
            f"Top queries:          {top}"
        )
        print(
            f"EXPLAIN timeout:      "
            f"{explain_timeout_ms} ms"
        )
        print("=" * 100)
        print()

        engine = db.engine

        captured_queries: list[dict[str, Any]] = []

        def before_cursor_execute(
            conn,
            cursor,
            statement,
            parameters,
            context,
            executemany,
        ):
            context._dashboard_explain_started_at = (
                time.perf_counter()
            )

        def after_cursor_execute(
            conn,
            cursor,
            statement,
            parameters,
            context,
            executemany,
        ):
            started = getattr(
                context,
                "_dashboard_explain_started_at",
                None,
            )

            if started is None:
                return

            elapsed_ms = (
                time.perf_counter() - started
            ) * 1000

            try:
                safe_parameters = copy.deepcopy(
                    parameters
                )
            except Exception:
                safe_parameters = parameters

            captured_queries.append(
                {
                    "query_number": len(
                        captured_queries
                    )
                    + 1,
                    "duration_ms": elapsed_ms,
                    "statement": statement,
                    "parameters": safe_parameters,
                    "executemany": executemany,
                }
            )

        event.listen(
            engine,
            "before_cursor_execute",
            before_cursor_execute,
        )

        event.listen(
            engine,
            "after_cursor_execute",
            after_cursor_execute,
        )

        service_started = time.perf_counter()

        try:
            result = get_dashboard(
                actor_id=actor_id,
            )
        finally:
            event.remove(
                engine,
                "before_cursor_execute",
                before_cursor_execute,
            )

            event.remove(
                engine,
                "after_cursor_execute",
                after_cursor_execute,
            )

        service_elapsed_ms = (
            time.perf_counter() - service_started
        ) * 1000

        ranked_queries = sorted(
            captured_queries,
            key=lambda item: item["duration_ms"],
            reverse=True,
        )

        explain_candidates = [
            item
            for item in ranked_queries
            if _is_explainable_statement(
                item["statement"]
            )
        ][:top]

        timestamp = time.strftime(
            "%Y%m%d-%H%M%S"
        )

        json_path = (
            output_dir
            / f"dashboard-explain-{timestamp}.json"
        )

        txt_path = (
            output_dir
            / f"dashboard-explain-{timestamp}.txt"
        )

        explain_results: list[dict[str, Any]] = []

        print(
            f"Dashboard result:     "
            f"{type(result).__name__}"
        )
        print(
            f"Service time:         "
            f"{service_elapsed_ms:.3f} ms"
        )
        print(
            f"Captured SQL queries: "
            f"{len(captured_queries)}"
        )
        print()

        print("=" * 100)
        print("RUNNING EXPLAIN ANALYZE")
        print("=" * 100)

        for query in explain_candidates:
            query_number = query[
                "query_number"
            ]

            duration_ms = query[
                "duration_ms"
            ]

            statement = query[
                "statement"
            ]

            parameters = query[
                "parameters"
            ]

            print()
            print(
                f"[Query {query_number:02d}] "
                f"{duration_ms:.3f} ms"
            )

            explain_result = _run_explain(
                engine=engine,
                statement=statement,
                parameters=parameters,
                timeout_ms=explain_timeout_ms,
            )

            explain_results.append(
                {
                    "query_number": query_number,
                    "original_duration_ms": round(
                        duration_ms,
                        3,
                    ),
                    "statement": statement,
                    "parameters": _safe_repr(
                        parameters
                    ),
                    "executemany": query[
                        "executemany"
                    ],
                    **explain_result,
                }
            )

            if explain_result["success"]:
                print(
                    f"  Planning:  "
                    f"{explain_result['planning_time_ms']} ms"
                )
                print(
                    f"  Execution: "
                    f"{explain_result['execution_time_ms']} ms"
                )
            else:
                print(
                    f"  ERROR: "
                    f"{explain_result['error']}"
                )

        summary = {
            "actor_id": actor_id,
            "actor_role": getattr(
                actor.role,
                "value",
                str(actor.role),
            ),
            "clinic_id": actor.clinic_id,
            "service_entry_point": (
                "app.modules.dashboard.services.dashboard_service.get_dashboard"
            ),
            "dashboard_result_type": type(
                result
            ).__name__,
            "service_time_ms": round(
                service_elapsed_ms,
                3,
            ),
            "sql_query_count": len(
                captured_queries
            ),
            "top_queries_explained": len(
                explain_results
            ),
            "queries": [
                {
                    "query_number": query[
                        "query_number"
                    ],
                    "duration_ms": round(
                        query["duration_ms"],
                        3,
                    ),
                    "statement": query[
                        "statement"
                    ],
                    "parameters": _safe_repr(
                        query["parameters"]
                    ),
                    "executemany": query[
                        "executemany"
                    ],
                }
                for query in captured_queries
            ],
            "explain_results": explain_results,
            "generated_at": time.strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),
        }

        json_path.write_text(
            json.dumps(
                summary,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        with txt_path.open(
            "w",
            encoding="utf-8",
        ) as fh:
            fh.write(
                "=" * 100 + "\n"
            )
            fh.write(
                "DASHBOARD EXACT-SQL EXPLAIN REPORT\n"
            )
            fh.write(
                "=" * 100 + "\n\n"
            )

            fh.write(
                f"Actor ID:             {actor_id}\n"
            )
            fh.write(
                f"Actor role:           "
                f"{getattr(actor.role, 'value', actor.role)}\n"
            )
            fh.write(
                f"Clinic ID:            "
                f"{actor.clinic_id}\n"
            )
            fh.write(
                f"Dashboard result:     "
                f"{type(result).__name__}\n"
            )
            fh.write(
                f"Service time:         "
                f"{service_elapsed_ms:.3f} ms\n"
            )
            fh.write(
                f"SQL query count:      "
                f"{len(captured_queries)}\n"
            )
            fh.write("\n")

            fh.write(
                "=" * 100 + "\n"
            )
            fh.write(
                "ALL CAPTURED QUERIES BY ORIGINAL ORDER\n"
            )
            fh.write(
                "=" * 100 + "\n\n"
            )

            for query in captured_queries:
                fh.write(
                    f"[{query['query_number']:02d}] "
                    f"{query['duration_ms']:.3f} ms\n"
                )
                fh.write(
                    f"Parameters: "
                    f"{_safe_repr(query['parameters'])}\n"
                )
                fh.write(
                    query["statement"]
                )
                fh.write(
                    "\n"
                    + "-" * 100
                    + "\n\n"
                )

            fh.write(
                "=" * 100 + "\n"
            )
            fh.write(
                "EXPLAIN ANALYZE RESULTS\n"
            )
            fh.write(
                "=" * 100 + "\n\n"
            )

            for result_data in explain_results:
                fh.write(
                    f"[Query "
                    f"{result_data['query_number']:02d}] "
                    f"Original: "
                    f"{result_data['original_duration_ms']:.3f} ms\n"
                )

                fh.write(
                    f"Parameters: "
                    f"{result_data['parameters']}\n"
                )

                fh.write(
                    result_data["statement"]
                )
                fh.write(
                    "\n\n"
                )

                if result_data["success"]:
                    fh.write(
                        f"Planning Time: "
                        f"{result_data['planning_time_ms']} ms\n"
                    )
                    fh.write(
                        f"Execution Time: "
                        f"{result_data['execution_time_ms']} ms\n"
                    )
                    fh.write(
                        f"Profiler EXPLAIN elapsed: "
                        f"{result_data['explain_elapsed_ms']} ms\n"
                    )
                    fh.write(
                        "\n"
                    )

                    fh.write(
                        "\n".join(
                            result_data["plan"]
                        )
                    )
                    fh.write(
                        "\n"
                    )
                else:
                    fh.write(
                        f"ERROR: "
                        f"{result_data['error_type']}: "
                        f"{result_data['error']}\n"
                    )

                fh.write(
                    "\n"
                    + "=" * 100
                    + "\n\n"
                )

        print()
        print("=" * 100)
        print("EXPLAIN PROFILING COMPLETE")
        print("=" * 100)
        print(
            f"Service time:         "
            f"{service_elapsed_ms:.3f} ms"
        )
        print(
            f"SQL queries:          "
            f"{len(captured_queries)}"
        )
        print(
            f"Explained queries:    "
            f"{len(explain_results)}"
        )
        print(
            f"JSON report:          "
            f"{json_path}"
        )
        print(
            f"Text report:          "
            f"{txt_path}"
        )
        print("=" * 100)

        print()
        print(
            "TOP QUERIES BY ORIGINAL EXECUTION TIME"
        )
        print("=" * 100)

        for query in explain_results:
            execution_time = (
                query.get("execution_time_ms")
            )

            planning_time = (
                query.get("planning_time_ms")
            )

            print(
                f"[Query {query['query_number']:02d}] "
                f"original={query['original_duration_ms']:.3f} ms "
                f"planning={planning_time} ms "
                f"execution={execution_time} ms"
            )

        print()
        print("Done.")


def main() -> None:
    args = parse_args()

    app = create_app(
        args.env
    )

    profile_dashboard(
        app=app,
        actor_id=args.actor_id,
        top=args.top,
        explain_timeout_ms=args.explain_timeout_ms,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()