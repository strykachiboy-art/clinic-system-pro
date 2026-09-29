from __future__ import annotations

import logging

import pytest

from app.core.observability.tracing import (
    SPAN_ID_HEADER,
    TRACE_ID_HEADER,
    get_span_id,
    get_trace_id,
    trace_span,
)


def _add_route(app):
    @app.get(
        "/__test/observability/trace"
    )
    def trace_route():
        return {
            "trace_id": get_trace_id(),
            "span_id": get_span_id(),
        }


def test_trace_id_is_generated_and_returned(
    app,
    client,
):
    _add_route(app)

    response = client.get(
        "/__test/observability/trace"
    )

    assert response.status_code == 200

    trace_id = response.headers.get(
        TRACE_ID_HEADER
    )

    span_id = response.headers.get(
        SPAN_ID_HEADER
    )

    assert trace_id
    assert span_id
    assert len(trace_id) == 32
    assert len(span_id) == 32


def test_trace_id_header_is_preserved(
    app,
    client,
):
    _add_route(app)

    trace_id = "trace-external-123"

    response = client.get(
        "/__test/observability/trace",
        headers={
            TRACE_ID_HEADER: trace_id,
        },
    )

    assert response.status_code == 200

    assert response.headers[
        TRACE_ID_HEADER
    ] == trace_id


def test_trace_id_is_sanitized():
    from app.core.observability.tracing import (
        _sanitize_id,
        MAX_TRACE_ID_LENGTH,
    )

    value = (
        "A"
        * (MAX_TRACE_ID_LENGTH + 50)
        + "\r\nignored"
    )

    sanitized = _sanitize_id(
        value,
        max_length=MAX_TRACE_ID_LENGTH,
    )

    assert len(sanitized) == (
        MAX_TRACE_ID_LENGTH
    )
    assert "\r" not in sanitized
    assert "\n" not in sanitized


def test_trace_span_emits_start_and_end_logs(
    app,
    caplog,
):
    with app.test_request_context(
        "/__test/observability/trace"
    ):
        from app.core.observability.tracing import (
            init_tracing,
        )

        if not app.extensions.get(
            "_clinic_tracing_context"
        ):
            init_tracing(app)

        with caplog.at_level(
            logging.INFO,
        ):
            app.preprocess_request()

            with trace_span(
                "test.child",
                attributes={
                    "component": "test",
                },
            ) as span:
                assert span["trace_id"]
                assert span["span_id"]
                assert span[
                    "parent_span_id"
                ]

    records = [
        record
        for record in caplog.records
        if getattr(
            record,
            "trace_event",
            False,
        )
        and getattr(
            record,
            "span_name",
            None,
        ) == "test.child"
    ]

    assert len(records) == 2
    assert {
        getattr(
            record,
            "trace_phase",
            None,
        )
        for record in records
    } == {
        "start",
        "end",
    }


def test_trace_span_records_errors(
    app,
    caplog,
):
    with app.test_request_context(
        "/__test/observability/trace"
    ):
        from app.core.observability.tracing import (
            init_tracing,
        )

        if not app.extensions.get(
            "_clinic_tracing_context"
        ):
            init_tracing(app)

        app.preprocess_request()

        with caplog.at_level(
            logging.INFO,
        ):
            with pytest.raises(
                RuntimeError
            ):
                with trace_span(
                    "test.failure"
                ):
                    raise RuntimeError(
                        "synthetic failure"
                    )

    records = [
        record
        for record in caplog.records
        if getattr(
            record,
            "trace_event",
            False,
        )
        and getattr(
            record,
            "span_name",
            None,
        ) == "test.failure"
        and getattr(
            record,
            "trace_phase",
            None,
        ) == "end"
    ]

    assert records
    assert getattr(
        records[-1],
        "outcome",
        None,
    ) == "error"
    assert getattr(
        records[-1],
        "error_type",
        None,
    ) == "RuntimeError"


def test_invalid_span_name_is_rejected():
    with pytest.raises(
        ValueError
    ):
        with trace_span(""):
            pass
