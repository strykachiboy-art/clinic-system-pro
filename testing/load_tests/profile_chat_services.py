from __future__ import annotations

import argparse
import cProfile
import json
import os
import pstats
import statistics
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

from app.modules.chat.models.conversation_model import Conversation
from app.modules.chat.models.message_model import Message

from app.modules.chat.services.message_service import (
    create_message,
    list_messages,
)
from app.modules.chat.services.message_search_service import (
    search_messages,
)


DEFAULT_ENV = "development"
DEFAULT_RESULTS_DIR = (
    PROJECT_ROOT / "load_tests" / "results"
)

DEFAULT_WARMUPS = 3
DEFAULT_RUNS = 10
DEFAULT_PER_PAGE = 50
DEFAULT_SEARCH = "clinical"


class QueryProfiler:
    def __init__(self) -> None:
        self.query_count = 0
        self.db_time_ms = 0.0
        self._started_at: float | None = None

    def reset(self) -> None:
        self.query_count = 0
        self.db_time_ms = 0.0
        self._started_at = None

    def before_cursor_execute(
        self,
        conn,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ) -> None:
        self.query_count += 1
        self._started_at = time.perf_counter()

    def after_cursor_execute(
        self,
        conn,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ) -> None:
        if self._started_at is None:
            return

        self.db_time_ms += (
            time.perf_counter()
            - self._started_at
        ) * 1000

        self._started_at = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Profile Clinic System Pro Chat service "
            "performance without modifying Chat production code."
        )
    )

    parser.add_argument(
        "--mode",
        choices=(
            "create",
            "list",
            "search",
            "all",
        ),
        default="all",
    )

    parser.add_argument(
        "--clinic-id",
        type=int,
        default=int(
            os.getenv(
                "CHAT_PROFILE_CLINIC_ID",
                "0",
            )
        ),
    )

    parser.add_argument(
        "--user-id",
        type=int,
        default=int(
            os.getenv(
                "CHAT_PROFILE_USER_ID",
                "0",
            )
        ),
    )

    parser.add_argument(
        "--conversation-id",
        type=int,
        default=int(
            os.getenv(
                "CHAT_PROFILE_CONVERSATION_ID",
                "0",
            )
        ),
    )

    parser.add_argument(
        "--warmups",
        type=int,
        default=int(
            os.getenv(
                "CHAT_PROFILE_WARMUPS",
                str(DEFAULT_WARMUPS),
            )
        ),
    )

    parser.add_argument(
        "--runs",
        type=int,
        default=int(
            os.getenv(
                "CHAT_PROFILE_RUNS",
                str(DEFAULT_RUNS),
            )
        ),
    )

    parser.add_argument(
        "--per-page",
        type=int,
        default=DEFAULT_PER_PAGE,
    )

    parser.add_argument(
        "--search",
        default=DEFAULT_SEARCH,
    )

    parser.add_argument(
        "--env",
        default=os.getenv(
            "FLASK_ENV",
            DEFAULT_ENV,
        ),
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
    )

    return parser.parse_args()


def validate_args(
    args: argparse.Namespace,
) -> None:
    if args.clinic_id <= 0:
        raise RuntimeError(
            "A valid --clinic-id is required."
        )

    if args.user_id <= 0:
        raise RuntimeError(
            "A valid --user-id is required."
        )

    if args.conversation_id <= 0:
        raise RuntimeError(
            "A valid --conversation-id is required."
        )

    if args.warmups < 0:
        raise RuntimeError(
            "--warmups cannot be negative."
        )

    if args.runs <= 0:
        raise RuntimeError(
            "--runs must be greater than zero."
        )

    if args.per_page <= 0:
        raise RuntimeError(
            "--per-page must be greater than zero."
        )


