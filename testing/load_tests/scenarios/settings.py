from __future__ import annotations

import os

from locust import HttpUser, between, task

from load_tests.common.auth import get_required_env
from load_tests.common.benchmark import get_load_test_id


class SettingsUser(HttpUser):
    wait_time = between(
        float(os.getenv("LOCUST_WAIT_MIN", "1")),
        float(os.getenv("LOCUST_WAIT_MAX", "3")),
    )

    load_test_id = get_load_test_id()

    def on_start(self) -> None:
        self.access_token = self._login()

    def _login(self) -> str:
        email = get_required_env("LOCUST_EMAIL")
        password = get_required_env("LOCUST_PASSWORD")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Load-Test-ID": self.load_test_id,
        }

        with self.client.post(
            "/api/v1/auth/login",
            json={
                "email": email,
                "password": password,
            },
            headers=headers,
            name="POST /api/v1/auth/login [setup]",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"Unexpected HTTP {response.status_code}: "
                    f"{response.text[:200]}"
                )
                raise RuntimeError(
                    "Benchmark authentication failed"
                )

            try:
                body = response.json()
            except ValueError as exc:
                response.failure(
                    "HTTP 200 but response was not JSON"
                )
                raise RuntimeError(
                    "Benchmark authentication returned invalid JSON"
                ) from exc

            if body.get("success") is not True:
                response.failure(
                    "HTTP 200 but success != true"
                )
                raise RuntimeError(
                    "Benchmark authentication failed"
                )

            data = body.get("data")

            if not isinstance(data, dict):
                response.failure(
                    "Login response data is missing or invalid"
                )
                raise RuntimeError(
                    "Benchmark authentication failed"
                )

            token = data.get("access_token")

            if not token:
                response.failure(
                    "Login response has no access_token"
                )
                raise RuntimeError(
                    "Benchmark authentication failed"
                )

            response.success()
            return str(token)

    @task
    def get_clinic_settings(self) -> None:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
            "X-Load-Test-ID": self.load_test_id,
        }

        with self.client.get(
            "/api/v1/settings/clinic",
            headers=headers,
            name="GET /api/v1/settings/clinic",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"Unexpected HTTP {response.status_code}: "
                    f"{response.text[:200]}"
                )
                return

            try:
                body = response.json()
            except ValueError:
                response.failure(
                    "HTTP 200 but response was not JSON"
                )
                return

            if not isinstance(body, dict):
                response.failure(
                    "Settings response is not an object"
                )
                return

            if body.get("success") is not True:
                response.failure(
                    "Settings response success != true"
                )
                return

            data = body.get("data")

            if not isinstance(data, dict):
                response.failure(
                    "Settings data is not an object"
                )
                return

            required_ints = (
                "id",
                "clinic_id",
                "version",
            )

            for field in required_ints:
                if not isinstance(data.get(field), int):
                    response.failure(
                        f"Settings {field} is not an integer"
                    )
                    return

            required_strings = (
                "language",
                "date_format",
                "time_format",
            )

            for field in required_strings:
                if not isinstance(data.get(field), str):
                    response.failure(
                        f"Settings {field} is not a string"
                    )
                    return

            preference_fields = (
                "notification_preferences",
                "feature_flags",
                "operational_preferences",
                "security_preferences",
                "system_preferences",
            )

            for field in preference_fields:
                if not isinstance(data.get(field), dict):
                    response.failure(
                        f"Settings {field} is not an object"
                    )
                    return

            if not isinstance(data.get("is_enabled"), bool):
                response.failure(
                    "Settings is_enabled is not boolean"
                )
                return

            if "created_at" not in data:
                response.failure(
                    "Settings created_at is missing"
                )
                return

            if "updated_at" not in data:
                response.failure(
                    "Settings updated_at is missing"
                )
                return

            response.success()