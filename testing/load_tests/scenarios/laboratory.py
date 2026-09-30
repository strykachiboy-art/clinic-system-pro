from __future__ import annotations

import os

from locust import HttpUser, between, task

from load_tests.common.auth import get_required_env
from load_tests.common.benchmark import get_load_test_id


class LaboratoryUser(HttpUser):
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
    def list_patient_lab_orders(self) -> None:
        patient_id = int(
            os.getenv("LOCUST_LAB_PATIENT_ID", "505")
        )

        if patient_id <= 0:
            raise RuntimeError(
                "LOCUST_LAB_PATIENT_ID must be greater than zero"
            )

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
            "X-Load-Test-ID": self.load_test_id,
        }

        url = (
            "/api/v1/lab/orders"
            f"?patient_id={patient_id}"
            "&page=1"
            "&per_page=50"
        )

        with self.client.get(
            url,
            headers=headers,
            name="GET /api/v1/lab/orders [patient,page=1,per_page=50]",
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

            if not isinstance(data, dict):
                response.failure(
                    "Laboratory order data is missing or invalid"
                )
                return

            items = data.get("items")
            total = data.get("total")
            page = data.get("page")
            per_page = data.get("per_page")

            if not isinstance(items, list):
                response.failure(
                    "Laboratory order items is not a list"
                )
                return

            if not isinstance(total, int):
                response.failure(
                    "Laboratory order total is not an integer"
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
                    f"Returned more than 50 lab orders: {len(items)}"
                )
                return

            for order in items:
                if not isinstance(order, dict):
                    response.failure(
                        "Laboratory order item is not an object"
                    )
                    return

                if order.get("patient_id") != patient_id:
                    response.failure(
                        "Laboratory order belongs to unexpected patient"
                    )
                    return

                if not isinstance(order.get("items"), list):
                    response.failure(
                        "Laboratory order items collection is invalid"
                    )
                    return

            response.success()