def percentile(
    values: list[float],
    percentile_value: float,
) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    rank = (
        percentile_value
        / 100
        * (len(ordered) - 1)
    )

    lower = int(rank)
    upper = min(
        lower + 1,
        len(ordered) - 1,
    )

    fraction = rank - lower

    return (
        ordered[lower]
        + (
            ordered[upper]
            - ordered[lower]
        )
        * fraction
    )


def validate_database_objects(
    clinic_id: int,
    user_id: int,
    conversation_id: int,
) -> tuple[User, Conversation]:
    user = db.session.get(
        User,
        user_id,
    )

    if user is None:
        raise RuntimeError(
            f"User {user_id} does not exist."
        )

    if user.clinic_id != clinic_id:
        raise RuntimeError(
            f"User {user_id} belongs to clinic "
            f"{user.clinic_id}, not clinic {clinic_id}."
        )

    conversation = db.session.get(
        Conversation,
        conversation_id,
    )

    if conversation is None:
        raise RuntimeError(
            f"Conversation {conversation_id} does not exist."
        )

    if conversation.clinic_id != clinic_id:
        raise RuntimeError(
            f"Conversation {conversation_id} belongs to clinic "
            f"{conversation.clinic_id}, not clinic {clinic_id}."
        )

    return user, conversation


def run_operation(
    *,
    operation_name: str,
    operation,
    query_profiler: QueryProfiler,
) -> dict[str, Any]:
    query_profiler.reset()

    started = time.perf_counter()

    result = operation()

    elapsed_ms = (
        time.perf_counter()
        - started
    ) * 1000

    return {
        "operation": operation_name,
        "service_time_ms": elapsed_ms,
        "query_count": query_profiler.query_count,
        "db_time_ms": query_profiler.db_time_ms,
        "result_type": type(result).__name__,
    }


def warmup(
    operation,
    query_profiler: QueryProfiler,
    warmup_count: int,
) -> None:
    for _ in range(warmup_count):
        run_operation(
            operation_name="warmup",
            operation=operation,
            query_profiler=query_profiler,
        )

    db.session.expire_all()


def profile_representative_run(
    *,
    operation_name: str,
    operation,
    query_profiler: QueryProfiler,
    output_dir: Path,
) -> tuple[dict[str, Any], Path, Path]:
    profiler = cProfile.Profile()

    query_profiler.reset()

    started = time.perf_counter()

    profiler.enable()

    result = operation()

    profiler.disable()

    elapsed_ms = (
        time.perf_counter()
        - started
    ) * 1000

    timestamp = time.strftime(
        "%Y%m%d-%H%M%S"
    )

    profile_path = (
        output_dir
        / f"chat-{operation_name}-{timestamp}.prof"
    )

    stats_path = (
        output_dir
        / f"chat-{operation_name}-{timestamp}.txt"
    )

    profiler.dump_stats(
        str(profile_path)
    )

    stats = pstats.Stats(
        profiler
    )

    stats.sort_stats(
        "cumulative"
    )

    with stats_path.open(
        "w",
        encoding="utf-8",
    ) as fh:
        stats.stream = fh
        stats.print_stats(100)

    stats.stream = sys.stdout

    summary = {
        "operation": operation_name,
        "service_time_ms": round(
            elapsed_ms,
            3,
        ),
        "query_count": (
            query_profiler.query_count
        ),
        "db_time_ms": round(
            query_profiler.db_time_ms,
            3,
        ),
        "result_type": type(result).__name__,
        "profile_file": str(
            profile_path
        ),
        "stats_file": str(
            stats_path
        ),
    }

    return (
        summary,
        profile_path,
        stats_path,
    )


