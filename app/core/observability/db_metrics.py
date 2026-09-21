from __future__ import annotations

import time
from weakref import WeakKeyDictionary

from flask import g, has_request_context
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.extensions import db


DB_METRICS_STATE_KEY = "_clinic_db_metrics"

_REGISTERED_ENGINES = WeakKeyDictionary()


def _get_request_db_state() -> dict:
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

    return state


def _before_cursor_execute(
    conn,
    cursor,
    statement,
    parameters,
    context,
    executemany,
):
    if not has_request_context():
        return

    state = _get_request_db_state()

    state["query_count"] += 1
    state["query_stack"].append(
        time.perf_counter()
    )


def _after_cursor_execute(
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

    if not state:
        return

    if not state["query_stack"]:
        return

    started_at = state["query_stack"].pop()

    state["db_time_ms"] += (
        time.perf_counter() - started_at
    ) * 1000.0


def init_db_metrics(app) -> None:
    if app.extensions.get(DB_METRICS_STATE_KEY):
        return

    with app.app_context():
        engine: Engine = db.engine

    if engine not in _REGISTERED_ENGINES:
        event.listen(
            engine,
            "before_cursor_execute",
            _before_cursor_execute,
        )

        event.listen(
            engine,
            "after_cursor_execute",
            _after_cursor_execute,
        )

        _REGISTERED_ENGINES[engine] = True

    app.extensions[DB_METRICS_STATE_KEY] = {
        "engine": engine,
        "registered": True,
    }