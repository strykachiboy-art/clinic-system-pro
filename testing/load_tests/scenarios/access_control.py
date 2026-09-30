from __future__ import annotations

import os

from locust import HttpUser, between, task

from load_tests.common.auth import get_required_env
from load_tests.common.benchmark import get_load_test_id


class AccessControlUser(HttpUser):
    wait_time = between(
        float(os.getenv("LOCUST_WAIT_MIN", "1")),
        float(os.getenv("LOCUST_WAIT_MAX", "3")),
    )

    load_test_id = get_load_test_id()

    def on_start(self) -> None:
        self.access_token = self._login()

    def _login(self) -> str:
        email = get_required_env(
            "LOCUST_ACCESS_CONTROL_EMAIL"
        )

        password = get_required_env(
            "LOCUST_ACCESS_CONTROL_PASSWORD"
        )

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
                    "Access Control benchmark authentication failed"
                )

            try:
                body = response.json()
            except ValueError as exc:
                response.failure(
                    "HTTP 200 but response was not JSON"
                )
                raise RuntimeError(
                    "Access Control benchmark authentication "
                    "returned invalid JSON"
                ) from exc

            if body.get("success") is not True:
                response.failure(
                    "HTTP 200 but success != true"
                )
                raise RuntimeError(
                    "Access Control benchmark authentication failed"
                )

            data = body.get("data")

            if not isinstance(data, dict):
                response.failure(
                    "Login response data is missing or invalid"
                )
                raise RuntimeError(
                    "Access Control benchmark authentication "
                    "returned invalid data"
                )

            access_token = data.get(
                "access_token"
            )

            if not access_token:
                response.failure(
                    "Login response has no access_token"
                )
                raise RuntimeError(
                    "Access Control benchmark authentication "
                    "returned no access token"
                )

            response.success()

            return str(access_token)

    @task
    def list_access_control_users(self) -> None:
        headers = {
            "Authorization": (
                f"Bearer {self.access_token}"
            ),
            "Accept": "application/json",
            "X-Load-Test-ID": self.load_test_id,
        }

        with self.client.get(
            "/api/v1/access-control/users"
            "?page=1&per_page=50",
            headers=headers,
            name=(
                "GET /api/v1/access-control/users "
                "[page=1,per_page=50]"
            ),
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
                    "Access Control response is not an object"
                )
                return

            if body.get("success") is not True:
                response.failure(
                    "Access Control response success != true"
                )
                return

            data = body.get("data")

            if not isinstance(data, dict):
                response.failure(
                    "Access Control data is missing or invalid"
                )
                return

            items = data.get("items")

            if not isinstance(items, list):
                response.failure(
                    "Access Control items is missing or invalid"
                )
                return

            pagination = data.get("pagination")

            if not isinstance(pagination, dict):
                response.failure(
                    "Access Control pagination is missing "
                    "or invalid"
                )
                return

            if pagination.get("page") != 1:
                response.failure(
                    "Unexpected page value"
                )
                return

            if pagination.get("per_page") != 50:
                response.failure(
                    "Unexpected per_page value"
                )
                return

            total = pagination.get("total")

            if not isinstance(total, int):
                response.failure(
                    "pagination.total must be an integer"
                )
                return

            if total < 0:
                response.failure(
                    "pagination.total cannot be negative"
                )
                return

            pages = pagination.get("pages")

            if not isinstance(pages, int):
                response.failure(
                    "pagination.pages must be an integer"
                )
                return

            if pages < 0:
                response.failure(
                    "pagination.pages cannot be negative"
                )
                return

            if len(items) > 50:
                response.failure(
                    "Returned more than 50 users"
                )
                return

            for item in items:
                if not isinstance(item, dict):
                    response.failure(
                        "Access Control user must be an object"
                    )
                    return

                if not isinstance(
                    item.get("id"),
                    int,
                ):
                    response.failure(
                        "User id must be an integer"
                    )
                    return

                if not isinstance(
                    item.get("email"),
                    str,
                ):
                    response.failure(
                        "User email must be a string"
                    )
                    return

                if not isinstance(
                    item.get("role"),
                    str,
                ):
                    response.failure(
                        "User role must be a string"
                    )
                    return

                if not isinstance(
                    item.get("is_active"),
                    bool,
                ):
                    response.failure(
                        "User is_active must be boolean"
                    )
                    return

                clinic_id = item.get("clinic_id")

                if (
                    clinic_id is not None
                    and not isinstance(
                        clinic_id,
                        int,
                    )
                ):
                    response.failure(
                        "User clinic_id must be integer or null"
                    )
                    return

            response.success()