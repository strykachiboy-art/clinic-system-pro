from __future__ import annotations

import os
import time

import pytest
from sqlalchemy import text

from app.tests.core.concurrency.concurrency_harness import (
    PostgresConcurrencyHarness,
)


def test_postgresql_concurrency_harness_serializes_row_updates():
    database_url = os.getenv(
        "CONCURRENCY_TEST_DATABASE_URL"
    )

    if not database_url:
        pytest.fail(
            "CONCURRENCY_TEST_DATABASE_URL is required"
        )

    harness = PostgresConcurrencyHarness(
        database_url
    )

    table_name = "gate9_concurrency_probe"

    try:
        with harness.engine.begin() as connection:
            connection.execute(
                text(
                    f"""
                    CREATE TABLE {table_name} (
                        id INTEGER PRIMARY KEY,
                        value INTEGER NOT NULL
                    )
                    """
                )
            )

            connection.execute(
                text(
                    f"""
                    INSERT INTO {table_name} (
                        id,
                        value
                    )
                    VALUES (
                        1,
                        0
                    )
                    """
                )
            )

        def increment_value(
            session,
            worker_index,
        ):
            current_value = session.execute(
                text(
                    f"""
                    SELECT value
                    FROM {table_name}
                    WHERE id = 1
                    FOR UPDATE
                    """
                )
            ).scalar_one()

            time.sleep(0.15)

            next_value = current_value + 1

            session.execute(
                text(
                    f"""
                    UPDATE {table_name}
                    SET value = :value
                    WHERE id = 1
                    """
                ),
                {
                    "value": next_value,
                },
            )

            return {
                "worker_index": worker_index,
                "before": current_value,
                "after": next_value,
            }

        results = harness.run(
            increment_value
        )

        assert len(results) == 2

        errors = [
            result.error
            for result in results
            if result.error is not None
        ]

        assert errors == []

        backend_pids = {
            result.backend_pid
            for result in results
        }

        assert len(backend_pids) == 2

        before_values = sorted(
            result.value["before"]
            for result in results
        )

        after_values = sorted(
            result.value["after"]
            for result in results
        )

        assert before_values == [0, 1]
        assert after_values == [1, 2]

        with harness.engine.begin() as connection:
            final_value = connection.execute(
                text(
                    f"""
                    SELECT value
                    FROM {table_name}
                    WHERE id = 1
                    """
                )
            ).scalar_one()

        assert final_value == 2

    finally:
        with harness.engine.begin() as connection:
            connection.execute(
                text(
                    f"""
                    DROP TABLE IF EXISTS {table_name}
                    """
                )
            )

        harness.close()
