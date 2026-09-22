from __future__ import annotations

import os

from locust import HttpUser, between, task

from load_tests.common.auth import get_required_env
from load_tests.common.benchmark import get_load_test_id


class ConsultationsUser(HttpUser):
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
    def staff_consultations(self) -> None:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
            "X-Load-Test-ID": self.load_test_id,
        }

        with self.client.get(
            "/api/v1/consultations/staff/20?page=1&per_page=50",
            headers=headers,
            name="GET /api/v1/consultations/staff/{staff_id} [page=1,per_page=50]",
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

            if body.get("success") is not True:
                response.failure(
                    "HTTP 200 but success != true"
                )
                return

            data = body.get("data")
            pagination = body.get("pagination")

            if not isinstance(data, list):
                response.failure(
                    "Consultation data is not a list"
                )
                return

            if not isinstance(pagination, dict):
                response.failure(
                    "Consultation pagination is missing or invalid"
                )
                return

            if pagination.get("page") != 1:
                response.failure(
                    f"Unexpected page value: {pagination.get('page')}"
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
                    "Pagination total is not an integer"
                )
                return

            if len(data) > 50:
                response.failure(
                    f"Returned more than 50 consultations: {len(data)}"
                )
                return

            for consultation in data:
                if not isinstance(consultation, dict):
                    response.failure(
                        "Consultation item is not an object"
                    )
                    return

                if consultation.get("staff_id") != 20:
                    response.failure(
                        "Consultation belongs to unexpected staff"
                    )
                    return

            response.success()