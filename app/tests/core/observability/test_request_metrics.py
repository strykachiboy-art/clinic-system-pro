from __future__ import annotations

import logging

from flask import jsonify

from app.tests.core.observability.conftest import init_request_metrics


def _add_test_route(app):
    @app.get("/__test/observability/request/<int:item_id>")
    def request_metrics_test_route(item_id: int):
        return jsonify(
            {
                "success": True,
                "item_id": item_id,
            }
        )


def _get_performance_request_record(caplog):
    records = [
        record
        for record in caplog.records
        if record.getMessage() == "performance.request"
    ]

    assert records, "Expected a performance.request log record."
    return records[-1]


def _get_performance_request_records(caplog):
    return [
        record
        for record in caplog.records
        if record.getMessage() == "performance.request"
    ]


def test_request_metrics_records_request_data(
    app,
    client,
    caplog,
):
    init_request_metrics(app)
    _add_test_route(app)

    with caplog.at_level(logging.INFO, logger=app.logger.name):
        response = client.get(
            "/__test/observability/request/123"
        )

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "item_id": 123,
    }

    record = _get_performance_request_record(caplog)

    assert getattr(record, "method", None) == "GET"
    assert getattr(record, "route", None) == (
        "/__test/observability/request/<int:item_id>"
    )
    assert getattr(record, "status", None) == 200

    duration_ms = getattr(record, "duration_ms", None)

    assert isinstance(duration_ms, (int, float))
    assert duration_ms >= 0


def test_request_metrics_uses_route_template_not_raw_path(
    app,
    client,
    caplog,
):
    init_request_metrics(app)
    _add_test_route(app)

    with caplog.at_level(logging.INFO, logger=app.logger.name):
        response = client.get(
            "/__test/observability/request/987654"
        )

    assert response.status_code == 200

    record = _get_performance_request_record(caplog)

    assert getattr(record, "route", None) == (
        "/__test/observability/request/<int:item_id>"
    )
    assert getattr(record, "route", None) != (
        "/__test/observability/request/987654"
    )


def test_request_metrics_records_db_fields(
    app,
    client,
    caplog,
):
    init_request_metrics(app)
    _add_test_route(app)

    with caplog.at_level(logging.INFO, logger=app.logger.name):
        response = client.get(
            "/__test/observability/request/55"
        )

    assert response.status_code == 200

    record = _get_performance_request_record(caplog)

    query_count = getattr(record, "db_query_count", None)
    db_time_ms = getattr(record, "db_time_ms", None)

    assert isinstance(query_count, int)
    assert query_count >= 0

    assert isinstance(db_time_ms, (int, float))
    assert db_time_ms >= 0


def test_request_metrics_records_load_test_id(
    app,
    client,
    caplog,
):
    init_request_metrics(app)
    _add_test_route(app)

    load_test_id = "clinic-load-20260921-001"

    with caplog.at_level(logging.INFO, logger=app.logger.name):
        response = client.get(
            "/__test/observability/request/123",
            headers={
                "X-Load-Test-ID": load_test_id,
            },
        )

    assert response.status_code == 200

    record = _get_performance_request_record(caplog)

    assert getattr(record, "load_test_id", None) == load_test_id


def test_request_metrics_does_not_create_load_test_id_when_missing(
    app,
    client,
    caplog,
):
    init_request_metrics(app)
    _add_test_route(app)

    with caplog.at_level(logging.INFO, logger=app.logger.name):
        response = client.get(
            "/__test/observability/request/123"
        )

    assert response.status_code == 200

    record = _get_performance_request_record(caplog)

    assert getattr(record, "load_test_id", None) is None


def test_request_metrics_records_client_error_status(
    app,
    client,
    caplog,
):
    init_request_metrics(app)

    @app.get("/__test/observability/request-400")
    def request_metrics_400_route():
        return jsonify(
            {
                "success": False,
            }
        ), 400

    with caplog.at_level(logging.INFO, logger=app.logger.name):
        response = client.get(
            "/__test/observability/request-400"
        )

    assert response.status_code == 400

    record = _get_performance_request_record(caplog)

    assert getattr(record, "method", None) == "GET"
    assert getattr(record, "route", None) == (
        "/__test/observability/request-400"
    )
    assert getattr(record, "status", None) == 400

    duration_ms = getattr(record, "duration_ms", None)

    assert isinstance(duration_ms, (int, float))
    assert duration_ms >= 0


def test_request_metrics_records_server_error_status(
    app,
    client,
    caplog,
):
    init_request_metrics(app)

    @app.get("/__test/observability/request-500")
    def request_metrics_500_route():
        return jsonify(
            {
                "success": False,
            }
        ), 500

    with caplog.at_level(logging.INFO, logger=app.logger.name):
        response = client.get(
            "/__test/observability/request-500"
        )

    assert response.status_code == 500

    record = _get_performance_request_record(caplog)

    assert getattr(record, "method", None) == "GET"
    assert getattr(record, "route", None) == (
        "/__test/observability/request-500"
    )
    assert getattr(record, "status", None) == 500

    duration_ms = getattr(record, "duration_ms", None)

    assert isinstance(duration_ms, (int, float))
    assert duration_ms >= 0


def test_request_metrics_records_post_method(
    app,
    client,
    caplog,
):
    init_request_metrics(app)

    @app.post("/__test/observability/request-post")
    def request_metrics_post_route():
        return jsonify(
            {
                "success": True,
            }
        )

    with caplog.at_level(logging.INFO, logger=app.logger.name):
        response = client.post(
            "/__test/observability/request-post"
        )

    assert response.status_code == 200

    record = _get_performance_request_record(caplog)

    assert getattr(record, "method", None) == "POST"
    assert getattr(record, "route", None) == (
        "/__test/observability/request-post"
    )
    assert getattr(record, "status", None) == 200


def test_request_metrics_records_each_request_separately(
    app,
    client,
    caplog,
):
    init_request_metrics(app)
    _add_test_route(app)

    with caplog.at_level(logging.INFO, logger=app.logger.name):
        first_response = client.get(
            "/__test/observability/request/1",
            headers={
                "X-Load-Test-ID": "load-test-001",
            },
        )
        second_response = client.get(
            "/__test/observability/request/2",
            headers={
                "X-Load-Test-ID": "load-test-002",
            },
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    records = _get_performance_request_records(caplog)

    assert len(records) == 2

    assert getattr(records[0], "method", None) == "GET"
    assert getattr(records[0], "route", None) == (
        "/__test/observability/request/<int:item_id>"
    )
    assert getattr(records[0], "status", None) == 200
    assert getattr(records[0], "load_test_id", None) == (
        "load-test-001"
    )

    assert getattr(records[1], "method", None) == "GET"
    assert getattr(records[1], "route", None) == (
        "/__test/observability/request/<int:item_id>"
    )
    assert getattr(records[1], "status", None) == 200
    assert getattr(records[1], "load_test_id", None) == (
        "load-test-002"
    )

    assert getattr(records[0], "duration_ms", None) >= 0
    assert getattr(records[1], "duration_ms", None) >= 0


def test_request_metrics_does_not_register_twice(
    app,
    client,
    caplog,
):
    init_request_metrics(app)
    init_request_metrics(app)
    _add_test_route(app)

    with caplog.at_level(logging.INFO, logger=app.logger.name):
        response = client.get(
            "/__test/observability/request/1",
            headers={
                "X-Load-Test-ID": "load-test-001",
            },
        )

    assert response.status_code == 200

    records = [
        record
        for record in caplog.records
        if record.getMessage() == "performance.request"
    ]

    assert len(records) == 1