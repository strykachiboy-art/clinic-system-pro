from __future__ import annotations

import logging

from app.tests.core.observability.conftest import (
    aggregate_performance_metrics,
)


def _make_record(
    *,
    created: float,
    duration_ms: float,
    status: int,
    response_size_bytes: int,
    db_query_count: int,
    db_time_ms: float,
):
    record = logging.LogRecord(
        name="app",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="performance.request",
        args=(),
        exc_info=None,
    )

    record.created = created
    record.duration_ms = duration_ms
    record.status = status
    record.response_size_bytes = response_size_bytes
    record.db_query_count = db_query_count
    record.db_time_ms = db_time_ms

    return record


def test_aggregate_metrics_counts_requests_and_failures():
    records = [
        _make_record(
            created=100.0,
            duration_ms=10.0,
            status=200,
            response_size_bytes=100,
            db_query_count=2,
            db_time_ms=1.0,
        ),
        _make_record(
            created=101.0,
            duration_ms=20.0,
            status=201,
            response_size_bytes=200,
            db_query_count=3,
            db_time_ms=2.0,
        ),
        _make_record(
            created=102.0,
            duration_ms=30.0,
            status=400,
            response_size_bytes=300,
            db_query_count=1,
            db_time_ms=3.0,
        ),
        _make_record(
            created=103.0,
            duration_ms=40.0,
            status=500,
            response_size_bytes=400,
            db_query_count=4,
            db_time_ms=4.0,
        ),
    ]

    metrics = aggregate_performance_metrics(records)

    assert metrics["total_requests"] == 4
    assert metrics["total_failures"] == 2
    assert metrics["failure_rate"] == 0.5


def test_aggregate_metrics_calculates_duration_statistics():
    records = [
        _make_record(
            created=100.0,
            duration_ms=10.0,
            status=200,
            response_size_bytes=100,
            db_query_count=0,
            db_time_ms=0.0,
        ),
        _make_record(
            created=101.0,
            duration_ms=20.0,
            status=200,
            response_size_bytes=100,
            db_query_count=0,
            db_time_ms=0.0,
        ),
        _make_record(
            created=102.0,
            duration_ms=30.0,
            status=200,
            response_size_bytes=100,
            db_query_count=0,
            db_time_ms=0.0,
        ),
        _make_record(
            created=103.0,
            duration_ms=40.0,
            status=200,
            response_size_bytes=100,
            db_query_count=0,
            db_time_ms=0.0,
        ),
        _make_record(
            created=104.0,
            duration_ms=50.0,
            status=200,
            response_size_bytes=100,
            db_query_count=0,
            db_time_ms=0.0,
        ),
    ]

    metrics = aggregate_performance_metrics(records)

    assert metrics["average_duration_ms"] == 30.0
    assert metrics["median_duration_ms"] == 30.0
    assert metrics["p95_duration_ms"] == 48.0
    assert metrics["p99_duration_ms"] == 49.6
    assert metrics["min_duration_ms"] == 10.0
    assert metrics["max_duration_ms"] == 50.0


def test_aggregate_metrics_calculates_response_size():
    records = [
        _make_record(
            created=100.0,
            duration_ms=10.0,
            status=200,
            response_size_bytes=100,
            db_query_count=0,
            db_time_ms=0.0,
        ),
        _make_record(
            created=101.0,
            duration_ms=10.0,
            status=200,
            response_size_bytes=300,
            db_query_count=0,
            db_time_ms=0.0,
        ),
        _make_record(
            created=102.0,
            duration_ms=10.0,
            status=200,
            response_size_bytes=500,
            db_query_count=0,
            db_time_ms=0.0,
        ),
    ]

    metrics = aggregate_performance_metrics(records)

    assert metrics["average_response_size_bytes"] == 300.0


def test_aggregate_metrics_sums_database_metrics():
    records = [
        _make_record(
            created=100.0,
            duration_ms=10.0,
            status=200,
            response_size_bytes=100,
            db_query_count=2,
            db_time_ms=1.5,
        ),
        _make_record(
            created=101.0,
            duration_ms=20.0,
            status=200,
            response_size_bytes=100,
            db_query_count=5,
            db_time_ms=3.5,
        ),
        _make_record(
            created=102.0,
            duration_ms=30.0,
            status=200,
            response_size_bytes=100,
            db_query_count=1,
            db_time_ms=2.0,
        ),
    ]

    metrics = aggregate_performance_metrics(records)

    assert metrics["total_db_queries"] == 8
    assert metrics["total_db_time_ms"] == 7.0


def test_aggregate_metrics_calculates_throughput():
    records = [
        _make_record(
            created=100.0,
            duration_ms=100.0,
            status=200,
            response_size_bytes=100,
            db_query_count=0,
            db_time_ms=0.0,
        ),
        _make_record(
            created=101.0,
            duration_ms=100.0,
            status=200,
            response_size_bytes=100,
            db_query_count=0,
            db_time_ms=0.0,
        ),
        _make_record(
            created=102.0,
            duration_ms=100.0,
            status=200,
            response_size_bytes=100,
            db_query_count=0,
            db_time_ms=0.0,
        ),
    ]

    metrics = aggregate_performance_metrics(records)

    assert metrics["rps"] > 0
    assert metrics["rps"] < 4


def test_aggregate_metrics_handles_empty_records():
    metrics = aggregate_performance_metrics([])

    assert metrics["total_requests"] == 0
    assert metrics["total_failures"] == 0
    assert metrics["failure_rate"] == 0.0
    assert metrics["rps"] == 0.0
    assert metrics["average_duration_ms"] == 0.0
    assert metrics["median_duration_ms"] == 0.0
    assert metrics["p95_duration_ms"] == 0.0
    assert metrics["p99_duration_ms"] == 0.0
    assert metrics["min_duration_ms"] == 0.0
    assert metrics["max_duration_ms"] == 0.0
    assert metrics["average_response_size_bytes"] == 0.0
    assert metrics["total_db_queries"] == 0
    assert metrics["total_db_time_ms"] == 0.0