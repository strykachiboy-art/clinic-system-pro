from __future__ import annotations

from app.core.observability.db_metrics import (
    init_db_metrics,
)
from app.core.observability.metrics import (
    aggregate_performance_metrics,
)
from app.core.observability.request_metrics import (
    init_request_metrics,
)


__all__ = [
    "aggregate_performance_metrics",
    "init_db_metrics",
    "init_request_metrics",
]
import logging
import statistics
import time

from flask import Flask, g, has_request_context, request
from sqlalchemy import event

from app.extensions import db


DB_METRICS_STATE_KEY = "_clinic_db_metrics"
REQUEST_METRICS_STATE_KEY = "_clinic_request_metrics"


def init_db_metrics(app: Flask) -> None:
    if app.extensions.get(DB_METRICS_STATE_KEY):
        return

    with app.app_context():
        engine = db.engine

    def before_cursor_execute(
        conn,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ):
        if not has_request_context():
            return

        state = getattr(
            g,
            "_db_metrics_state",
            None,
        )

        if state is None:
            state = {
                "query_count": 0,
                "db_time_ms": 0.0,
                "query_stack": [],
            }
            g._db_metrics_state = state

        state["query_count"] += 1
        state["query_stack"].append(
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
        if not has_request_context():
            return

        state = getattr(
            g,
            "_db_metrics_state",
            None,
        )

        if not state or not state["query_stack"]:
            return

        started_at = state["query_stack"].pop()

        state["db_time_ms"] += (
            time.perf_counter() - started_at
        ) * 1000.0

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

    app.extensions[DB_METRICS_STATE_KEY] = {
        "engine": engine,
        "before_cursor_execute": before_cursor_execute,
        "after_cursor_execute": after_cursor_execute,
    }


def init_request_metrics(app: Flask) -> None:
    if app.extensions.get(REQUEST_METRICS_STATE_KEY):
        return

    logger = app.logger

    @app.before_request
    def _request_metrics_before_request():
        g._request_metrics_started_at = time.perf_counter()

        if not hasattr(g, "_db_metrics_state"):
            g._db_metrics_state = {
                "query_count": 0,
                "db_time_ms": 0.0,
                "query_stack": [],
            }

    @app.after_request
    def _request_metrics_after_request(response):
        started_at = getattr(
            g,
            "_request_metrics_started_at",
            None,
        )

        if started_at is None:
            duration_ms = 0.0
        else:
            duration_ms = (
                time.perf_counter() - started_at
            ) * 1000.0

        db_state = getattr(
            g,
            "_db_metrics_state",
            None,
        )

        if db_state is None:
            query_count = 0
            db_time_ms = 0.0
        else:
            query_count = int(
                db_state.get(
                    "query_count",
                    0,
                )
            )
            db_time_ms = float(
                db_state.get(
                    "db_time_ms",
                    0.0,
                )
            )

        route = None

        if request.url_rule is not None:
            route = request.url_rule.rule

        response_size_bytes = (
            response.calculate_content_length()
        )

        if response_size_bytes is None:
            response_size_bytes = 0

        load_test_id = request.headers.get(
            "X-Load-Test-ID"
        )

        logger.info(
            "performance.request",
            extra={
                "load_test_id": load_test_id,
                "method": request.method,
                "route": route,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "response_size_bytes": int(
                    response_size_bytes
                ),
                "db_query_count": query_count,
                "db_time_ms": db_time_ms,
            },
        )

        return response

    app.extensions[REQUEST_METRICS_STATE_KEY] = True


def _percentile(
    values: list[float],
    percentile: float,
) -> float:
    if not values:
        return 0.0

    if len(values) == 1:
        return float(values[0])

    ordered = sorted(values)

    position = (
        len(ordered) - 1
    ) * percentile

    lower = int(position)
    upper = lower + 1

    if upper >= len(ordered):
        return float(ordered[-1])

    weight = position - lower

    return (
        ordered[lower]
        + (
            ordered[upper]
            - ordered[lower]
        )
        * weight
    )


def aggregate_performance_metrics(
    records,
) -> dict[str, float | int]:
    records = list(records)

    if not records:
        return {
            "total_requests": 0,
            "total_failures": 0,
            "failure_rate": 0.0,
            "rps": 0.0,
            "average_duration_ms": 0.0,
            "median_duration_ms": 0.0,
            "p95_duration_ms": 0.0,
            "p99_duration_ms": 0.0,
            "min_duration_ms": 0.0,
            "max_duration_ms": 0.0,
            "average_response_size_bytes": 0.0,
            "total_db_queries": 0,
            "total_db_time_ms": 0.0,
        }

    durations = [
        float(
            getattr(
                record,
                "duration_ms",
                0.0,
            )
        )
        for record in records
    ]

    response_sizes = [
        int(
            getattr(
                record,
                "response_size_bytes",
                0,
            )
        )
        for record in records
    ]

    db_query_counts = [
        int(
            getattr(
                record,
                "db_query_count",
                0,
            )
        )
        for record in records
    ]

    db_times = [
        float(
            getattr(
                record,
                "db_time_ms",
                0.0,
            )
        )
        for record in records
    ]

    total_requests = len(records)

    total_failures = sum(
        1
        for record in records
        if int(
            getattr(
                record,
                "status",
                0,
            )
        ) >= 400
    )

    starts = [
        float(record.created)
        for record in records
    ]

    ends = [
        float(record.created)
        + (
            float(
                getattr(
                    record,
                    "duration_ms",
                    0.0,
                )
            )
            / 1000.0
        )
        for record in records
    ]

    window_seconds = (
        max(ends)
        - min(starts)
    )

    if window_seconds <= 0:
        window_seconds = max(
            max(
                durations,
                default=0.0,
            )
            / 1000.0,
            0.001,
        )

    return {
        "total_requests": total_requests,
        "total_failures": total_failures,
        "failure_rate": (
            total_failures
            / total_requests
        ),
        "rps": (
            total_requests
            / window_seconds
        ),
        "average_duration_ms": (
            statistics.fmean(durations)
        ),
        "median_duration_ms": (
            statistics.median(durations)
        ),
        "p95_duration_ms": _percentile(
            durations,
            0.95,
        ),
        "p99_duration_ms": _percentile(
            durations,
            0.99,
        ),
        "min_duration_ms": min(durations),
        "max_duration_ms": max(durations),
        "average_response_size_bytes": (
            statistics.fmean(
                response_sizes
            )
        ),
        "total_db_queries": sum(
            db_query_counts
        ),
        "total_db_time_ms": sum(
            db_times
        ),
    }