from __future__ import annotations

from locust import HttpUser, between, task

from load_tests.common.auth import get_required_env
from load_tests.common.benchmark import get_load_test_id


class UserDevicesUser(HttpUser):
    wait_time = between(
        1,
        3,
    )

    load_test_id = get_load_test_id()

    def on_start(self):
        self.access_token = self._login()

    def _login(self):
        email = get_required_env(
            "LOCUST_EMAIL"
        )

        password = get_required_env(
            "LOCUST_PASSWORD"
        )

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Load-Test-ID": self.load_test_id,
        }

        payload = {
            "email": email,
            "password": password,
        }

        with self.client.post(
            "/api/v1/auth/login",
            json=payload,
            headers=headers,
            name="POST /api/v1/auth/login [setup]",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"Unexpected HTTP "
                    f"{response.status_code}: "
                    f"{response.text[:200]}"
                )
                raise RuntimeError(
                    "Load-test authentication failed"
                )

            try:
                body = response.json()
            except ValueError as exc:
                response.failure(
                    "HTTP 200 but response was not JSON"
                )
                raise RuntimeError(
                    "Load-test authentication "
                    "returned invalid JSON"
                ) from exc

            if body.get("success") is not True:
                response.failure(
                    "HTTP 200 but success != true"
                )
                raise RuntimeError(
                    "Load-test authentication "
                    "returned success != true"
                )

            data = body.get("data")

            if not isinstance(data, dict):
                response.failure(
                    "Login response data is missing "
                    "or invalid"
                )
                raise RuntimeError(
                    "Load-test authentication "
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
                    "Load-test authentication "
                    "returned no access token"
                )

            response.success()

            return access_token

    @task
    def list_user_devices(self):
        headers = {
            "Authorization": (
                f"Bearer {self.access_token}"
            ),
            "Accept": "application/json",
            "X-Load-Test-ID": self.load_test_id,
        }

        with self.client.get(
            "/api/v1/users/devices/"
            "?page=1&per_page=20",
            headers=headers,
            name=(
                "GET /api/v1/users/devices/ "
                "[page=1,per_page=20]"
            ),
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"Unexpected HTTP "
                    f"{response.status_code}: "
                    f"{response.text[:200]}"
                )
                return

            try:
                body = response.json()
            except ValueError:
                response.failure(
                    "HTTP 200 but response "
                    "was not JSON"
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
                    "Response data is missing "
                    "or invalid"
                )
                return

            items = data.get("items")

            if not isinstance(items, list):
                response.failure(
                    "Response items is missing "
                    "or invalid"
                )
                return

            if data.get("page") != 1:
                response.failure(
                    "Unexpected page value"
                )
                return

            if data.get("per_page") != 20:
                response.failure(
                    "Unexpected per_page value"
                )
                return

            total = data.get("total")

            if not isinstance(total, int):
                response.failure(
                    "total must be an integer"
                )
                return

            if total < 0:
                response.failure(
                    "total cannot be negative"
                )
                return

            pages = data.get("pages")

            if not isinstance(pages, int):
                response.failure(
                    "pages must be an integer"
                )
                return

            if pages < 0:
                response.failure(
                    "pages cannot be negative"
                )
                return

            if not isinstance(
                data.get("has_next"),
                bool,
            ):
                response.failure(
                    "has_next must be boolean"
                )
                return

            if not isinstance(
                data.get("has_prev"),
                bool,
            ):
                response.failure(
                    "has_prev must be boolean"
                )
                return

            if len(items) > 20:
                response.failure(
                    "Returned more than "
                    "20 devices"
                )
                return

            for item in items:
                if not isinstance(
                    item,
                    dict,
                ):
                    response.failure(
                        "Device item must "
                        "be an object"
                    )
                    return

                if not isinstance(
                    item.get("id"),
                    int,
                ):
                    response.failure(
                        "Device id must "
                        "be an integer"
                    )
                    return

                if not isinstance(
                    item.get("user_id"),
                    int,
                ):
                    response.failure(
                        "Device user_id must "
                        "be an integer"
                    )
                    return

                if not isinstance(
                    item.get("device_token"),
                    str,
                ):
                    response.failure(
                        "Device token must "
                        "be a string"
                    )
                    return

                device_name = item.get(
                    "device_name"
                )

                if (
                    device_name is not None
                    and not isinstance(
                        device_name,
                        str,
                    )
                ):
                    response.failure(
                        "device_name must "
                        "be string or null"
                    )
                    return

                if not isinstance(
                    item.get("platform"),
                    str,
                ):
                    response.failure(
                        "platform must "
                        "be a string"
                    )
                    return

                if not isinstance(
                    item.get("is_active"),
                    bool,
                ):
                    response.failure(
                        "is_active must "
                        "be boolean"
                    )
                    return

                for field in (
                    "last_seen_at",
                    "created_at",
                    "updated_at",
                ):
                    if field not in item:
                        response.failure(
                            f"Missing field: {field}"
                        )
                        return

            response.success()