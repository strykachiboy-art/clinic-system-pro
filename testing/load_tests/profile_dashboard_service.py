from __future__ import annotations

import argparse
import cProfile
import json
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

from app.modules.dashboard.services.dashboard_service import (
    get_dashboard,
)


DEFAULT_ENV = "development"
DEFAULT_ACTOR_ID = 5
DEFAULT_RESULTS_DIR = (
    PROJECT_ROOT / "load_tests" / "results"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Profile the real Dashboard service entry point "
            "without modifying Dashboard code."
        )
    )

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


def profile_dashboard(
    app,
    actor_id: int,
    output_dir: Path,
) -> None:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    with app.app_context():
        actor = db.session.get(
            User,
            actor_id,
        )

        if actor is None:
            raise RuntimeError(
                f"User with ID {actor_id} does not exist."
            )

        print("=" * 100)
        print("DASHBOARD APPLICATION PROFILER")
        print("=" * 100)
        print(f"Actor ID:             {actor_id}")
        print(
            f"Actor role:           "
            f"{getattr(actor.role, 'value', actor.role)}"
        )
        print(f"Clinic ID:            {actor.clinic_id}")
        print("=" * 100)
        print()

        profiler = cProfile.Profile()

        started = time.perf_counter()

        profiler.enable()

        result = get_dashboard(
            actor_id=actor_id,
        )

        profiler.disable()

        elapsed_ms = (
            time.perf_counter() - started
        ) * 1000

        timestamp = time.strftime(
            "%Y%m%d-%H%M%S"
        )

        profile_path = (
            output_dir
            / f"dashboard-service-{timestamp}.prof"
        )

        stats_path = (
            output_dir
            / f"dashboard-service-{timestamp}.txt"
        )

        summary_path = (
            output_dir
            / f"dashboard-service-{timestamp}.json"
        )

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

        summary = {
            "actor_id": actor_id,
            "actor_role": getattr(
                actor.role,
                "value",
                str(actor.role),
            ),
            "clinic_id": actor.clinic_id,
            "service_entry_point": (
                "app.modules.dashboard.services.dashboard_service.get_dashboard"
            ),
            "result_type": type(result).__name__,
            "service_time_ms": round(
                elapsed_ms,
                3,
            ),
            "profile_file": str(
                profile_path
            ),
            "stats_file": str(
                stats_path
            ),
        }

        summary_path.write_text(
            json.dumps(
                summary,
                indent=2,
            ),
            encoding="utf-8",
        )

        print()
        print("=" * 100)
        print("DASHBOARD APPLICATION PROFILE")
        print("=" * 100)
        print(
            f"Actor ID:             {actor_id}"
        )
        print(
            f"Actor role:           {summary['actor_role']}"
        )
        print(
            f"Clinic ID:            {actor.clinic_id}"
        )
        print(
            f"Service entry point:  "
            f"{summary['service_entry_point']}"
        )
        print(
            f"Dashboard result:     {summary['result_type']}"
        )
        print(
            f"Service time:         "
            f"{elapsed_ms:.3f} ms"
        )
        print(
            f"Profile:              "
            f"{profile_path}"
        )
        print(
            f"Stats:                "
            f"{stats_path}"
        )
        print(
            f"Summary:              "
            f"{summary_path}"
        )
        print("=" * 100)

        print()
        print(
            "TOP FUNCTIONS BY CUMULATIVE TIME"
        )
        print("=" * 100)

        stats.sort_stats(
            "cumulative"
        )

        stats.print_stats(50)

        print()
        print("Done.")


def main() -> None:
    args = parse_args()

    app = create_app(
        args.env
    )

    profile_dashboard(
        app=app,
        actor_id=args.actor_id,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()