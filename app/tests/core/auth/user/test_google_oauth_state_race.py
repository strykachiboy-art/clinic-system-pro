from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

import pytest

from app.core.auth.user.services import google_auth_service
from app.core.exceptions import ValidationError


class RaceRedis:
    def __init__(self):
        self.exists_barrier = Barrier(2)
        self.lock = Lock()
        self.consumed = False

    def exists(self, key):
        state_present = not self.consumed

        self.exists_barrier.wait(
            timeout=5
        )

        return state_present

    def delete(self, key):
        with self.lock:
            self.consumed = True

        return 1

    def eval(self, script, numkeys, key):
        with self.lock:
            if self.consumed:
                return 0

            self.consumed = True
            return 1


def test_google_oauth_state_consumption_is_atomic_under_concurrent_callbacks():
    redis_mock = RaceRedis()

    def consume_state():
        try:
            google_auth_service.validate_google_oauth_state(
                "race-state"
            )
            return "accepted"
        except ValidationError:
            return "rejected"

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            google_auth_service.extensions,
            "redis_client",
            redis_mock,
        )

        with ThreadPoolExecutor(
            max_workers=2
        ) as executor:
            results = list(
                executor.map(
                    lambda _: consume_state(),
                    range(2),
                )
            )

    assert sorted(results) == [
        "accepted",
        "rejected",
    ]