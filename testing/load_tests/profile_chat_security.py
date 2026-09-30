from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import event

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.extensions import db
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.chat.models.conversation_model import Conversation
from app.modules.chat.services.chat_security_service import (
    ChatSecurityService,
)


DEFAULT_CLINIC_ID = 2
DEFAULT_USER_ID = 5037
DEFAULT_CONVERSATION_ID = 51


@dataclass
class StageResult:
    name: str
    elapsed_ms: float


class SQLProfiler:
    def __init__(self) -> None:
        self.query_count = 0
        self.db_time_ms = 0.0

    def before_cursor_execute(
        self,
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        conn.info.setdefault(
            "security_profile_query_start",
            [],
        ).append(
            time.perf_counter()
        )

    def after_cursor_execute(
        self,
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        starts = conn.info.get(
            "security_profile_query_start",
        )

        if not starts:
            return

        started = starts.pop()

        self.query_count += 1
        self.db_time_ms += (
            time.perf_counter() - started
        ) * 1000.0


def patch_method(
    original_methods: dict[str, Any],
    timings: dict[str, list[float]],
    method_name: str,
) -> None:
    original = getattr(
        ChatSecurityService,
        method_name,
    )

    original_methods[method_name] = original

    def wrapper(
        cls: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        started = time.perf_counter()

        try:
            return original(
                *args,
                **kwargs,
            )
        finally:
            timings.setdefault(
                method_name,
                [],
            ).append(
                (
                    time.perf_counter() - started
                ) * 1000.0
            )

    setattr(
        ChatSecurityService,
        method_name,
        classmethod(wrapper),
    )


def restore_methods(
    original_methods: dict[str, Any],
) -> None:
    for name, original in original_methods.items():
        setattr(
            ChatSecurityService,
            name,
            original,
        )


def main() -> None:
    app = create_app("development")

    original_methods: dict[str, Any] = {}

    timings: dict[str, list[float]] = {}

    methods_to_profile = [
        "get_active_user",
        "ensure_staff_clinic_consistency",
        "get_conversation",
        "ensure_same_clinic",
        "get_participant",
        "ensure_participant_belongs_to_conversation",
        "ensure_user_is_participant",
        "ensure_user_can_access_conversation",
        "ensure_user_can_send_message",
    ]

    for method_name in methods_to_profile:
        patch_method(
            original_methods,
            timings,
            method_name,
        )

    sql_profiler = SQLProfiler()
    total_start = time.perf_counter()

    with app.app_context():
        engine = db.engine

        event.listen(
            engine,
            "before_cursor_execute",
            sql_profiler.before_cursor_execute,
        )

        event.listen(
            engine,
            "after_cursor_execute",
            sql_profiler.after_cursor_execute,
        )

        try:
            db.session.rollback()

            result = ChatSecurityService.ensure_user_can_send_message(
                DEFAULT_USER_ID,
                DEFAULT_CONVERSATION_ID,
            )

            conversation_id = result.id

        except Exception as exc:
            print()
            print(
                f"PROFILE FAILED: "
                f"{type(exc).__name__}: {exc}"
            )
            raise

        finally:
            event.remove(
                engine,
                "before_cursor_execute",
                sql_profiler.before_cursor_execute,
            )

            event.remove(
                engine,
                "after_cursor_execute",
                sql_profiler.after_cursor_execute,
            )

            db.session.rollback()

            restore_methods(
                original_methods
            )

    total_ms = (
        time.perf_counter() - total_start
    ) * 1000.0

    print()
    print("=" * 110)
    print(
        "CHAT SECURITY SERVICE — STAGE PROFILE"
    )
    print("=" * 110)
    print(
        f"Clinic:                  {DEFAULT_CLINIC_ID}"
    )
    print(
        f"User:                    {DEFAULT_USER_ID}"
    )
    print(
        f"Conversation:            {conversation_id}"
    )
    print(
        f"Total service time:      {total_ms:,.3f} ms"
    )
    print(
        f"SQL queries:             {sql_profiler.query_count}"
    )
    print(
        f"SQL execution time:      "
        f"{sql_profiler.db_time_ms:,.3f} ms"
    )
    print("=" * 110)

    print()
    print(
        f"{'Method':<55} "
        f"{'Calls':>8} "
        f"{'Total ms':>14} "
        f"{'Mean ms':>14} "
        f"{'Max ms':>14}"
    )
    print("-" * 110)

    ordered = sorted(
        timings.items(),
        key=lambda item: sum(item[1]),
        reverse=True,
    )

    for method_name, values in ordered:
        total_method_ms = sum(values)
        mean_method_ms = (
            total_method_ms / len(values)
        )

        print(
            f"{method_name:<55} "
            f"{len(values):>8} "
            f"{total_method_ms:>14,.3f} "
            f"{mean_method_ms:>14,.3f} "
            f"{max(values):>14,.3f}"
        )

    print("-" * 110)

    print()
    print(
        "CALL COUNTS / EXECUTION ORDER"
    )
    print("-" * 110)

    for method_name, values in timings.items():
        print(
            f"{method_name:<55} "
            f"{len(values):>3} call(s)"
        )

    print()
    print("=" * 110)
    print()


if __name__ == "__main__":
    main()