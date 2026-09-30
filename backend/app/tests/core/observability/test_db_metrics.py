from __future__ import annotations

import logging

from flask import jsonify
from sqlalchemy import text

from app.extensions import db
from app.tests.core.observability.conftest import (
    init_db_metrics,
    init_request_metrics,
)


def _add_db_test_route(app):
    @app.get("/__test/observability/db")
    def db_metrics_test_route():
        db.session.execute(text("SELECT 1"))
        db.session.execute(text("SELECT 2"))

        return jsonify(
            {
                "success": True,
            }
        )


def _get_performance_request_record(caplog):
    records = [
        record
        for record in caplog.records
        if getattr(
            record,
            "performance_event",
            False,
        )
    ]

    assert records, (
        "Expected a performance.request log record."
    )

    return records[-1]


def test_db_metrics_counts_queries_and_records_time(
    app,
    client,
    caplog,
):
    init_db_metrics(app)
    init_request_metrics(app)
    _add_db_test_route(app)

    with caplog.at_level(
        logging.INFO,
        logger=app.logger.name,
    ):
        response = client.get(
            "/__test/observability/db"
        )

    assert response.status_code == 200

    assert response.get_json() == {
        "success": True,
    }

    record = _get_performance_request_record(
        caplog
    )

    query_count = getattr(
        record,
        "db_query_count",
        None,
    )

    db_time_ms = getattr(
        record,
        "db_time_ms",
        None,
    )

    assert isinstance(
        query_count,
        int,
    )

    assert query_count >= 2

    assert isinstance(
        db_time_ms,
        (int, float),
    )

    assert db_time_ms >= 0


def test_db_metrics_records_only_database_execution_time(
    app,
    client,
    caplog,
):
    init_db_metrics(app)
    init_request_metrics(app)

    @app.get("/__test/observability/db-single")
    def db_single_query_route():
        db.session.execute(
            text("SELECT 1")
        )

        return jsonify(
            {
                "success": True,
            }
        )

    with caplog.at_level(
        logging.INFO,
        logger=app.logger.name,
    ):
        response = client.get(
            "/__test/observability/db-single"
        )

    assert response.status_code == 200

    record = _get_performance_request_record(
        caplog
    )

    query_count = getattr(
        record,
        "db_query_count",
        None,
    )

    db_time_ms = getattr(
        record,
        "db_time_ms",
        None,
    )

    request_duration_ms = getattr(
        record,
        "duration_ms",
        None,
    )

    assert isinstance(
        query_count,
        int,
    )

    assert query_count >= 1

    assert isinstance(
        db_time_ms,
        (int, float),
    )

    assert db_time_ms >= 0

    assert isinstance(
        request_duration_ms,
        (int, float),
    )

    assert request_duration_ms >= 0

    assert db_time_ms <= request_duration_ms


def test_db_metrics_counts_multiple_queries(
    app,
    client,
    caplog,
):
    init_db_metrics(app)
    init_request_metrics(app)

    @app.get(
        "/__test/observability/db-multiple"
    )
    def db_multiple_queries_route():
        db.session.execute(
            text("SELECT 1")
        )

        db.session.execute(
            text("SELECT 2")
        )

        db.session.execute(
            text("SELECT 3")
        )

        db.session.execute(
            text("SELECT 4")
        )

        return jsonify(
            {
                "success": True,
            }
        )

    with caplog.at_level(
        logging.INFO,
        logger=app.logger.name,
    ):
        response = client.get(
            "/__test/observability/db-multiple"
        )

    assert response.status_code == 200

    record = _get_performance_request_record(
        caplog
    )

    query_count = getattr(
        record,
        "db_query_count",
        None,
    )

    db_time_ms = getattr(
        record,
        "db_time_ms",
        None,
    )

    assert isinstance(
        query_count,
        int,
    )

    assert query_count >= 4

    assert isinstance(
        db_time_ms,
        (int, float),
    )

    assert db_time_ms >= 0


def test_db_metrics_records_zero_for_request_without_database_queries(
    app,
    client,
    caplog,
):
    init_db_metrics(app)
    init_request_metrics(app)

    @app.get("/__test/observability/db-zero")
    def db_zero_query_route():
        return jsonify(
            {
                "success": True,
            }
        )

    with caplog.at_level(
        logging.INFO,
        logger=app.logger.name,
    ):
        response = client.get(
            "/__test/observability/db-zero"
        )

    assert response.status_code == 200

    record = _get_performance_request_record(
        caplog
    )

    query_count = getattr(
        record,
        "db_query_count",
        None,
    )

    db_time_ms = getattr(
        record,
        "db_time_ms",
        None,
    )

    assert query_count == 0

    assert isinstance(
        db_time_ms,
        (int, float),
    )

    assert db_time_ms >= 0


def test_db_metrics_does_not_count_queries_outside_request(
    app,
    client,
    caplog,
):
    init_db_metrics(app)
    init_request_metrics(app)

    with app.app_context():
        db.session.execute(
            text("SELECT 1")
        )

    @app.get(
        "/__test/observability/db-after-context"
    )
    def db_after_context_route():
        db.session.execute(
            text("SELECT 2")
        )

        return jsonify(
            {
                "success": True,
            }
        )

    with caplog.at_level(
        logging.INFO,
        logger=app.logger.name,
    ):
        response = client.get(
            "/__test/observability/db-after-context"
        )

    assert response.status_code == 200

    record = _get_performance_request_record(
        caplog
    )

    query_count = getattr(
        record,
        "db_query_count",
        None,
    )

    db_time_ms = getattr(
        record,
        "db_time_ms",
        None,
    )

    assert query_count == 1

    assert isinstance(
        db_time_ms,
        (int, float),
    )

    assert db_time_ms >= 0


def test_db_metrics_does_not_register_twice(
    app,
    client,
    caplog,
):
    init_db_metrics(app)
    init_db_metrics(app)
    init_request_metrics(app)

    @app.get(
        "/__test/observability/db-duplicate"
    )
    def db_duplicate_route():
        db.session.execute(
            text("SELECT 1")
        )

        return jsonify(
            {
                "success": True,
            }
        )

    with caplog.at_level(
        logging.INFO,
        logger=app.logger.name,
    ):
        response = client.get(
            "/__test/observability/db-duplicate"
        )

    assert response.status_code == 200

    record = _get_performance_request_record(
        caplog
    )

    query_count = getattr(
        record,
        "db_query_count",
        None,
    )

    assert isinstance(
        query_count,
        int,
    )

    assert query_count >= 1
    assert query_count < 3