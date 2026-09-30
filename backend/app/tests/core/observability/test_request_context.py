from __future__ import annotations

import logging

from flask import jsonify

from app.core.observability.request_context import (
    MAX_REQUEST_ID_LENGTH,
    REQUEST_ID_HEADER,
)


def _add_test_route(app):
    @app.get(
        "/__test/observability/context"
    )
    def request_context_test_route():
        return jsonify(
            {
                "success": True,
            }
        )


def test_request_id_is_generated_and_returned(
    app,
    client,
):
    _add_test_route(app)

    response = client.get(
        "/__test/observability/context"
    )

    assert response.status_code == 200

    request_id = response.headers.get(
        REQUEST_ID_HEADER
    )

    assert request_id
    assert len(request_id) == 32
    assert request_id.isalnum()


def test_request_id_header_is_preserved_after_sanitization(
    app,
    client,
):
    _add_test_route(app)

    request_id = "external-request-123"

    response = client.get(
        "/__test/observability/context",
        headers={
            REQUEST_ID_HEADER: request_id,
        },
    )

    assert response.status_code == 200

    assert response.headers[
        REQUEST_ID_HEADER
    ] == request_id


def test_request_id_is_bounded_and_newline_safe():
    from app.core.observability.request_context import (
        _sanitize_request_id,
    )

    request_id = (
        "A"
        * (MAX_REQUEST_ID_LENGTH + 20)
        + "\r\nignored"
    )

    sanitized = _sanitize_request_id(
        request_id
    )

    assert len(sanitized) == (
        MAX_REQUEST_ID_LENGTH
    )
    assert "\r" not in sanitized
    assert "\n" not in sanitized


def test_request_id_is_attached_to_performance_log(
    app,
    client,
    caplog,
):
    _add_test_route(app)

    request_id = "correlation-test-123"

    with caplog.at_level(
        logging.INFO,
        logger=app.logger.name,
    ):
        response = client.get(
            "/__test/observability/context",
            headers={
                REQUEST_ID_HEADER: request_id,
            },
        )

    assert response.status_code == 200

    records = [
        record
        for record in caplog.records
        if getattr(
            record,
            "performance_event",
            False,
        )
    ]

    assert records

    assert getattr(
        records[-1],
        "request_id",
        None,
    ) == request_id


def test_unexpected_errors_log_safe_request_context(
    app,
    client,
    caplog,
):
    @app.get(
        "/__test/observability/error"
    )
    def error_route():
        raise RuntimeError(
            "synthetic internal failure"
        )

    request_id = "error-correlation-123"

    with caplog.at_level(
        logging.ERROR,
    ):
        response = client.get(
            "/__test/observability/error",
            headers={
                REQUEST_ID_HEADER: request_id,
            },
        )

    assert response.status_code == 500

    records = [
        record
        for record in caplog.records
        if getattr(
            record,
            "event",
            None,
        ) == "application.error"
    ]

    assert records

    record = records[-1]

    assert getattr(
        record,
        "request_id",
        None,
    ) == request_id

    assert getattr(
        record,
        "method",
        None,
    ) == "GET"

    assert getattr(
        record,
        "status",
        None,
    ) == 500

    assert getattr(
        record,
        "error_type",
        None,
    ) == "RuntimeError"
