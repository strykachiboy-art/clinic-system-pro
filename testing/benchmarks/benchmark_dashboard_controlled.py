from __future__ import annotations

import sys
import statistics
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
WARMUPS = 3
RUNS = 20


def percentile(values, percentile):
    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower

    return (
        ordered[lower]
        + (
            ordered[upper] - ordered[lower]
        ) * fraction
    )


def main():
    app = create_app("development")

    with app.app_context():
        actor = db.session.get(
            User,
            ACTOR_ID,
        )

        if actor is None:
            raise RuntimeError(
                f"User {ACTOR_ID} does not exist."
            )

        cache = getattr(
            db.engine,
            "_compiled_cache",
            None,
        )

        print("=" * 100)
        print("CONTROLLED DASHBOARD WARM BENCHMARK")
        print("=" * 100)
        print(f"Actor ID: {ACTOR_ID}")
        print(
            f"Role: {getattr(actor.role, 'value', actor.role)}"
        )
        print(f"Clinic ID: {actor.clinic_id}")
        print(f"Warmups: {WARMUPS}")
        print(f"Measured runs: {RUNS}")
        print("=" * 100)
        print()

        for number in range(1, WARMUPS + 1):
            started = time.perf_counter()

            get_dashboard(
                actor_id=ACTOR_ID,
            )

            elapsed = (
                time.perf_counter() - started
            ) * 1000

            print(
                f"Warmup {number:02d}: "
                f"{elapsed:.3f} ms"
            )

        print()

        timings = []

        for number in range(1, RUNS + 1):
            started = time.perf_counter()

            result = get_dashboard(
                actor_id=ACTOR_ID,
            )

            elapsed = (
                time.perf_counter() - started
            ) * 1000

            timings.append(elapsed)

            print(
                f"Run {number:02d}: "
                f"{elapsed:.3f} ms "
                f"result={type(result).__name__}"
            )

        average = statistics.mean(timings)
        median = statistics.median(timings)
        p95 = percentile(timings, 0.95)
        p99 = percentile(timings, 0.99)

        print()
        print("=" * 100)
        print("SUMMARY")
        print("=" * 100)
        print(f"Average:  {average:.3f} ms")
        print(f"Median:   {median:.3f} ms")
        print(f"P95:      {p95:.3f} ms")
        print(f"P99:      {p99:.3f} ms")
        print(f"Fastest:  {min(timings):.3f} ms")
        print(f"Slowest:  {max(timings):.3f} ms")

        if cache is not None:
            print(f"Cache:    {len(cache)}")

        print("=" * 100)


if __name__ == "__main__":
    main()
