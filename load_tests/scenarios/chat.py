from __future__ import annotations

import os

from locust import HttpUser, between, task

from load_tests.common.auth import get_required_env
from load_tests.common.benchmark import get_load_test_id


class ChatUser(HttpUser):
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
    def list_chat_conversations(self) -> None:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
            "X-Load-Test-ID": self.load_test_id,
        }

        with self.client.get(
            "/api/v1/chat/conversations?page=1&per_page=50",
            headers=headers,
            name="GET /api/v1/chat/conversations [page=1,per_page=50]",
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
                    "Chat conversation response is not an object"
                )
                return

            if body.get("success") is not True:
                response.failure(
                    "Chat conversation response success != true"
                )
                return

            data = body.get("data")
            total = body.get("total")
            page = body.get("page")
            per_page = body.get("per_page")
            pages = body.get("pages")
            has_next = body.get("has_next")
            has_previous = body.get("has_previous")

            if not isinstance(data, list):
                response.failure(
                    "Chat conversation data is not a list"
                )
                return

            if not isinstance(total, int):
                response.failure(
                    "Chat conversation total is not an integer"
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

            if not isinstance(pages, int):
                response.failure(
                    "Chat conversation pages is not an integer"
                )
                return

            if not isinstance(has_next, bool):
                response.failure(
                    "Chat conversation has_next is not boolean"
                )
                return

            if not isinstance(has_previous, bool):
                response.failure(
                    "Chat conversation has_previous is not boolean"
                )
                return

            if len(data) > 50:
                response.failure(
                    f"Returned more than 50 conversations: {len(data)}"
                )
                return

            for item in data:
                if not isinstance(item, dict):
                    response.failure(
                        "Chat conversation item is not an object"
                    )
                    return

                if not isinstance(item.get("id"), int):
                    response.failure(
                        "Chat conversation id is not an integer"
                    )
                    return

                if not isinstance(item.get("clinic_id"), int):
                    response.failure(
                        "Chat conversation clinic_id is not an integer"
                    )
                    return

                if not isinstance(item.get("title"), (str, type(None))):
                    response.failure(
                        "Chat conversation title is not string/null"
                    )
                    return

                if not isinstance(
                    item.get("conversation_type"),
                    str,
                ):
                    response.failure(
                        "Chat conversation_type is not a string"
                    )
                    return

                if not isinstance(
                    item.get("status"),
                    str,
                ):
                    response.failure(
                        "Chat conversation status is not a string"
                    )
                    return

            response.success()