from __future__ import annotations


def test_failure_dashboard_requires_authentication(
    client,
):
    response = client.get(
        "/api/v1/operations/failures"
    )

    assert response.status_code == 401


def test_failure_dashboard_rejects_non_admin(
    client,
    make_user,
    clinic,
    make_auth_headers,
):
    from app.core.enums.role_enums import Role

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/v1/operations/failures",
        headers=make_auth_headers(actor),
    )

    assert response.status_code == 403
    assert response.get_json()["error"] == (
        "Insufficient permissions"
    )


def test_failure_dashboard_accepts_admin(
    client,
    user,
    make_auth_headers,
    monkeypatch,
):
    import app.core.observability.failure_dashboard_routes as routes

    monkeypatch.setattr(
        routes,
        "get_failure_dashboard",
        lambda actor_id, limit=50: {
            "schema_version": "v1",
            "scope": "platform",
            "timestamp": (
                "2026-09-29T10:00:00+00:00"
            ),
            "recent_failures": [],
            "summary": {
                "recent_failure_count": 0,
                "by_component": {},
                "by_event_type": {},
                "by_severity": {},
                "latest_failure_at": None,
            },
            "state_store_available": True,
        },
    )

    response = client.get(
        "/api/v1/operations/failures",
        headers=make_auth_headers(user),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["scope"] == "platform"


def test_failure_dashboard_returns_domain_errors(
    client,
    user,
    make_auth_headers,
    monkeypatch,
):
    import app.core.observability.failure_dashboard_routes as routes
    from app.core.exceptions import ValidationError

    def _raise(
        actor_id,
        limit=50,
    ):
        raise ValidationError(
            "Failure dashboard unavailable"
        )

    monkeypatch.setattr(
        routes,
        "get_failure_dashboard",
        _raise,
    )

    response = client.get(
        "/api/v1/operations/failures",
        headers=make_auth_headers(user),
    )

    assert response.status_code == 422
    assert response.get_json()["success"] is False
