from __future__ import annotations

import os

from locust import HttpUser, between, task

from load_tests.common.auth import get_required_env
from load_tests.common.benchmark import get_load_test_id


class AuditUser(HttpUser):
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
    def get_audit_logs(self) -> None:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
            "X-Load-Test-ID": self.load_test_id,
        }

        with self.client.get(
            "/api/v1/audit-logs?page=1&per_page=20",
            headers=headers,
            name="GET /api/v1/audit-logs?page=1&per_page=20",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"Unexpected HTTP {response.status_code}: "
                    f"{response.text[:300]}"
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
                    "Audit response is not an object"
                )
                return

            if body.get("success") is not True:
                response.failure(
                    "Audit response success != true"
                )
                return

            data = body.get("data")

            if not isinstance(data, dict):
                response.failure(
                    "Audit data is not an object"
                )
                return

            required_pagination = {
                "items",
                "total",
                "page",
                "per_page",
                "pages",
                "has_next",
                "has_prev",
            }

            if not required_pagination.issubset(data):
                response.failure(
                    "Audit response is missing required pagination fields"
                )
                return

            items = data.get("items")

            if not isinstance(items, list):
                response.failure(
                    "Audit items is not a list"
                )
                return

            if not isinstance(data.get("total"), int):
                response.failure(
                    "Audit total is not an integer"
                )
                return

            if not isinstance(data.get("page"), int):
                response.failure(
                    "Audit page is not an integer"
                )
                return

            if not isinstance(data.get("per_page"), int):
                response.failure(
                    "Audit per_page is not an integer"
                )
                return

            if not isinstance(data.get("pages"), int):
                response.failure(
                    "Audit pages is not an integer"
                )
                return

            if not isinstance(data.get("has_next"), bool):
                response.failure(
                    "Audit has_next is not boolean"
                )
                return

            if not isinstance(data.get("has_prev"), bool):
                response.failure(
                    "Audit has_prev is not boolean"
                )
                return

            if data["page"] != 1:
                response.failure(
                    f"Unexpected audit page: {data['page']}"
                )
                return

            if data["per_page"] != 20:
                response.failure(
                    f"Unexpected audit per_page: {data['per_page']}"
                )
                return

            for item in items:
                if not isinstance(item, dict):
                    response.failure(
                        "Audit item is not an object"
                    )
                    return

                required_fields = (
                    "id",
                    "action",
                    "entity_type",
                    "entity_id",
                    "user_id",
                    "description",
                    "old_value",
                    "new_value",
                    "ip_address",
                    "created_at",
                )

                missing = [
                    field
                    for field in required_fields
                    if field not in item
                ]

                if missing:
                    response.failure(
                        "Audit item missing fields: "
                        + ", ".join(missing)
                    )
                    return

                if not isinstance(item.get("id"), int):
                    response.failure(
                        "Audit item id is not an integer"
                    )
                    return

                if not isinstance(item.get("action"), str):
                    response.failure(
                        "Audit item action is not a string"
                    )
                    return

                if not isinstance(item.get("entity_type"), str):
                    response.failure(
                        "Audit item entity_type is not a string"
                    )
                    return

                if not isinstance(item.get("entity_id"), int):
                    response.failure(
                        "Audit item entity_id is not an integer"
                    )
                    return

                user_id = item.get("user_id")

                if user_id is not None and not isinstance(
                    user_id,
                    int,
                ):
                    response.failure(
                        "Audit item user_id is not an integer or null"
                    )
                    return

                description = item.get("description")

                if description is not None and not isinstance(
                    description,
                    str,
                ):
                    response.failure(
                        "Audit item description is not a string or null"
                    )
                    return

                for field in (
                    "old_value",
                    "new_value",
                ):
                    value = item.get(field)

                    if value is not None and not isinstance(
                        value,
                        dict,
                    ):
                        response.failure(
                            f"Audit item {field} is not an object or null"
                        )
                        return

                ip_address = item.get("ip_address")

                if ip_address is not None and not isinstance(
                    ip_address,
                    str,
                ):
                    response.failure(
                        "Audit item ip_address is not a string or null"
                    )
                    return

                if not isinstance(
                    item.get("created_at"),
                    str,
                ):
                    response.failure(
                        "Audit item created_at is not a string"
                    )
                    return

            if len(items) > data["per_page"]:
                response.failure(
                    "Audit item count exceeds per_page"
                )
                return

            response.success()