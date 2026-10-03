from __future__ import annotations

import pytest


@pytest.fixture()
def e2e_login(client):
    def _login(email: str, password: str = "supersecret") -> dict:
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": email,
                "password": password,
            },
        )

        assert response.status_code == 200, response.get_json()

        body = response.get_json()

        assert body["success"] is True
        assert isinstance(body["data"], dict)
        assert body["data"]["access_token"]

        return body["data"]

    return _login


@pytest.fixture()
def e2e_headers(e2e_login):
    def _headers(
        email: str,
        password: str = "supersecret",
    ) -> dict[str, str]:
        result = e2e_login(
            email,
            password,
        )

        return {
            "Authorization": (
                f"Bearer {result['access_token']}"
            ),
        }

    return _headers