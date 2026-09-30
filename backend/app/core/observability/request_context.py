from __future__ import annotations

from uuid import uuid4

from flask import Flask, g, request


REQUEST_CONTEXT_STATE_KEY = "_clinic_request_context"
REQUEST_ID_HEADER = "X-Request-ID"
MAX_REQUEST_ID_LENGTH = 128


def _sanitize_request_id(
    value: str | None,
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

    return value[:MAX_REQUEST_ID_LENGTH]


def get_request_id(
    default: str | None = None,
) -> str | None:
    return getattr(
        g,
        "request_id",
        default,
    )


def init_request_context(
    app: Flask,
) -> None:
    if app.extensions.get(
        REQUEST_CONTEXT_STATE_KEY
    ):
        return

    @app.before_request
    def _request_context_before_request():
        request_id = _sanitize_request_id(
            request.headers.get(
                REQUEST_ID_HEADER
            )
        )

        g.request_id = (
            request_id
            or uuid4().hex
        )

    @app.after_request
    def _request_context_after_request(
        response,
    ):
        request_id = get_request_id()

        if request_id:
            response.headers[
                REQUEST_ID_HEADER
            ] = request_id

        return response

    app.extensions[
        REQUEST_CONTEXT_STATE_KEY
    ] = {
        "registered": True,
    }
