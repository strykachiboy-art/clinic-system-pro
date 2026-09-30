from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4


def create_load_test_id(prefix: str = "locust") -> str:
    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")

    return (
        f"{prefix}-{timestamp}-{uuid4().hex[:8]}"
    )


def get_load_test_id() -> str:
    return (
        os.getenv("LOCUST_RUN_ID")
        or create_load_test_id()
    )


def get_benchmark_patient_id() -> int:
    value = os.getenv(
        "LOCUST_PATIENT_ID",
        "4",
    )

    try:
        patient_id = int(value)
    except ValueError as exc:
        raise RuntimeError(
            "LOCUST_PATIENT_ID must be an integer"
        ) from exc

    if patient_id <= 0:
        raise RuntimeError(
            "LOCUST_PATIENT_ID must be greater than zero"
        )

    return patient_id