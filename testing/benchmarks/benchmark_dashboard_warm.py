from __future__ import annotations

import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app import create_app
from app.extensions import db
from app.core.auth.user.models.user_model import User
from app.modules.dashboard.services.dashboard_service import get_dashboard


ACTOR_ID = 5
RUNS = 8


def main() -> None:
    app = create_app("development")

    with app.app_context():
        actor = db.session.get(
            User,
            ACTOR_ID,
        )

        if actor is None:
            raise RuntimeError(
                f"User with ID {ACTOR_ID} does not exist."
            )

        engine = db.engine
        cache = getattr(
            engine,
            "_compiled_cache",
            None,
        )

        print("=" * 100)
        print("DASHBOARD WARM BENCHMARK")
        print("=" * 100)
        print(
            f"Actor ID:       {ACTOR_ID}"
        )
        print(
            f"Role:           "
            f"{getattr(actor.role, 'value', actor.role)}"
        )
        print(
            f"Clinic ID:      "
            f"{actor.clinic_id}"
        )
        print(
            f"Cache enabled:  "
            f"{cache is not None}"
        )
        print("=" * 100)
        print()

        print("WARM-UP")

        started = time.perf_counter()

        get_dashboard(
            actor_id=ACTOR_ID,
        )

        warmup_ms = (
            time.perf_counter() - started
        ) * 1000

        print(
            f"Warm-up: {warmup_ms:.3f} ms"
        )

        if cache is not None:
            print(
                f"Cache:   {len(cache)}"
            )

        print()
        print("MEASURED RUNS")

        timings = []

        for number in range(
            1,
            RUNS + 1,
        ):
            started = time.perf_counter()

            result = get_dashboard(
                actor_id=ACTOR_ID,
            )

            elapsed_ms = (
                time.perf_counter() - started
            ) * 1000

            timings.append(
                elapsed_ms
            )

            print(
                f"Run {number:02d}: "
                f"{elapsed_ms:.3f} ms "
                f"result={type(result).__name__}"
            )

        average = (
            sum(timings) / len(timings)
        )

        print()
        print("=" * 100)
        print("SUMMARY")
        print("=" * 100)
        print(
            f"Average:  {average:.3f} ms"
        )
        print(
            f"Fastest:  {min(timings):.3f} ms"
        )
        print(
            f"Slowest:  {max(timings):.3f} ms"
        )

        if cache is not None:
            print(
                f"Cache:    {len(cache)}"
            )

        print("=" * 100)


if __name__ == "__main__":
    main()