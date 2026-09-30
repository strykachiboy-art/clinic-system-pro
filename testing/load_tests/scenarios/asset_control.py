from __future__ import annotations

from locust import HttpUser, between, task

from load_tests.common.auth import get_required_env
from load_tests.common.benchmark import get_load_test_id


class AssetControlUser(HttpUser):
    wait_time = between(
        1,
        3,
    )

    load_test_id = get_load_test_id()

    def on_start(self) -> None:
        self.access_token = self._login()

    def _login(self) -> str:
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
                    "Benchmark authentication returned invalid data"
                )

            access_token = data.get(
                "access_token"
            )

            if not access_token:
                response.failure(
                    "Login response has no access_token"
                )
                raise RuntimeError(
                    "Benchmark authentication returned no access token"
                )

            response.success()

            return str(access_token)

    @task
    def list_assets(self) -> None:
        headers = {
            "Authorization": (
                f"Bearer {self.access_token}"
            ),
            "Accept": "application/json",
            "X-Load-Test-ID": self.load_test_id,
        }

        with self.client.get(
            "/api/v1/assets"
            "?page=1&per_page=50",
            headers=headers,
            name=(
                "GET /api/v1/assets "
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
                    "Asset response is not an object"
                )
                return

            if body.get("success") is not True:
                response.failure(
                    "Asset response success != true"
                )
                return

            items = body.get("items")

            if not isinstance(items, list):
                response.failure(
                    "Asset items is missing or invalid"
                )
                return

            if body.get("page") != 1:
                response.failure(
                    "Unexpected page value"
                )
                return

            if body.get("per_page") != 50:
                response.failure(
                    "Unexpected per_page value"
                )
                return

            total = body.get("total")

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

            pages = body.get("pages")

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
                body.get("has_next"),
                bool,
            ):
                response.failure(
                    "has_next must be boolean"
                )
                return

            if not isinstance(
                body.get("has_prev"),
                bool,
            ):
                response.failure(
                    "has_prev must be boolean"
                )
                return

            if len(items) > 50:
                response.failure(
                    "Returned more than 50 assets"
                )
                return

            for item in items:
                if not isinstance(item, dict):
                    response.failure(
                        "Asset item must be an object"
                    )
                    return

                if not isinstance(
                    item.get("id"),
                    int,
                ):
                    response.failure(
                        "Asset id must be an integer"
                    )
                    return

                if not isinstance(
                    item.get("clinic_id"),
                    int,
                ):
                    response.failure(
                        "Asset clinic_id must be an integer"
                    )
                    return

                if not isinstance(
                    item.get("asset_tag"),
                    str,
                ):
                    response.failure(
                        "Asset asset_tag must be a string"
                    )
                    return

                if not isinstance(
                    item.get("name"),
                    str,
                ):
                    response.failure(
                        "Asset name must be a string"
                    )
                    return

                if not isinstance(
                    item.get("category"),
                    str,
                ):
                    response.failure(
                        "Asset category must be a string"
                    )
                    return

                if not isinstance(
                    item.get("status"),
                    str,
                ):
                    response.failure(
                        "Asset status must be a string"
                    )
                    return

                if not isinstance(
                    item.get("condition"),
                    str,
                ):
                    response.failure(
                        "Asset condition must be a string"
                    )
                    return

                if not isinstance(
                    item.get("ownership"),
                    str,
                ):
                    response.failure(
                        "Asset ownership must be a string"
                    )
                    return

                if not isinstance(
                    item.get("maintenance_status"),
                    str,
                ):
                    response.failure(
                        "Asset maintenance_status "
                        "must be a string"
                    )
                    return

                if not isinstance(
                    item.get("is_active"),
                    bool,
                ):
                    response.failure(
                        "Asset is_active must be boolean"
                    )
                    return

                for field in (
                    "created_at",
                    "updated_at",
                ):
                    if field not in item:
                        response.failure(
                            f"Missing field: {field}"
                        )
                        return

            response.success()