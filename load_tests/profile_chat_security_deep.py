from __future__ import annotations

import argparse
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import event

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.extensions import db
from app.modules.chat.services.chat_security_service import (
    ChatSecurityService,
)


DEFAULT_USER_ID = 5037
DEFAULT_CONVERSATION_ID = 51
DEFAULT_RUNS = 20
DEFAULT_WARMUP = 3


@dataclass
class Measurement:
    total_ms: float
    sql_ms: float
    query_count: int


class SQLProfiler:
    def __init__(self) -> None:
        self.query_count = 0
        self.sql_ms = 0.0

    def reset(self) -> None:
        self.query_count = 0
        self.sql_ms = 0.0

    def before_cursor_execute(
        self,
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        conn.info.setdefault(
            "deep_profile_query_start",
            [],
        ).append(
            time.perf_counter()
        )

    def after_cursor_execute(
        self,
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        starts = conn.info.get(
            "deep_profile_query_start"
        )

        if not starts:
            return

        started = starts.pop()

        self.query_count += 1
        self.sql_ms += (
            time.perf_counter() - started
        ) * 1000.0


@dataclass
class PoolStats:
    checkout_count: int = 0
    checkin_count: int = 0
    connect_count: int = 0


def attach_pool_profiler(
    engine: Any,
    pool_stats: PoolStats,
) -> None:
    def on_checkout(
        dbapi_connection: Any,
        connection_record: Any,
        connection_proxy: Any,
    ) -> None:
        pool_stats.checkout_count += 1

    def on_checkin(
        dbapi_connection: Any,
        connection_record: Any,
    ) -> None:
        pool_stats.checkin_count += 1

    def on_connect(
        dbapi_connection: Any,
        connection_record: Any,
    ) -> None:
        pool_stats.connect_count += 1

    event.listen(
        engine.pool,
        "checkout",
        on_checkout,
    )

    event.listen(
        engine.pool,
        "checkin",
        on_checkin,
    )

    event.listen(
        engine.pool,
        "connect",
        on_connect,
    )

    pool_stats._checkout_listener = on_checkout
    pool_stats._checkin_listener = on_checkin
    pool_stats._connect_listener = on_connect


def detach_pool_profiler(
    engine: Any,
    pool_stats: PoolStats,
) -> None:
    event.remove(
        engine.pool,
        "checkout",
        pool_stats._checkout_listener,
    )

    event.remove(
        engine.pool,
        "checkin",
        pool_stats._checkin_listener,
    )

    event.remove(
        engine.pool,
        "connect",
        pool_stats._connect_listener,
    )


def measure_get_active_user(
    user_id: int,
    sql_profiler: SQLProfiler,
) -> Measurement:
    db.session.remove()

    sql_profiler.reset()

    started = time.perf_counter()

    ChatSecurityService.get_active_user(
        user_id
    )

    total_ms = (
        time.perf_counter() - started
    ) * 1000.0

    db.session.rollback()
    db.session.remove()

    return Measurement(
        total_ms=total_ms,
        sql_ms=sql_profiler.sql_ms,
        query_count=sql_profiler.query_count,
    )


def measure_connection_acquisition() -> float:
    db.session.remove()

    started = time.perf_counter()

    connection = db.session.connection()

    elapsed_ms = (
        time.perf_counter() - started
    ) * 1000.0

    db.session.rollback()
    db.session.remove()

    return elapsed_ms


def measure_raw_user_query(
    user_id: int,
    sql_profiler: SQLProfiler,
) -> Measurement:
    db.session.remove()

    sql_profiler.reset()

    started = time.perf_counter()

    db.session.execute(
        db.select(
            ChatSecurityService.get_active_user.__self__
            if False
            else db.select
        )
    )

    total_ms = (
        time.perf_counter() - started
    ) * 1000.0

    db.session.rollback()
    db.session.remove()

    return Measurement(
        total_ms=total_ms,
        sql_ms=sql_profiler.sql_ms,
        query_count=sql_profiler.query_count,
    )


def measure_full_security(
    user_id: int,
    conversation_id: int,
    sql_profiler: SQLProfiler,
) -> Measurement:
    db.session.remove()

    sql_profiler.reset()

    started = time.perf_counter()

    ChatSecurityService.ensure_user_can_send_message(
        user_id,
        conversation_id,
    )

    total_ms = (
        time.perf_counter() - started
    ) * 1000.0

    db.session.rollback()
    db.session.remove()

    return Measurement(
        total_ms=total_ms,
        sql_ms=sql_profiler.sql_ms,
        query_count=sql_profiler.query_count,
    )


def print_measurement_summary(
    label: str,
    measurements: list[Measurement],
) -> None:
    totals = [
        item.total_ms
        for item in measurements
    ]

    sql_times = [
        item.sql_ms
        for item in measurements
    ]

    query_counts = [
        item.query_count
        for item in measurements
    ]

    print()
    print(label)
    print("-" * 110)

    print(
        f"Total mean:             "
        f"{statistics.mean(totals):,.3f} ms"
    )

    print(
        f"Total median:           "
        f"{statistics.median(totals):,.3f} ms"
    )

    print(
        f"Total min:              "
        f"{min(totals):,.3f} ms"
    )

    print(
        f"Total max:              "
        f"{max(totals):,.3f} ms"
    )

    print(
        f"SQL mean:               "
        f"{statistics.mean(sql_times):,.3f} ms"
    )

    print(
        f"Queries mean:           "
        f"{statistics.mean(query_counts):,.2f}"
    )

    overheads = [
        max(
            0.0,
            total - sql,
        )
        for total, sql in zip(
            totals,
            sql_times,
        )
    ]

    print(
        f"Non-SQL mean:           "
        f"{statistics.mean(overheads):,.3f} ms"
    )


def print_outliers(
    measurements: list[Measurement],
    label: str,
) -> None:
    if not measurements:
        return

    totals = [
        item.total_ms
        for item in measurements
    ]

    median = statistics.median(
        totals
    )

    threshold = max(
        3.0 * median,
        50.0,
    )

    outliers = [
        (
            index + 1,
            measurement,
        )
        for index, measurement in enumerate(
            measurements
        )
        if measurement.total_ms > threshold
    ]

    print()
    print(
        f"{label} OUTLIERS"
    )
    print("-" * 110)

    if not outliers:
        print(
            "No runs exceeded the outlier threshold."
        )
        return

    print(
        f"Outlier threshold: "
        f"{threshold:,.3f} ms"
    )

    for index, measurement in outliers:
        print(
            f"Run {index:>3}: "
            f"total={measurement.total_ms:,.3f} ms | "
            f"sql={measurement.sql_ms:,.3f} ms | "
            f"queries={measurement.query_count}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Deep profiler for Clinic System Pro "
            "chat security and SQLAlchemy connection behavior."
        )
    )

    parser.add_argument(
        "--user-id",
        type=int,
        default=DEFAULT_USER_ID,
    )

    parser.add_argument(
        "--conversation-id",
        type=int,
        default=DEFAULT_CONVERSATION_ID,
    )

    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_RUNS,
    )

    parser.add_argument(
        "--warmup",
        type=int,
        default=DEFAULT_WARMUP,
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.runs <= 0:
        raise SystemExit(
            "--runs must be a positive integer"
        )

    if args.warmup < 0:
        raise SystemExit(
            "--warmup cannot be negative"
        )

    app = create_app("development")

    with app.app_context():
        engine = db.engine

        sql_profiler = SQLProfiler()
        pool_stats = PoolStats()

        event.listen(
            engine,
            "before_cursor_execute",
            sql_profiler.before_cursor_execute,
        )

        event.listen(
            engine,
            "after_cursor_execute",
            sql_profiler.after_cursor_execute,
        )

        attach_pool_profiler(
            engine,
            pool_stats,
        )

        try:
            print()
            print("=" * 110)
            print(
                "CLINIC SYSTEM PRO v5"
            )
            print(
                "CHAT SECURITY — DEEP ORM / CONNECTION PROFILER"
            )
            print("=" * 110)
            print(
                f"User:                    {args.user_id}"
            )
            print(
                f"Conversation:            {args.conversation_id}"
            )
            print(
                f"Warmup runs:             {args.warmup}"
            )
            print(
                f"Measured runs:           {args.runs}"
            )
            print("=" * 110)

            print()
            print(
                "WARMING UP..."
            )

            for warmup_index in range(
                args.warmup
            ):
                print(
                    f"Warmup "
                    f"{warmup_index + 1}/"
                    f"{args.warmup}"
                )

                measure_get_active_user(
                    args.user_id,
                    sql_profiler,
                )

                measure_full_security(
                    args.user_id,
                    args.conversation_id,
                    sql_profiler,
                )

            print()
            print(
                "WARMUP COMPLETE"
            )

            print()
            print(
                "MEASURING CONNECTION ACQUISITION..."
            )

            connection_times: list[float] = []

            for _ in range(args.runs):
                connection_times.append(
                    measure_connection_acquisition()
                )

            print()
            print(
                "MEASURING get_active_user()..."
            )

            user_measurements: list[Measurement] = []

            for run_index in range(
                args.runs
            ):
                measurement = (
                    measure_get_active_user(
                        args.user_id,
                        sql_profiler,
                    )
                )

                user_measurements.append(
                    measurement
                )

                print(
                    f"Run "
                    f"{run_index + 1:>3}/"
                    f"{args.runs}: "
                    f"{measurement.total_ms:>10,.3f} ms | "
                    f"SQL "
                    f"{measurement.sql_ms:>9,.3f} ms | "
                    f"{measurement.query_count} query(s)"
                )

            print()
            print(
                "MEASURING FULL SECURITY PATH..."
            )

            security_measurements: list[
                Measurement
            ] = []

            for run_index in range(
                args.runs
            ):
                measurement = (
                    measure_full_security(
                        args.user_id,
                        args.conversation_id,
                        sql_profiler,
                    )
                )

                security_measurements.append(
                    measurement
                )

                print(
                    f"Run "
                    f"{run_index + 1:>3}/"
                    f"{args.runs}: "
                    f"{measurement.total_ms:>10,.3f} ms | "
                    f"SQL "
                    f"{measurement.sql_ms:>9,.3f} ms | "
                    f"{measurement.query_count} query(s)"
                )

            print()
            print("=" * 110)
            print(
                "DEEP PROFILE SUMMARY"
            )
            print("=" * 110)

            connection_mean = (
                statistics.mean(
                    connection_times
                )
            )

            connection_median = (
                statistics.median(
                    connection_times
                )
            )

            connection_min = min(
                connection_times
            )

            connection_max = max(
                connection_times
            )

            print(
                f"Connection acquisition mean:   "
                f"{connection_mean:,.3f} ms"
            )

            print(
                f"Connection acquisition median: "
                f"{connection_median:,.3f} ms"
            )

            print(
                f"Connection acquisition min:    "
                f"{connection_min:,.3f} ms"
            )

            print(
                f"Connection acquisition max:    "
                f"{connection_max:,.3f} ms"
            )

            print_measurement_summary(
                "get_active_user()",
                user_measurements,
            )

            print_measurement_summary(
                "ensure_user_can_send_message()",
                security_measurements,
            )

            print_outliers(
                user_measurements,
                "get_active_user()",
            )

            print_outliers(
                security_measurements,
                "ensure_user_can_send_message()",
            )

            print()
            print(
                "POOL EVENTS"
            )
            print("-" * 110)

            print(
                f"Connections created:     "
                f"{pool_stats.connect_count}"
            )

            print(
                f"Checkouts:               "
                f"{pool_stats.checkout_count}"
            )

            print(
                f"Check-ins:               "
                f"{pool_stats.checkin_count}"
            )

            print()
            print("=" * 110)
            print(
                "INTERPRETATION GUIDE"
            )
            print("=" * 110)

            print(
                "1. If connection acquisition spikes with get_active_user(), "
                "the latency is around connection checkout/pool behavior."
            )

            print(
                "2. If connection acquisition stays low but get_active_user() "
                "spikes, investigate ORM/session/result handling."
            )

            print(
                "3. If SQL time spikes with total time, investigate the database/query."
            )

            print(
                "4. If SQL stays low while total time spikes, the delay is outside "
                "SQL execution."
            )

            print(
                "5. Do not refactor authorization until the outlier source is identified."
            )

            print("=" * 110)
            print()

        finally:
            event.remove(
                engine,
                "before_cursor_execute",
                sql_profiler.before_cursor_execute,
            )

            event.remove(
                engine,
                "after_cursor_execute",
                sql_profiler.after_cursor_execute,
            )

            detach_pool_profiler(
                engine,
                pool_stats,
            )

            db.session.remove()


if __name__ == "__main__":
    main()