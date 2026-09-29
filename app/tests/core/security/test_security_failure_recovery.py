from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from redis.exceptions import ConnectionError, TimeoutError

from app import extensions
from app.core.auth.user.services.token_service import (
    REVOKED_TOKEN_PREFIX,
    is_token_revoked,
    revoke_token,
)
from app.core.exceptions import ValidationError


PROTECTED_ENDPOINT = (
    "/api/v1/patients?page=1&per_page=50"
)


class RedisDown:
    def __init__(self, error):
        self.error = error

    def exists(self, key):
        raise self.error

    def setex(self, key, seconds, value):
        raise self.error


class RedisHealthy:
    def __init__(self, revoked=False):
        self.revoked = revoked

    def exists(self, key):
        return 1 if self.revoked else 0


def test_protected_request_fails_closed_when_redis_connection_fails(
    client,
    user,
    auth_headers_for,
    monkeypatch,
):
    headers = auth_headers_for(user)

    monkeypatch.setattr(
        extensions,
        "redis_client",
        RedisDown(
            ConnectionError(
                "synthetic redis connection failure"
            )
        ),
    )

    response = client.get(
        PROTECTED_ENDPOINT,
        headers=headers,
    )

    assert response.status_code == 401


def test_protected_request_fails_closed_when_redis_times_out(
    client,
    user,
    auth_headers_for,
    monkeypatch,
):
    headers = auth_headers_for(user)

    monkeypatch.setattr(
        extensions,
        "redis_client",
        RedisDown(
            TimeoutError(
                "synthetic redis timeout"
            )
        ),
    )

    response = client.get(
        PROTECTED_ENDPOINT,
        headers=headers,
    )

    assert response.status_code == 401


def test_authorization_recovers_after_redis_restores(
    client,
    user,
    auth_headers_for,
    monkeypatch,
):
    headers = auth_headers_for(user)

    monkeypatch.setattr(
        extensions,
        "redis_client",
        RedisDown(
            ConnectionError(
                "synthetic redis connection failure"
            )
        ),
    )

    failed_response = client.get(
        PROTECTED_ENDPOINT,
        headers=headers,
    )

    assert failed_response.status_code == 401

    monkeypatch.setattr(
        extensions,
        "redis_client",
        RedisHealthy(
            revoked=False,
        ),
    )

    recovered_response = client.get(
        PROTECTED_ENDPOINT,
        headers=headers,
    )

    assert recovered_response.status_code == 200


def test_revoked_token_remains_denied_after_redis_recovery(
    client,
    user,
    auth_headers_for,
    monkeypatch,
):
    headers = auth_headers_for(user)

    monkeypatch.setattr(
        extensions,
        "redis_client",
        RedisHealthy(
            revoked=True,
        ),
    )

    response = client.get(
        PROTECTED_ENDPOINT,
        headers=headers,
    )

    assert response.status_code == 401


def test_revoke_token_fails_closed_when_redis_write_fails(
    app,
    user,
    monkeypatch,
):
    jwt_payload = {
        "jti": "synthetic-security-failure-jti",
        "exp": (
            datetime.now(timezone.utc)
            + timedelta(minutes=5)
        ).timestamp(),
    }

    monkeypatch.setattr(
        extensions,
        "redis_client",
        RedisDown(
            ConnectionError(
                "synthetic redis write failure"
            )
        ),
    )

    with pytest.raises(
        ValidationError,
        match="Unable to access token revocation storage",
    ):
        revoke_token(jwt_payload)


def test_revoke_token_recovers_after_redis_restores(
    app,
    user,
    monkeypatch,
):
    jwt_payload = {
        "jti": "synthetic-security-recovery-jti",
        "exp": (
            datetime.now(timezone.utc)
            + timedelta(minutes=5)
        ).timestamp(),
    }

    redis_mock = Mock()

    monkeypatch.setattr(
        extensions,
        "redis_client",
        redis_mock,
    )

    revoke_token(jwt_payload)

    expected_key = (
        f"{REVOKED_TOKEN_PREFIX}"
        f"{jwt_payload['jti']}"
    )

    redis_mock.setex.assert_called_once()

    call = redis_mock.setex.call_args

    assert call.args[0] == expected_key
    assert call.args[2] == "1"
    assert call.args[1] >= 1


def test_is_token_revoked_fails_closed_when_redis_is_unavailable(
    app,
    user,
    monkeypatch,
):
    payload = {
        "jti": "synthetic-fail-closed-jti",
        "sub": str(user.id),
        "token_version": user.token_version,
        "exp": (
            datetime.now(timezone.utc)
            + timedelta(minutes=5)
        ).timestamp(),
    }

    monkeypatch.setattr(
        extensions,
        "redis_client",
        RedisDown(
            ConnectionError(
                "synthetic redis availability failure"
            )
        ),
    )

    assert is_token_revoked(payload) is True


def test_is_token_revoked_allows_active_token_after_recovery(
    app,
    user,
    monkeypatch,
):
    payload = {
        "jti": "synthetic-recovered-jti",
        "sub": str(user.id),
        "token_version": user.token_version,
        "exp": (
            datetime.now(timezone.utc)
            + timedelta(minutes=5)
        ).timestamp(),
    }

    monkeypatch.setattr(
        extensions,
        "redis_client",
        RedisHealthy(
            revoked=False,
        ),
    )

    assert is_token_revoked(payload) is False