def benchmark_operation(
    *,
    operation_name: str,
    operation,
    query_profiler: QueryProfiler,
    warmup_count: int,
    run_count: int,
    output_dir: Path,
) -> dict[str, Any]:
    print()
    print("=" * 100)
    print(
        f"CHAT PROFILE: {operation_name.upper()}"
    )
    print("=" * 100)

    print(
        f"Warmups:              {warmup_count}"
    )
    print(
        f"Measured runs:        {run_count}"
    )

    warmup(
        operation,
        query_profiler,
        warmup_count,
    )

    runs: list[dict[str, Any]] = []

    for index in range(run_count):
        result = run_operation(
            operation_name=operation_name,
            operation=operation,
            query_profiler=query_profiler,
        )

        runs.append(result)

        print(
            f"Run {index + 1:>2}: "
            f"{result['service_time_ms']:>10.3f} ms | "
            f"queries={result['query_count']:>3} | "
            f"DB={result['db_time_ms']:>10.3f} ms"
        )

    service_times = [
        item["service_time_ms"]
        for item in runs
    ]

    db_times = [
        item["db_time_ms"]
        for item in runs
    ]

    query_counts = [
        item["query_count"]
        for item in runs
    ]

    profile_summary, profile_path, stats_path = (
        profile_representative_run(
            operation_name=operation_name,
            operation=operation,
            query_profiler=query_profiler,
            output_dir=output_dir,
        )
    )

    summary = {
        "operation": operation_name,
        "warmups": warmup_count,
        "runs": run_count,
        "service_time_ms": {
            "average": round(
                statistics.mean(service_times),
                3,
            ),
            "median": round(
                statistics.median(service_times),
                3,
            ),
            "p95": round(
                percentile(
                    service_times,
                    95,
                ),
                3,
            ),
            "p99": round(
                percentile(
                    service_times,
                    99,
                ),
                3,
            ),
            "min": round(
                min(service_times),
                3,
            ),
            "max": round(
                max(service_times),
                3,
            ),
        },
        "db_time_ms": {
            "average": round(
                statistics.mean(db_times),
                3,
            ),
            "median": round(
                statistics.median(db_times),
                3,
            ),
            "p95": round(
                percentile(
                    db_times,
                    95,
                ),
                3,
            ),
            "p99": round(
                percentile(
                    db_times,
                    99,
                ),
                3,
            ),
            "min": round(
                min(db_times),
                3,
            ),
            "max": round(
                max(db_times),
                3,
            ),
        },
        "query_count": {
            "average": round(
                statistics.mean(query_counts),
                3,
            ),
            "median": round(
                statistics.median(query_counts),
                3,
            ),
            "min": min(query_counts),
            "max": max(query_counts),
        },
        "representative_profile": profile_summary,
        "runs_detail": runs,
    }

    print()
    print(
        f"Average service time: "
        f"{summary['service_time_ms']['average']:.3f} ms"
    )
    print(
        f"Median service time:  "
        f"{summary['service_time_ms']['median']:.3f} ms"
    )
    print(
        f"P95 service time:     "
        f"{summary['service_time_ms']['p95']:.3f} ms"
    )
    print(
        f"P99 service time:     "
        f"{summary['service_time_ms']['p99']:.3f} ms"
    )
    print(
        f"Average DB time:      "
        f"{summary['db_time_ms']['average']:.3f} ms"
    )
    print(
        f"Average query count:  "
        f"{summary['query_count']['average']:.3f}"
    )
    print(
        f"Profile:              {profile_path}"
    )
    print(
        f"Stats:                {stats_path}"
    )

    return summary


def build_operations(
    *,
    clinic_id: int,
    user_id: int,
    conversation_id: int,
    search_text: str,
    per_page: int,
) -> dict[str, Any]:
    def create_operation():
        unique_suffix = (
            time.time_ns()
        )

        return create_message(
            clinic_id=clinic_id,
            conversation_id=conversation_id,
            sender_id=user_id,
            content=(
                "Chat performance profiling message "
                f"{unique_suffix}"
            ),
        )

    def list_operation():
        return list_messages(
            clinic_id=clinic_id,
            conversation_id=conversation_id,
            user_id=user_id,
            page=1,
            per_page=per_page,
        )

    def search_operation():
        return search_messages(
            clinic_id=clinic_id,
            user_id=user_id,
            query=search_text,
            page=1,
            per_page=per_page,
            conversation_id=conversation_id,
        )

    return {
        "create": create_operation,
        "list": list_operation,
        "search": search_operation,
    }


