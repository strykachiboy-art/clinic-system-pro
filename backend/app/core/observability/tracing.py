from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

from flask import Flask, g, request


TRACE_CONTEXT_STATE_KEY = (
    "_clinic_tracing_context"
)

TRACE_ID_HEADER = "X-Trace-ID"
SPAN_ID_HEADER = "X-Span-ID"

MAX_TRACE_ID_LENGTH = 128
MAX_SPAN_NAME_LENGTH = 128

logger = logging.getLogger(__name__)

_current_span_id: ContextVar[str | None] = ContextVar(
    "clinic_current_span_id",
    default=None,
)


def _sanitize_id(
    value: str | None,
    *,
    max_length: int,
) -> str | None:
    if value is None:
        return None

    value = (
        value.strip()
        .replace("\r", "")
        .replace("\n", "")
    )

    if not value:
        return None

    return value[:max_length]


def get_trace_id(
    default: str | None = None,
) -> str | None:
    return getattr(
        g,
        "trace_id",
        default,
    )


def get_span_id(
    default: str | None = None,
) -> str | None:
    return _current_span_id.get(
        default
    )


def _new_id() -> str:
    return uuid4().hex


def _safe_span_name(
    name: str,
) -> str:
    value = _sanitize_id(
        name,
        max_length=MAX_SPAN_NAME_LENGTH,
    )

    if value is None:
        raise ValueError(
            "span name must be non-empty"
        )

    return value


@contextmanager
def trace_span(
    name: str,
    *,
    attributes: dict[str, object] | None = None,
):
    span_name = _safe_span_name(
        name
    )

    trace_id = get_trace_id()

    if trace_id is None:
        trace_id = _new_id()

    parent_span_id = get_span_id()
    span_id = _new_id()

    token = _current_span_id.set(
        span_id
    )

    started_at = time.perf_counter()

    logger.info(
        "trace.span.start",
        extra={
            "trace_event": True,
            "trace_phase": "start",
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "span_name": span_name,
            "attributes": (
                dict(attributes)
                if attributes
                else {}
            ),
        },
    )

    error = None

    try:
        yield {
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "span_name": span_name,
        }
    except Exception as exc:
        error = exc
        raise
    finally:
        duration_ms = (
            time.perf_counter()
            - started_at
        ) * 1000.0

        logger.info(
            "trace.span.end",
            extra={
                "trace_event": True,
                "trace_phase": "end",
                "trace_id": trace_id,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "span_name": span_name,
                "duration_ms": duration_ms,
                "outcome": (
                    "error"
                    if error is not None
                    else "success"
                ),
                "error_type": (
                    type(error).__name__
                    if error is not None
                    else None
                ),
                "attributes": (
                    dict(attributes)
                    if attributes
                    else {}
                ),
            },
        )

        _current_span_id.reset(
            token
        )


def init_tracing(
    app: Flask,
) -> None:
    if app.extensions.get(
        TRACE_CONTEXT_STATE_KEY
    ):
        return

    @app.before_request
    def _tracing_before_request():
        trace_id = _sanitize_id(
            request.headers.get(
                TRACE_ID_HEADER
            ),
            max_length=MAX_TRACE_ID_LENGTH,
        )

        if trace_id is None:
            trace_id = _new_id()

        g.trace_id = trace_id

        root_span = trace_span(
            f"http.{request.method.lower()}",
            attributes={
                "method": request.method,
                "route": (
                    request.url_rule.rule
                    if request.url_rule is not None
                    else request.path
                ),
            },
        )

        root_span.__enter__()

        g._root_trace_span = root_span

    @app.after_request
    def _tracing_after_request(
        response,
    ):
        trace_id = get_trace_id()
        span_id = get_span_id()

        if trace_id:
            response.headers[
                TRACE_ID_HEADER
            ] = trace_id

        if span_id:
            response.headers[
                SPAN_ID_HEADER
            ] = span_id

        root_span = getattr(
            g,
            "_root_trace_span",
            None,
        )

        if root_span is not None:
            root_span.__exit__(
                None,
                None,
                None,
            )

        return response

    @app.teardown_request
    def _tracing_teardown_request(
        error,
    ):
        root_span = getattr(
            g,
            "_root_trace_span",
            None,
        )

        if (
            root_span is not None
            and error is not None
        ):
            root_span.__exit__(
                type(error),
                error,
                error.__traceback__,
            )

    app.extensions[
        TRACE_CONTEXT_STATE_KEY
    ] = {
        "registered": True,
    }
