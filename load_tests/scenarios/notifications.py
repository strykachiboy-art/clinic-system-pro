from __future__ import annotations

import os

from locust import HttpUser, between, task

from load_tests.common.auth import get_required_env
from load_tests.common.benchmark import get_load_test_id


class NotificationsUser(HttpUser):
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
                raise RuntimeError("Benchmark authentication failed")

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
                raise RuntimeError("Benchmark authentication failed")

            data = body.get("data")

            if not isinstance(data, dict):
                response.failure(
                    "Login response data is missing or invalid"
                )
                raise RuntimeError("Benchmark authentication failed")

            token = data.get("access_token")

            if not token:
                response.failure(
                    "Login response has no access_token"
                )
                raise RuntimeError("Benchmark authentication failed")

            response.success()
            return str(token)

    @task
    def list_notifications(self) -> None:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
            "X-Load-Test-ID": self.load_test_id,
        }

        with self.client.get(
            "/api/v1/notifications/?page=1&per_page=50",
            headers=headers,
            name="GET /api/v1/notifications/ [page=1,per_page=50]",
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
                    "Notification response is not an object"
                )
                return

            if body.get("success") is not True:
                response.failure(
                    "Notification response success != true"
                )
                return

            data = body.get("data")

            if not isinstance(data, dict):
                response.failure(
                    "Notification response data is missing or invalid"
                )
                return

            items = data.get("items")
            total = data.get("total")
            page = data.get("page")
            per_page = data.get("per_page")

            if not isinstance(items, list):
                response.failure(
                    "Notification items is not a list"
                )
                return

            if not isinstance(total, int):
                response.failure(
                    "Notification total is not an integer"
                )
                return

            if page != 1:
                response.failure(
                    f"Unexpected page value: {page}"
                )
                return

            if per_page != 50:
                response.failure(
                    f"Unexpected per_page value: {per_page}"
                )
                return

            if len(items) > 50:
                response.failure(
                    f"Returned more than 50 notifications: {len(items)}"
                )
                return

            for item in items:
                if not isinstance(item, dict):
                    response.failure(
                        "Notification item is not an object"
                    )
                    return

                if not isinstance(item.get("id"), int):
                    response.failure(
                        "Notification id is not an integer"
                    )
                    return

                if not isinstance(item.get("clinic_id"), int):
                    response.failure(
                        "Notification clinic_id is not an integer"
                    )
                    return

                if not isinstance(item.get("user_id"), int):
                    response.failure(
                        "Notification user_id is not an integer"
                    )
                    return

                if not isinstance(item.get("title"), str):
                    response.failure(
                        "Notification title is not a string"
                    )
                    return

                if not isinstance(item.get("message"), str):
                    response.failure(
                        "Notification message is not a string"
                    )
                    return

                if not isinstance(item.get("notification_type"), str):
                    response.failure(
                        "Notification type is not a string"
                    )
                    return

                if not isinstance(item.get("priority"), str):
                    response.failure(
                        "Notification priority is not a string"
                    )
                    return

                if not isinstance(item.get("channel"), str):
                    response.failure(
                        "Notification channel is not a string"
                    )
                    return

                if not isinstance(item.get("status"), str):
                    response.failure(
                        "Notification status is not a string"
                    )
                    return

                if not isinstance(item.get("is_read"), bool):
                    response.failure(
                        "Notification is_read is not a boolean"
                    )
                    return

                if not isinstance(item.get("retry_count"), int):
                    response.failure(
                        "Notification retry_count is not an integer"
                    )
                    return

            response.success()