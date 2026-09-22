from __future__ import annotations

import time
from pathlib import Path
import sys

from sqlalchemy import event


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app import create_app
from app.extensions import db
from app.core.auth.user.models.user_model import User

from app.modules.dashboard.services.dashboard_widget_service import (
    build_ai_aggregates,
    build_chat_summary,
    period_bounds,
    resolve_dashboard_period,
)


ACTOR_ID = 5
RUNS = 5


def benchmark(
    label: str,
    function,
    **kwargs,
):
    results = []

    for run_number in range(1, RUNS + 1):
        query_count = 0

        def before_cursor_execute(
            conn,
            cursor,
            statement,
            parameters,
            context,
            executemany,
        ):
            nonlocal query_count
            query_count += 1

        event.listen(
            db.engine,
            "before_cursor_execute",
            before_cursor_execute,
        )

        started = time.perf_counter()

        try:
            result = function(
                **kwargs
            )
        finally:
            event.remove(
                db.engine,
                "before_cursor_execute",
                before_cursor_execute,
            )

        elapsed_ms = (
            time.perf_counter() - started
        ) * 1000

        results.append(
            {
                "run": run_number,
                "time_ms": elapsed_ms,
                "queries": query_count,
                "result_type": type(result).__name__,
            }
        )

        print(
            f"{label} Run {run_number}: "
            f"{elapsed_ms:.3f} ms "
            f"queries={query_count} "
            f"result={type(result).__name__}"
        )

    warm = results[1:]

    print()
    print(
        f"{label} warm average: "
        f"{sum(x['time_ms'] for x in warm) / len(warm):.3f} ms"
    )

    print(
        f"{label} fastest warm:  "
        f"{min(x['time_ms'] for x in warm):.3f} ms"
    )

    print(
        f"{label} slowest warm:  "
        f"{max(x['time_ms'] for x in warm):.3f} ms"
    )

    print(
        f"{label} warm queries:  "
        f"{warm[0]['queries']}"
    )

    return results


def main() -> None:
    app = create_app(
        "development"
    )

    with app.app_context():
        actor = db.session.get(
            User,
            ACTOR_ID,
        )

        if actor is None:
            raise RuntimeError(
                f"User {ACTOR_ID} does not exist."
            )

        period = resolve_dashboard_period(
            None
        )

        print("=" * 100)
        print("DASHBOARD WIDGET BENCHMARK")
        print("=" * 100)
        print(
            f"Actor ID:       {ACTOR_ID}"
        )
        print(
            f"Role:           "
            f"{getattr(actor.role, 'value', actor.role)}"
        )
        print(
            f"Clinic ID:      {actor.clinic_id}"
        )
        print(
            f"Period:         "
            f"{period.date_from} -> {period.date_to}"
        )
        print("=" * 100)
        print()

        print("WARMING AI AGGREGATES...")
        build_ai_aggregates(
            clinic_id=actor.clinic_id,
            period=period,
        )

        print("WARMING CHAT SUMMARY...")
        build_chat_summary(
            user_id=actor.id,
            clinic_id=actor.clinic_id,
            period=period,
        )

        print()
        print("=" * 100)
        print("AI AGGREGATES")
        print("=" * 100)

        benchmark(
            "AI",
            build_ai_aggregates,
            clinic_id=actor.clinic_id,
            period=period,
        )

        print()
        print("=" * 100)
        print("CHAT SUMMARY")
        print("=" * 100)

        benchmark(
            "CHAT",
            build_chat_summary,
            user_id=actor.id,
            clinic_id=actor.clinic_id,
            period=period,
        )

        print()
        print("=" * 100)
        print("COMPLETE")
        print("=" * 100)


if __name__ == "__main__":
    main()