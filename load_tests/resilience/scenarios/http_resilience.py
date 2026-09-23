from __future__ import annotations

from typing import Any

from app.extensions import db

from load_tests.resilience.common.assertions import (
    assert_http_status,
    assert_success_response,
)
from load_tests.resilience.common.network import (
    NetworkFault,
    inject_network_conditions,
)
from load_tests.resilience.profiles.high_latency import (
    PROFILE as HIGH_LATENCY_PROFILE,
)
from load_tests.resilience.profiles.intermittent import (
    PROFILE as INTERMITTENT_PROFILE,
)


PATIENTS_ENDPOINT = (
    "/api/v1/patients?page=1&per_page=50"
)


def _headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "X-Load-Test-ID": "resilience-http",
    }


def _request_patients(
    client: Any,
    token: str,
):
    return client.get(
        PATIENTS_ENDPOINT,
        headers=_headers(token),
    )


def test_http_request_succeeds_under_high_latency(
    client,
    user,
    auth_headers_for,
    monkeypatch,
):
    headers = _headers(
        auth_headers_for(user)["Authorization"].removeprefix(
            "Bearer "
        )
    )

    injected_delays: list[float] = []

    monkeypatch.setattr(
        "load_tests.resilience.common.network.sleep",
        injected_delays.append,
    )

    inject_network_conditions(
        HIGH_LATENCY_PROFILE,
        seed=123,
    )

    response = client.get(
        PATIENTS_ENDPOINT,
        headers=headers,
    )

    assert_http_status(
        response,
        200,
    )

    assert_success_response(
        response,
    )

    assert injected_delays
    assert injected_delays[0] == 1.2


def test_http_interruption_is_classified_as_network_fault(
    monkeypatch,
):
    interrupted = []

    def fake_sleep(seconds: float) -> None:
        interrupted.append(seconds)

    monkeypatch.setattr(
        "load_tests.resilience.common.network.sleep",
        fake_sleep,
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

    assert interrupted == [0.3]


def test_http_interruption_does_not_create_database_changes(
    app,
    db,
    user,
    monkeypatch,
):
    with app.app_context():
        before = db.session.execute(
            db.select(
                db.func.count()
                if False
                else db.text(
                    "SELECT COUNT(*) "
                    "FROM patients"
                )
            )
        ).scalar_one()

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

        with __import__(
            "pytest"
        ).raises(NetworkFault):
            inject_network_conditions(
                INTERMITTENT_PROFILE,
                seed=123,
            )

        after = db.session.execute(
            db.text(
                "SELECT COUNT(*) FROM patients"
            )
        ).scalar_one()

        assert after == before