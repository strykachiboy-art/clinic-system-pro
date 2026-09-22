from __future__ import annotations

import argparse
import cProfile
import os
import pstats
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


DEFAULT_ENV = "development"
DEFAULT_ACTOR_ID = 5
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "load_tests" / "results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--actor-id",
        type=int,
        default=DEFAULT_ACTOR_ID,
    )

    parser.add_argument(
        "--env",
        default=os.getenv(
            "FLASK_ENV",
            DEFAULT_ENV,
        ),
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
    )

    return parser.parse_args()


def run_dashboard(actor_id: int) -> float:
    started = time.perf_counter()

    result = get_dashboard(
        actor_id=actor_id,
    )

    elapsed_ms = (
        time.perf_counter() - started
    ) * 1000

    if result is None:
        raise RuntimeError(
            "Dashboard returned None"
        )

    return elapsed_ms


def main() -> None:
    args = parse_args()

    args.output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    app = create_app(
        args.env
    )

    with app.app_context():
        actor = db.session.get(
            User,
            args.actor_id,
        )

        if actor is None:
            raise RuntimeError(
                f"User with ID {args.actor_id} does not exist."
            )

        engine = db.engine
        compiled_cache = getattr(
            engine,
            "_compiled_cache",
            None,
        )

        print("=" * 100)
        print("DASHBOARD WARM-PATH PROFILER")
        print("=" * 100)
        print(
            f"Actor ID:       {args.actor_id}"
        )
        print(
            f"Actor role:     "
            f"{getattr(actor.role, 'value', actor.role)}"
        )
        print(
            f"Clinic ID:      {actor.clinic_id}"
        )
        print("=" * 100)
        print()

        print("WARMING DASHBOARD...")
        warm_ms = run_dashboard(
            args.actor_id
        )

        cache_after_warm = (
            len(compiled_cache)
            if compiled_cache is not None
            else None
        )

        print(
            f"Warm-up run:    "
            f"{warm_ms:.3f} ms"
        )
        print(
            f"Cache size:     "
            f"{cache_after_warm}"
        )
        print()

        timestamp = time.strftime(
            "%Y%m%d-%H%M%S"
        )

        profile_path = (
            args.output_dir
            / f"dashboard-warm-{timestamp}.prof"
        )

        stats_path = (
            args.output_dir
            / f"dashboard-warm-{timestamp}.txt"
        )

        print("PROFILING WARM REQUEST...")
        print()

        profiler = cProfile.Profile()

        started = time.perf_counter()

        profiler.enable()

        result = get_dashboard(
            actor_id=args.actor_id,
        )

        profiler.disable()

        elapsed_ms = (
            time.perf_counter() - started
        ) * 1000

        profiler.dump_stats(
            str(profile_path)
        )

        stats = pstats.Stats(
            profiler
        )

        stats.sort_stats(
            "cumulative"
        )

        with stats_path.open(
            "w",
            encoding="utf-8",
        ) as fh:
            stats.stream = fh
            stats.print_stats(100)

        stats.stream = sys.stdout

        cache_after_profile = (
            len(compiled_cache)
            if compiled_cache is not None
            else None
        )

        print()
        print("=" * 100)
        print("WARM-PATH PROFILE COMPLETE")
        print("=" * 100)
        print(
            f"Warm-up time:         "
            f"{warm_ms:.3f} ms"
        )
        print(
            f"Profiled time:        "
            f"{elapsed_ms:.3f} ms"
        )
        print(
            f"Cache after warm-up:  "
            f"{cache_after_warm}"
        )
        print(
            f"Cache after profile:  "
            f"{cache_after_profile}"
        )
        print(
            f"Profile:              "
            f"{profile_path}"
        )
        print(
            f"Stats:                "
            f"{stats_path}"
        )
        print("=" * 100)
        print()

        print(
            "TOP WARM-PATH FUNCTIONS"
        )
        print("=" * 100)

        stats.sort_stats(
            "cumulative"
        )

        stats.print_stats(50)

        print()
        print(
            f"Dashboard result: "
            f"{type(result).__name__}"
        )


if __name__ == "__main__":
    main()