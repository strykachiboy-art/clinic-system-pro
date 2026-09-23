from __future__ import annotations

from typing import Any

import pytest

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
from load_tests.resilience.profiles.slow_3g import (
    PROFILE as SLOW_3G_PROFILE,
)


PATIENTS_ENDPOINT = (
    "/api/v1/patients?page=1&per_page=50"
)


def _headers(
    token: str,
) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "X-Load-Test-ID": "resilience-http",
    }


def _token(
    user,
    auth_headers_for,
) -> str:
    authorization = auth_headers_for(
        user
    )["Authorization"]

    return authorization.removeprefix(
        "Bearer "
    )


def _request_patients(
    client: Any,
    token: str,
):
    return client.get(
        PATIENTS_ENDPOINT,
        headers=_headers(token),
    )


def _assert_patient_response(
    response: Any,
) -> dict[str, Any]:
    assert_http_status(
        response,
        200,
    )

    body = assert_success_response(
        response,
    )

    data = body.get(
        "data"
    )

    assert isinstance(
        data,
        dict,
    )

    items = data.get(
        "items"
    )

    assert isinstance(
        items,
        list,
    )

    total = data.get(
        "total"
    )

    assert isinstance(
        total,
        int,
    )

    page = data.get(
        "page"
    )

    assert page == 1

    per_page = data.get(
        "per_page"
    )

    assert per_page == 50

    assert len(items) <= 50

    return data


def test_http_request_succeeds_normally(
    client,
    user,
    auth_headers_for,
):
    response = _request_patients(
        client,
        _token(
            user,
            auth_headers_for,
        ),
    )

    _assert_patient_response(
        response
    )


def test_http_request_succeeds_under_high_latency(
    client,
    user,
    auth_headers_for,
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

    response = _request_patients(
        client,
        _token(
            user,
            auth_headers_for,
        ),
    )

    _assert_patient_response(
        response
    )

    assert delays == [1.2]


@pytest.mark.parametrize(
    "profile,expected_delay",
    [
        (SLOW_2G_PROFILE, 0.7),
        (SLOW_3G_PROFILE, 0.25),
    ],
)
def test_http_request_succeeds_under_slow_network_profile(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    profile,
    expected_delay,
):
    delays: list[float] = []

    monkeypatch.setattr(
        "load_tests.resilience.common.network.sleep",
        delays.append,
    )

    inject_network_conditions(
        profile,
        seed=123,
    )

    response = _request_patients(
        client,
        _token(
            user,
            auth_headers_for,
        ),
    )

    _assert_patient_response(
        response
    )

    assert delays == [expected_delay]


def test_http_request_succeeds_with_jitter_profile(
    client,
    user,
    auth_headers_for,
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

    response = _request_patients(
        client,
        _token(
            user,
            auth_headers_for,
        ),
    )

    _assert_patient_response(
        response
    )

    assert len(delays) == 1
    assert 0.2 <= delays[0] <= 0.8


def test_http_request_succeeds_with_bandwidth_limitation(
    client,
    user,
    auth_headers_for,
    monkeypatch,
):
    delays: list[float] = []

    monkeypatch.setattr(
        "load_tests.resilience.common.network.sleep",
        delays.append,
    )

    payload_bytes = 16_000

    inject_network_conditions(
        BANDWIDTH_LIMITED_PROFILE,
        payload_bytes=payload_bytes,
        seed=123,
    )

    response = _request_patients(
        client,
        _token(
            user,
            auth_headers_for,
        ),
    )

    _assert_patient_response(
        response
    )

    assert len(delays) == 1

    expected_delay = (
        0.2 + 1.0
    )

    assert delays[0] == pytest.approx(
        expected_delay
    )


def test_http_packet_loss_is_classified_before_request_dispatch(
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

    monkeypatch.setattr(
        "load_tests.resilience.common.network.should_interrupt",
        lambda profile, rng: False,
    )

    with pytest.raises(
        NetworkFault,
        match=(
            "Injected packet loss "
            "for profile packet_loss"
        ),
    ):
        inject_network_conditions(
            PACKET_LOSS_PROFILE,
            seed=123,
        )


def test_http_interruption_is_classified_before_request_dispatch(
    monkeypatch,
):
    delays: list[float] = []

    monkeypatch.setattr(
        "load_tests.resilience.common.network.sleep",
        delays.append,
    )

    monkeypatch.setattr(
        "load_tests.resilience.common.network.should_drop",
        lambda profile, rng: False,
    )

    monkeypatch.setattr(
        "load_tests.resilience.common.network.should_interrupt",
        lambda profile, rng: True,
    )

    with pytest.raises(
        NetworkFault,
        match=(
            "Injected connection interruption "
            "for profile intermittent"
        ),
    ):
        inject_network_conditions(
            INTERMITTENT_PROFILE,
            seed=123,
        )

    assert delays == [0.3]


def test_http_patient_response_preserves_expected_pagination_contract(
    client,
    user,
    auth_headers_for,
):
    response = _request_patients(
        client,
        _token(
            user,
            auth_headers_for,
        ),
    )

    data = _assert_patient_response(
        response
    )

    assert data["page"] == 1
    assert data["per_page"] == 50
    assert data["total"] >= 0

    for item in data["items"]:
        assert isinstance(
            item,
            dict,
        )


@pytest.mark.parametrize(
    "profile",
    [
        HIGH_LATENCY_PROFILE,
        SLOW_2G_PROFILE,
        SLOW_3G_PROFILE,
        JITTER_PROFILE,
        BANDWIDTH_LIMITED_PROFILE,
    ],
)
def test_http_profiles_do_not_change_endpoint_contract(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    profile,
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
        lambda profile, rng: False,
    )

    inject_network_conditions(
        profile,
        payload_bytes=16_000,
        seed=123,
    )

    response = _request_patients(
        client,
        _token(
            user,
            auth_headers_for,
        ),
    )

    data = _assert_patient_response(
        response
    )

    assert data["page"] == 1
    assert data["per_page"] == 50
    assert data["total"] >= 0


def test_http_repeated_read_requests_remain_consistent(
    client,
    user,
    auth_headers_for,
):
    token = _token(
        user,
        auth_headers_for,
    )

    first = _request_patients(
        client,
        token,
    )

    second = _request_patients(
        client,
        token,
    )

    first_data = _assert_patient_response(
        first
    )

    second_data = _assert_patient_response(
        second
    )

    assert (
        first_data["page"]
        == second_data["page"]
    )

    assert (
        first_data["per_page"]
        == second_data["per_page"]
    )

    assert (
        first_data["total"]
        == second_data["total"]
    )

    assert (
        first_data["items"]
        == second_data["items"]
    )