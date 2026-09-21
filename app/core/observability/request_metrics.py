from __future__ import annotations

import time

from flask import Flask, g, request


REQUEST_METRICS_STATE_KEY = "_clinic_request_metrics"
MAX_LOAD_TEST_ID_LENGTH = 128


def _get_load_test_id() -> str | None:
    value = request.headers.get(
        "X-Load-Test-ID"
    )

    if value is None:
        return None

    value = (
        value.strip()
        .replace("\r", "")
        .replace("\n", "")
    )

    if not value:
        return None

    return value[:MAX_LOAD_TEST_ID_LENGTH]


def init_request_metrics(app: Flask) -> None:
    if app.extensions.get(
        REQUEST_METRICS_STATE_KEY
    ):
        return

    logger = app.logger

    @app.before_request
    def _request_metrics_before_request():
        g._request_metrics_started_at = (
            time.perf_counter()
        )

        if not hasattr(
            g,
            "_db_metrics_state",
        ):
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
                time.perf_counter()
                - started_at
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

        load_test_id = _get_load_test_id()

        logger.info(
            (
                "performance.request "
                "load_test_id=%s "
                "method=%s "
                "route=%s "
                "status=%s "
                "duration_ms=%.3f "
                "response_size_bytes=%s "
                "db_query_count=%s "
                "db_time_ms=%.3f"
            ),
            load_test_id,
            request.method,
            route,
            response.status_code,
            duration_ms,
            int(response_size_bytes),
            query_count,
            db_time_ms,
            extra={
                "performance_event": True,
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

    app.extensions[
        REQUEST_METRICS_STATE_KEY
    ] = {
        "registered": True,
    }