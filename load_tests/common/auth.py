from __future__ import annotations

import os

from locust import HttpUser


def get_required_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"{name} is required")

    return value


def login(
    user: HttpUser,
    load_test_id: str,
) -> dict[str, str | int]:
    email = get_required_env("LOCUST_EMAIL")
    password = get_required_env("LOCUST_PASSWORD")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Load-Test-ID": load_test_id,
    }

    payload = {
        "email": email,
        "password": password,
    }

    with user.client.post(
        "/api/v1/auth/login",
        json=payload,
        headers=headers,
        name="POST /api/v1/auth/login",
        catch_response=True,
    ) as response:
        if response.status_code != 200:
            response.failure(
                f"Unexpected HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )
            return {}

        try:
            body = response.json()
        except ValueError:
            response.failure(
                "HTTP 200 but response was not JSON"
            )
            return {}

        if body.get("success") is not True:
            response.failure(
                "HTTP 200 but success != true"
            )
            return {}

        data = body.get("data")

        if not isinstance(data, dict):
            response.failure(
                "Login response data is missing or invalid"
            )
            return {}

        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")

        if not access_token:
            response.failure(
                "Login response has no access_token"
            )
            return {}

        if not refresh_token:
            response.failure(
                "Login response has no refresh_token"
            )
            return {}

        response.success()

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user_id": data.get("user_id", 0),
            "role": data.get("role", ""),
        }