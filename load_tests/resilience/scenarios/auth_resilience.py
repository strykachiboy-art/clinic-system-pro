from __future__ import annotations

from typing import Any

from flask_jwt_extended import create_refresh_token

from load_tests.resilience.common.assertions import (
    assert_http_status,
    assert_success_response,
)
from load_tests.resilience.common.network import (
    NetworkFault,
    inject_network_conditions,
)
from load_tests.resilience.profiles.bandwidth_limited import (
    PROFILE as BANDWIDTH_LIMITED_PROFILE,
)
from load_tests.resilience.profiles.high_latency import (
    PROFILE as HIGH_LATENCY_PROFILE,
)
from load_tests.resilience.profiles.intermittent import (
    PROFILE as INTERMITTENT_PROFILE,
)
from load_tests.resilience.profiles.jitter import (
    PROFILE as JITTER_PROFILE,
)
from load_tests.resilience.profiles.packet_loss import (
    PROFILE as PACKET_LOSS_PROFILE,
)
from load_tests.resilience.profiles.slow_2g import (
    PROFILE as SLOW_2G_PROFILE,
)


LOGIN_ENDPOINT = "/api/v1/auth/login"
REFRESH_ENDPOINT = "/api/v1/auth/refresh"
LOGOUT_ENDPOINT = "/api/v1/auth/logout"
PROTECTED_ENDPOINT = (
    "/api/v1/patients?page=1&per_page=50"
)


def _load_headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Load-Test-ID": "resilience-auth",
    }


def _bearer_headers(
    token: str,
) -> dict[str, str]:
    headers = _load_headers()
    headers["Authorization"] = (
        f"Bearer {token}"
    )
    return headers


def _login(
    client: Any,
    user,
):
    return client.post(
        LOGIN_ENDPOINT,
        json={
            "email": user.email,
            "password": "supersecret",
        },
        headers=_load_headers(),
    )


def _refresh_headers(
    app,
    user,
) -> dict[str, str]:
    with app.test_request_context():
        token = create_refresh_token(
            identity=str(user.id),
            additional_claims={
                "token_version": user.token_version,
            },
        )

    return _bearer_headers(token)


def test_login_succeeds_under_high_latency(
    client,
    user,
    monkeypatch,
):
    delays: list[float] = []

    monkeypatch.setattr(
        "load_tests.resilience.common.network.sleep",
        delays.append,
    )

    inject_network_conditions(
        HIGH_LATENCY_PROFILE,
        seed=123,
    )

    response = _login(
        client,
        user,
    )

    assert_http_status(
        response,
        200,
    )

    assert_success_response(
        response,
    )

    body = response.get_json()

    assert body["data"]["access_token"]
    assert body["data"]["refresh_token"]
    assert body["data"]["user_id"] == user.id
    assert body["data"]["role"] == user.role.value

    assert delays == [1.2]


def test_login_succeeds_under_slow_2g(
    client,
    user,
    monkeypatch,
):
    delays: list[float] = []

    monkeypatch.setattr(
        "load_tests.resilience.common.network.sleep",
        delays.append,
    )

    inject_network_conditions(
        SLOW_2G_PROFILE,
        payload_bytes=1024,
        seed=123,
    )

    response = _login(
        client,
        user,
    )

    assert_http_status(
        response,
        200,
    )

    assert_success_response(
        response,
    )

    body = response.get_json()

    assert body["data"]["access_token"]
    assert body["data"]["refresh_token"]
    assert body["data"]["user_id"] == user.id
    assert body["data"]["role"] == user.role.value

    assert delays == [
        0.7 + (1024 * 8 / (50 * 1000))
    ]


def test_login_succeeds_under_jitter(
    client,
    user,
    monkeypatch,
):
    delays: list[float] = []

    monkeypatch.setattr(
        "load_tests.resilience.common.network.sleep",
        delays.append,
    )

    inject_network_conditions(
        JITTER_PROFILE,
        seed=123,
    )

    response = _login(
        client,
        user,
    )

    assert_http_status(
        response,
        200,
    )

    assert_success_response(
        response,
    )

    body = response.get_json()

    assert body["data"]["access_token"]
    assert body["data"]["refresh_token"]
    assert body["data"]["user_id"] == user.id
    assert body["data"]["role"] == user.role.value

    assert len(delays) == 1
    assert 0.2 <= delays[0] <= 0.8


def test_login_recovers_after_packet_loss(
    client,
    user,
    monkeypatch,
):
    monkeypatch.setattr(
        "load_tests.resilience.common.network.sleep",
        lambda seconds: None,
    )

    monkeypatch.setattr(
        "load_tests.resilience.common.network.should_drop",
        lambda profile, rng: True,
    )

    try:
        inject_network_conditions(
            PACKET_LOSS_PROFILE,
            seed=123,
        )
    except NetworkFault as exc:
        assert (
            str(exc)
            == "Injected packet loss "
            "for profile packet_loss"
        )
    else:
        raise AssertionError(
            "Expected NetworkFault"
        )

    response = _login(
        client,
        user,
    )

    assert_http_status(
        response,
        200,
    )

    assert_success_response(
        response,
    )


