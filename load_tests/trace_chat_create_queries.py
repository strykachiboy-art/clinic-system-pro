from __future__ import annotations

import sys
import time
from pathlib import Path

from sqlalchemy import event


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app import create_app
from app.extensions import db

from app.modules.chat.services.message_service import create_message


CLINIC_ID = 2
USER_ID = 5037
CONVERSATION_ID = 51


def main() -> None:
    app = create_app("development")

    queries: list[dict[str, object]] = []

    with app.app_context():
        def before_cursor_execute(
            conn,
            cursor,
            statement,
            parameters,
            context,
            executemany,
        ):
            queries.append(
                {
                    "started": time.perf_counter(),
                    "statement": statement,
                    "parameters": parameters,
                }
            )

        def after_cursor_execute(
            conn,
            cursor,
            statement,
            parameters,
            context,
            executemany,
        ):
            if not queries:
                return

            entry = queries[-1]

            started = entry.get("started")

            if isinstance(
                started,
                float,
            ):
                entry["duration_ms"] = (
                    time.perf_counter()
                    - started
                ) * 1000

        event.listen(
            db.engine,
            "before_cursor_execute",
            before_cursor_execute,
        )

        event.listen(
            db.engine,
            "after_cursor_execute",
            after_cursor_execute,
        )

        try:
            started = time.perf_counter()

            message = create_message(
                clinic_id=CLINIC_ID,
                conversation_id=CONVERSATION_ID,
                sender_id=USER_ID,
                content=(
                    "SQL trace benchmark message "
                    f"{time.time_ns()}"
                ),
            )

            elapsed_ms = (
                time.perf_counter()
                - started
            ) * 1000

        finally:
            event.remove(
                db.engine,
                "before_cursor_execute",
                before_cursor_execute,
            )

            event.remove(
                db.engine,
                "after_cursor_execute",
                after_cursor_execute,
            )

            db.session.rollback()

        print("=" * 110)
        print("CHAT CREATE_MESSAGE — FRESH SQL TRACE")
        print("=" * 110)
        print(
            f"Clinic:        {CLINIC_ID}"
        )
        print(
            f"User:          {USER_ID}"
        )
        print(
            f"Conversation:  {CONVERSATION_ID}"
        )
        print(
            f"Message ID:    {message.id}"
        )
        print(
            f"Total time:    {elapsed_ms:.3f} ms"
        )
        print(
            f"SQL queries:   {len(queries)}"
        )
        print("=" * 110)

        total_db_time = 0.0

        for index, query in enumerate(
            queries,
            start=1,
        ):
            duration_ms = float(
                query.get(
                    "duration_ms",
                    0.0,
                )
            )

            total_db_time += duration_ms

            statement = str(
                query.get(
                    "statement",
                    "",
                )
            ).strip()

            print()
            print(
                f"[{index:02d}] "
                f"{duration_ms:>9.3f} ms"
            )
            print(
                statement
            )

        print()
        print("=" * 110)
        print(
            f"Total DB execution time: "
            f"{total_db_time:.3f} ms"
        )
        print(
            f"Total service time:      "
            f"{elapsed_ms:.3f} ms"
        )
        print(
            f"Application overhead:    "
            f"{max(elapsed_ms - total_db_time, 0):.3f} ms"
        )
        print("=" * 110)


if __name__ == "__main__":
    main()