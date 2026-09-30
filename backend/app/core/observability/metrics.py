from __future__ import annotations

import statistics


def _percentile(
    values: list[float],
    percentile: float,
) -> float:
    if not 0.0 <= percentile <= 1.0:
        raise ValueError(
            "percentile must be between 0.0 and 1.0"
        )

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
        - (
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

    ends = [
        float(record.created)
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