from __future__ import annotations

from app.core.observability import health


def test_liveness_is_public(
    client,
):
    response = client.get(
        "/health/live"
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body == {
        "success": True,
        "status": "ok",
    }


def test_readiness_reports_ready_when_dependencies_are_healthy(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        health,
        "collect_readiness",
        lambda: {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "ready": True,
            "database": {
                "healthy": True,
                "latency_ms": 1.0,
            },
            "redis": {
                "healthy": True,
                "latency_ms": 1.0,
            },
        },
    )

    response = client.get(
        "/health/ready"
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body == {
        "success": True,
        "status": "ready",
    }


def test_readiness_returns_service_unavailable_when_dependency_fails(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        health,
        "collect_readiness",
        lambda: {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "ready": False,
            "database": {
                "healthy": False,
                "latency_ms": 1.0,
            },
            "redis": {
                "healthy": True,
                "latency_ms": 1.0,
            },
        },
    )

    response = client.get(
        "/health/ready"
    )

    assert response.status_code == 503

    body = response.get_json()

    assert body == {
        "success": False,
        "status": "not_ready",
    }


def test_readiness_does_not_expose_dependency_details(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        health,
        "collect_readiness",
        lambda: {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "ready": False,
            "database": {
                "healthy": False,
                "latency_ms": 1.0,
            },
            "redis": {
                "healthy": False,
                "latency_ms": 1.0,
            },
        },
    )

    response = client.get(
        "/health/ready"
    )

    body = response.get_json()

    assert body == {
        "success": False,
        "status": "not_ready",
    }
