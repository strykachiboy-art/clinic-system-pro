from __future__ import annotations

import os


PROTECTED_ENDPOINT = (
    "/api/v1/patients?page=1&per_page=50"
)


def test_protected_request_uses_real_redis_revocation_path(
    client,
    user,
    auth_headers_for,
):
    expected_state = os.getenv(
        "GATE10_REDIS_EXPECTED",
        "healthy",
    )

    assert expected_state in {
        "healthy",
        "down",
    }

    test_redis_url = os.getenv(
        "TEST_REDIS_URL"
    )

    assert test_redis_url, (
        "TEST_REDIS_URL is required"
    )

    response = client.get(
        PROTECTED_ENDPOINT,
        headers=auth_headers_for(user),
    )

    expected_status = (
        200
        if expected_state == "healthy"
        else 401
    )

    assert response.status_code == expected_status