from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app


REQUIRED_FILES = [
    "app/core/observability/health.py",
    "app/core/observability/health_routes.py",
    "app/core/observability/request_context.py",
    "app/core/observability/request_metrics.py",
    "app/core/observability/db_metrics.py",
    "app/core/observability/redis_metrics.py",
    "app/core/observability/system_metrics.py",
    "app/core/observability/celery_metrics.py",
    "app/core/observability/socketio_metrics.py",
    "app/core/observability/operational_metrics.py",
    "app/core/observability/alerts.py",
    "app/core/observability/alert_state.py",
    "app/core/observability/alert_delivery.py",
    "app/core/observability/failure_events.py",
    "app/core/observability/failure_dashboard_service.py",
    "app/core/observability/failure_dashboard_routes.py",
    "app/core/observability/tracing.py",
    "app/core/observability/operations_dashboard_service.py",
    "app/core/observability/operations_routes.py",
]

REQUIRED_RUNBOOKS = [
    "docs/runbooks/README.md",
    "docs/runbooks/observability-incident.md",
    "docs/runbooks/redis-degradation.md",
    "docs/runbooks/celery-degradation.md",
    "docs/runbooks/database-degradation.md",
]

REQUIRED_ROUTES = {
    "/health/live",
    "/health/ready",
    "/api/v1/operations",
    "/api/v1/operations/failures",
}


def fail(message: str) -> None:
    print(f"[FAIL] {message}")
    sys.exit(1)


def main() -> None:
    print("=" * 72)
    print("CLINIC SYSTEM PRO v5")
    print("PHASE 4 OBSERVABILITY / OPERATIONS EXIT REVIEW")
    print("=" * 72)
    print()

    print("[1/4] Checking required observability files...")

    missing_files = [
        path
        for path in REQUIRED_FILES
        if not (ROOT / path).is_file()
    ]

    if missing_files:
        for path in missing_files:
            print(f"  MISSING: {path}")

        fail(
            "Required observability files are missing."
        )

    print(
        f"  PASS: {len(REQUIRED_FILES)} required files present."
    )

    print()
    print("[2/4] Checking operational runbooks...")

    missing_runbooks = [
        path
        for path in REQUIRED_RUNBOOKS
        if not (ROOT / path).is_file()
    ]

    if missing_runbooks:
        for path in missing_runbooks:
            print(f"  MISSING: {path}")

        fail(
            "Required operational runbooks are missing."
        )

    print(
        f"  PASS: {len(REQUIRED_RUNBOOKS)} runbooks present."
    )

    print()
    print("[3/4] Checking registered operational routes...")

    app = create_app("testing")

    registered_routes = {
        str(rule)
        for rule in app.url_map.iter_rules()
    }

    missing_routes = (
        REQUIRED_ROUTES
        - registered_routes
    )

    if missing_routes:
        for route in sorted(missing_routes):
            print(f"  MISSING: {route}")

        fail(
            "Required operational routes are not registered."
        )

    for route in sorted(REQUIRED_ROUTES):
        print(f"  PASS: {route}")

    print()
    print("[4/4] Running observability test suite...")
    print()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "app/tests/core/observability/",
        ],
        cwd=ROOT,
    )

    if result.returncode != 0:
        fail(
            "Observability test suite failed."
        )

    print()
    print("=" * 72)
    print("PHASE 4 EXIT REVIEW: GREEN")
    print("=" * 72)
    print("Observability implementation: VERIFIED")
    print("Operational routes: VERIFIED")
    print("Operational runbooks: VERIFIED")
    print("Observability tests: GREEN")
    print()
    print("Phase 4 is ready for formal README status closure.")
    print("=" * 72)


if __name__ == "__main__":
    main()
