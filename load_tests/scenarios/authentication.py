from __future__ import annotations

import os

from locust import HttpUser, between, task

from load_tests.common.auth import login
from load_tests.common.benchmark import get_load_test_id


class AuthenticationUser(HttpUser):
    wait_time = between(
        float(os.getenv("LOCUST_WAIT_MIN", "2")),
        float(os.getenv("LOCUST_WAIT_MAX", "4")),
    )

    load_test_id = get_load_test_id()

    def on_start(self) -> None:
        self.login()

    def login(self) -> None:
        result = login(
            self,
            self.load_test_id,
        )

        if not result:
            raise RuntimeError(
                "Authentication benchmark login failed"
            )

        self.access_token = str(
            result["access_token"]
        )
        self.refresh_token = str(
            result["refresh_token"]
        )
        self.user_id = result["user_id"]
        self.role = result["role"]

    @task
    def login_request(self) -> None:
        login(
            self,
            self.load_test_id,
        )