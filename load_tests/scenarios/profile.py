from __future__ import annotations

import os

from locust import HttpUser, between, task

from load_tests.common.auth import get_required_env
from load_tests.common.benchmark import get_load_test_id


class ProfileUser(HttpUser):
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
    def get_my_profile(self) -> None:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
            "X-Load-Test-ID": self.load_test_id,
        }

        with self.client.get(
            "/api/v1/profile/me",
            headers=headers,
            name="GET /api/v1/profile/me",
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
                    "Profile response is not an object"
                )
                return

            if body.get("success") is not True:
                response.failure(
                    "Profile response success != true"
                )
                return

            data = body.get("data")

            if not isinstance(data, dict):
                response.failure(
                    "Profile data is not an object"
                )
                return

            user = data.get("user")
            staff = data.get("staff")
            clinic = data.get("clinic")

            if not isinstance(user, dict):
                response.failure(
                    "Profile user is not an object"
                )
                return

            if not isinstance(user.get("id"), int):
                response.failure(
                    "Profile user id is not an integer"
                )
                return

            if not isinstance(user.get("email"), (str, type(None))):
                response.failure(
                    "Profile user email is not string/null"
                )
                return

            if not isinstance(user.get("is_active"), bool):
                response.failure(
                    "Profile user is_active is not boolean"
                )
                return

            if not isinstance(user.get("clinic_id"), (int, type(None))):
                response.failure(
                    "Profile user clinic_id is not integer/null"
                )
                return

            if staff is not None:
                if not isinstance(staff, dict):
                    response.failure(
                        "Profile staff is not an object/null"
                    )
                    return

                if not isinstance(staff.get("id"), int):
                    response.failure(
                        "Profile staff id is not an integer"
                    )
                    return

                if not isinstance(staff.get("clinic_id"), int):
                    response.failure(
                        "Profile staff clinic_id is not an integer"
                    )
                    return

                if not isinstance(staff.get("user_id"), (int, type(None))):
                    response.failure(
                        "Profile staff user_id is not integer/null"
                    )
                    return

                if not isinstance(staff.get("first_name"), str):
                    response.failure(
                        "Profile staff first_name is not a string"
                    )
                    return

                if not isinstance(staff.get("last_name"), str):
                    response.failure(
                        "Profile staff last_name is not a string"
                    )
                    return

                if not isinstance(staff.get("status"), str):
                    response.failure(
                        "Profile staff status is not a string"
                    )
                    return

            if clinic is not None:
                if not isinstance(clinic, dict):
                    response.failure(
                        "Profile clinic is not an object/null"
                    )
                    return

                if not isinstance(clinic.get("id"), int):
                    response.failure(
                        "Profile clinic id is not an integer"
                    )
                    return

                if not isinstance(clinic.get("name"), str):
                    response.failure(
                        "Profile clinic name is not a string"
                    )
                    return

                if not isinstance(clinic.get("status"), str):
                    response.failure(
                        "Profile clinic status is not a string"
                    )
                    return

            response.success()