def test_login_recovers_after_intermittent_interruption(
    client,
    user,
    monkeypatch,
):
    monkeypatch.setattr(
        "load_tests.resilience.common.network.sleep",
        lambda seconds: None,
    )

    monkeypatch.setattr(
        "load_tests.resilience.common.network.should_drop",
        lambda profile, rng: False,
    )

    monkeypatch.setattr(
        "load_tests.resilience.common.network.should_interrupt",
        lambda profile, rng: True,
    )

    try:
        inject_network_conditions(
            INTERMITTENT_PROFILE,
            seed=123,
        )
    except NetworkFault as exc:
        assert (
            str(exc)
            == "Injected connection interruption "
            "for profile intermittent"
        )
    else:
        raise AssertionError(
            "Expected NetworkFault"
        )

    response = _login(
        client,
        user,
    )

    assert_http_status(
        response,
        200,
    )

    assert_success_response(
        response,
    )


def test_refresh_succeeds_under_bandwidth_limit(
    app,
    client,
    user,
    monkeypatch,
):
    delays: list[float] = []

    monkeypatch.setattr(
        "load_tests.resilience.common.network.sleep",
        delays.append,
    )

    inject_network_conditions(
        BANDWIDTH_LIMITED_PROFILE,
        payload_bytes=1024,
        seed=123,
    )

    response = client.post(
        REFRESH_ENDPOINT,
        headers=_refresh_headers(
            app,
            user,
        ),
    )

    assert_http_status(
        response,
        200,
    )

    assert_success_response(
        response,
    )

    body = response.get_json()

    assert body["data"]["access_token"]
    assert body["data"]["refresh_token"]
    assert body["data"]["user_id"] == user.id
    assert body["data"]["role"] == user.role.value

    assert delays == [
        0.2 + (1024 * 8 / (128 * 1000))
    ]


def test_revoked_refresh_token_cannot_be_reused_after_recovery(
    app,
    client,
    user,
):
    headers = _refresh_headers(
        app,
        user,
    )

    first_response = client.post(
        REFRESH_ENDPOINT,
        headers=headers,
    )

    assert_http_status(
        first_response,
        200,
    )

    second_response = client.post(
        REFRESH_ENDPOINT,
        headers=headers,
    )

    assert_http_status(
        second_response,
        401,
    )

    body = second_response.get_json()

    assert body["msg"] == "Token has been revoked"


def test_logout_revokes_access_after_network_delay(
    client,
    user,
    monkeypatch,
):
    login_response = _login(
        client,
        user,
    )

    assert_http_status(
        login_response,
        200,
    )

    body = login_response.get_json()

    access_token = body["data"]["access_token"]
    refresh_token = body["data"]["refresh_token"]

    delays: list[float] = []

    monkeypatch.setattr(
        "load_tests.resilience.common.network.sleep",
        delays.append,
    )

    inject_network_conditions(
        HIGH_LATENCY_PROFILE,
        seed=123,
    )

    logout_response = client.post(
        LOGOUT_ENDPOINT,
        json={
            "refresh_token": refresh_token,
        },
        headers=_bearer_headers(
            access_token,
        ),
    )

    assert_http_status(
        logout_response,
        200,
    )

    assert_success_response(
        logout_response,
    )

    protected_response = client.get(
        PROTECTED_ENDPOINT,
        headers=_bearer_headers(
            access_token,
        ),
    )

    assert_http_status(
        protected_response,
        401,
    )

    assert delays == [1.2]


def test_token_version_invalidation_survives_network_recovery(
    client,
    user,
    auth_headers_for,
    monkeypatch,
):
    access_token = auth_headers_for(
        user,
    )["Authorization"].removeprefix(
        "Bearer "
    )

    from app.core.auth.user.services.token_service import (
        revoke_user_tokens,
    )

    revoke_user_tokens(
        user.id,
    )

    monkeypatch.setattr(
        "load_tests.resilience.common.network.sleep",
        lambda seconds: None,
    )

    inject_network_conditions(
        HIGH_LATENCY_PROFILE,
        seed=123,
    )

    response = client.get(
        PROTECTED_ENDPOINT,
        headers=_bearer_headers(
            access_token,
        ),
    )

    assert_http_status(
        response,
        401,
    )


def test_authenticated_request_remains_valid_under_network_degradation(
    client,
    user,
    auth_headers_for,
    monkeypatch,
):
    access_token = auth_headers_for(
        user,
    )["Authorization"].removeprefix(
        "Bearer "
    )

    monkeypatch.setattr(
        "load_tests.resilience.common.network.sleep",
        lambda seconds: None,
    )

    inject_network_conditions(
        SLOW_2G_PROFILE,
        payload_bytes=2048,
        seed=123,
    )

    response = client.get(
        PROTECTED_ENDPOINT,
        headers=_bearer_headers(
            access_token,
        ),
    )

    assert_http_status(
        response,
        200,
    )

    assert_success_response(
        response,
    )