def main() -> None:
    args = parse_args()

    validate_args(
        args
    )

    args.output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    app = create_app(
        args.env
    )

    with app.app_context():
        user, conversation = (
            validate_database_objects(
                clinic_id=args.clinic_id,
                user_id=args.user_id,
                conversation_id=args.conversation_id,
            )
        )

        print("=" * 100)
        print("CLINIC SYSTEM PRO v5 — CHAT SERVICE PROFILER")
        print("=" * 100)
        print(
            f"Environment:         {args.env}"
        )
        print(
            f"Clinic ID:           {args.clinic_id}"
        )
        print(
            f"User ID:             {args.user_id}"
        )
        print(
            f"Conversation ID:     {args.conversation_id}"
        )
        print(
            f"User role:           "
            f"{getattr(user.role, 'value', user.role)}"
        )
        print(
            f"Conversation type:   "
            f"{getattr(conversation.conversation_type, 'value', conversation.conversation_type)}"
        )
        print(
            f"Per-page:            {args.per_page}"
        )
        print(
            f"Search term:         {args.search!r}"
        )
        print("=" * 100)

        query_profiler = QueryProfiler()

        engine = db.engine

        event.listen(
            engine,
            "before_cursor_execute",
            query_profiler.before_cursor_execute,
        )

        event.listen(
            engine,
            "after_cursor_execute",
            query_profiler.after_cursor_execute,
        )

        try:
            operations = build_operations(
                clinic_id=args.clinic_id,
                user_id=args.user_id,
                conversation_id=args.conversation_id,
                search_text=args.search,
                per_page=args.per_page,
            )

            requested_operations = (
                list(operations.keys())
                if args.mode == "all"
                else [args.mode]
            )

            results: dict[str, Any] = {}

            for operation_name in requested_operations:
                results[operation_name] = (
                    benchmark_operation(
                        operation_name=operation_name,
                        operation=operations[
                            operation_name
                        ],
                        query_profiler=query_profiler,
                        warmup_count=args.warmups,
                        run_count=args.runs,
                        output_dir=args.output_dir,
                    )
                )

            timestamp = time.strftime(
                "%Y%m%d-%H%M%S"
            )

            summary_path = (
                args.output_dir
                / f"chat-services-{timestamp}.json"
            )

            summary = {
                "environment": args.env,
                "clinic_id": args.clinic_id,
                "user_id": args.user_id,
                "conversation_id": args.conversation_id,
                "per_page": args.per_page,
                "search": args.search,
                "mode": args.mode,
                "warmups": args.warmups,
                "runs": args.runs,
                "results": results,
            }

            summary_path.write_text(
                json.dumps(
                    summary,
                    indent=2,
                ),
                encoding="utf-8",
            )

            print()
            print("=" * 100)
            print("CHAT PROFILE COMPLETE")
            print("=" * 100)

            for operation_name, result in results.items():
                print(
                    f"{operation_name:>8}: "
                    f"avg={result['service_time_ms']['average']:.3f} ms | "
                    f"median={result['service_time_ms']['median']:.3f} ms | "
                    f"P95={result['service_time_ms']['p95']:.3f} ms | "
                    f"queries={result['query_count']['average']:.3f} | "
                    f"DB={result['db_time_ms']['average']:.3f} ms"
                )

            print()
            print(
                f"Summary: {summary_path}"
            )
            print("=" * 100)

        finally:
            event.remove(
                engine,
                "before_cursor_execute",
                query_profiler.before_cursor_execute,
            )

            event.remove(
                engine,
                "after_cursor_execute",
                query_profiler.after_cursor_execute,
            )

            db.session.rollback()


if __name__ == "__main__":
    main()