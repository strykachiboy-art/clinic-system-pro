from __future__ import annotations

import os

from locust import HttpUser, between, task

from load_tests.common.auth import get_required_env
from load_tests.common.benchmark import get_load_test_id


class DashboardUser(HttpUser):
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
    def get_dashboard(self) -> None:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
            "X-Load-Test-ID": self.load_test_id,
        }

        with self.client.get(
            "/api/v1/dashboard"
            "?date_from=2026-01-01"
            "&date_to=2026-12-31",
            headers=headers,
            name="GET /api/v1/dashboard [2026-01-01..2026-12-31]",
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
                    "Dashboard response is not an object"
                )
                return

            if body.get("success") is not True:
                response.failure(
                    "Dashboard response success != true"
                )
                return

            data = body.get("data")

            if not isinstance(data, dict):
                response.failure(
                    "Dashboard data is not an object"
                )
                return

            context = data.get("context")
            overview = data.get("overview")
            ai = data.get("ai")
            chat = data.get("chat")
            metrics = data.get("metrics")
            alerts = data.get("alerts")
            recent_activity = data.get("recent_activity")

            if not isinstance(context, dict):
                response.failure(
                    "Dashboard context is not an object"
                )
                return

            if not isinstance(context.get("role"), str):
                response.failure(
                    "Dashboard context role is not a string"
                )
                return

            if not isinstance(context.get("scope"), str):
                response.failure(
                    "Dashboard context scope is not a string"
                )
                return

            if not isinstance(context.get("clinic_id"), (int, type(None))):
                response.failure(
                    "Dashboard context clinic_id is not integer/null"
                )
                return

            if not isinstance(overview, dict):
                response.failure(
                    "Dashboard overview is not an object"
                )
                return

            overview_fields = (
                "total_patients",
                "active_patients",
                "total_staff",
                "active_staff",
                "appointments_today",
                "missed_appointments_today",
                "active_admissions",
                "occupied_beds",
                "pending_lab_orders",
            )

            for field in overview_fields:
                if not isinstance(overview.get(field), int):
                    response.failure(
                        f"Dashboard overview {field} is not an integer"
                    )
                    return

            if not isinstance(ai, dict):
                response.failure(
                    "Dashboard AI summary is not an object"
                )
                return

            ai_overview = ai.get("overview")

            if not isinstance(ai_overview, dict):
                response.failure(
                    "Dashboard AI overview is not an object"
                )
                return

            ai_fields = (
                "total_ai_requests",
                "total_credits_used",
                "total_tokens",
                "pending_reviews",
                "approved_reviews",
                "rejected_reviews",
                "high_risk_results",
                "critical_risk_results",
            )

            for field in ai_fields:
                if not isinstance(ai_overview.get(field), int):
                    response.failure(
                        f"Dashboard AI {field} is not an integer"
                    )
                    return

            if not isinstance(
                ai.get("feature_usage"),
                list,
            ):
                response.failure(
                    "Dashboard AI feature_usage is not a list"
                )
                return

            if not isinstance(
                ai.get("risk_summary"),
                list,
            ):
                response.failure(
                    "Dashboard AI risk_summary is not a list"
                )
                return

            if not isinstance(
                ai.get("approval_summary"),
                list,
            ):
                response.failure(
                    "Dashboard AI approval_summary is not a list"
                )
                return

            if not isinstance(chat, dict):
                response.failure(
                    "Dashboard chat summary is not an object"
                )
                return

            for field in (
                "unread_messages",
                "unread_conversations",
                "mentions",
                "priority_messages",
                "recent_messages",
            ):
                if not isinstance(chat.get(field), int):
                    response.failure(
                        f"Dashboard chat {field} is not an integer"
                    )
                    return

            if not isinstance(metrics, list):
                response.failure(
                    "Dashboard metrics is not a list"
                )
                return

            if not isinstance(alerts, list):
                response.failure(
                    "Dashboard alerts is not a list"
                )
                return

            if not isinstance(recent_activity, list):
                response.failure(
                    "Dashboard recent_activity is not a list"
                )
                return

            for metric in metrics:
                if not isinstance(metric, dict):
                    response.failure(
                        "Dashboard metric is not an object"
                    )
                    return

                if not isinstance(metric.get("key"), str):
                    response.failure(
                        "Dashboard metric key is not a string"
                    )
                    return

                if not isinstance(metric.get("label"), str):
                    response.failure(
                        "Dashboard metric label is not a string"
                    )
                    return

                if not isinstance(
                    metric.get("value"),
                    (int, float),
                ):
                    response.failure(
                        "Dashboard metric value is not numeric"
                    )
                    return

            for alert in alerts:
                if not isinstance(alert, dict):
                    response.failure(
                        "Dashboard alert is not an object"
                    )
                    return

                if not isinstance(alert.get("key"), str):
                    response.failure(
                        "Dashboard alert key is not a string"
                    )
                    return

                if not isinstance(alert.get("severity"), str):
                    response.failure(
                        "Dashboard alert severity is not a string"
                    )
                    return

                if not isinstance(alert.get("title"), str):
                    response.failure(
                        "Dashboard alert title is not a string"
                    )
                    return

                if not isinstance(alert.get("count"), int):
                    response.failure(
                        "Dashboard alert count is not an integer"
                    )
                    return

            for activity in recent_activity:
                if not isinstance(activity, dict):
                    response.failure(
                        "Dashboard recent activity item is not an object"
                    )
                    return

                if not isinstance(
                    activity.get("entity_type"),
                    str,
                ):
                    response.failure(
                        "Dashboard activity entity_type is not a string"
                    )
                    return

                if not isinstance(
                    activity.get("entity_id"),
                    int,
                ):
                    response.failure(
                        "Dashboard activity entity_id is not an integer"
                    )
                    return

                if not isinstance(
                    activity.get("action"),
                    str,
                ):
                    response.failure(
                        "Dashboard activity action is not a string"
                    )
                    return

            response.success()