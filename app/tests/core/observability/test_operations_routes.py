from __future__ import annotations


def test_operations_route_requires_authentication(
    client,
):
    response = client.get(
        "/api/v1/operations"
    )

    assert response.status_code == 401


def test_operations_route_rejects_non_admin(
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
        "/api/v1/operations",
        headers=make_auth_headers(actor),
    )

    assert response.status_code == 403
    assert response.get_json()["error"] == (
        "Insufficient permissions"
    )


def test_operations_route_accepts_admin(
    client,
    user,
    make_auth_headers,
    monkeypatch,
):
    import app.core.observability.operations_routes as routes

    monkeypatch.setattr(
        routes,
        "get_operational_dashboard",
        lambda actor_id: {
            "schema_version": "v1",
            "scope": "platform",
            "healthy": True,
            "components": {},
            "alerts": {
                "current_conditions": [],
                "current_count": 0,
                "active": [],
                "active_count": 0,
                "critical_count": 0,
                "warning_count": 0,
                "state_store_available": True,
            },
            "timestamp": "2026-09-29T10:00:00+00:00",
        },
    )

    response = client.get(
        "/api/v1/operations",
        headers=make_auth_headers(user),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["scope"] == "platform"
    assert body["data"]["schema_version"] == "v1"


def test_operations_route_returns_domain_errors(
    client,
    user,
    make_auth_headers,
    monkeypatch,
):
    import app.core.observability.operations_routes as routes
    from app.core.exceptions import ValidationError

    monkeypatch.setattr(
        routes,
        "get_operational_dashboard",
        lambda actor_id: (_ for _ in ()).throw(
            ValidationError(
                "Operational dashboard is not available"
            )
        ),
    )

    response = client.get(
        "/api/v1/operations",
        headers=make_auth_headers(user),
    )

    assert response.status_code == 422
    assert response.get_json()["success"] is False
    assert response.get_json()["error"] == (
        "Operational dashboard is not available"
    )
