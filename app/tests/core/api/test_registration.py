from __future__ import annotations

import re

from flask import Flask

from app import create_app


API_ROUTE_PATTERN = re.compile(
    r"^/api/(?P<version>v\d+)(?:/|$)"
)


def _api_routes(app: Flask) -> list[str]:
    return sorted(
        {
            rule.rule
            for rule in app.url_map.iter_rules()
            if rule.rule.startswith("/api/")
        }
    )


def test_api_routes_exist():
    app = create_app("testing")

    routes = _api_routes(app)

    assert routes


def test_all_api_routes_are_registered_under_v1():
    app = create_app("testing")

    routes = _api_routes(app)

    assert all(
        route == "/api/v1"
        or route.startswith("/api/v1/")
        for route in routes
    )


def test_no_legacy_api_routes_are_registered():
    app = create_app("testing")

    routes = _api_routes(app)

    legacy_routes = [
        route
        for route in routes
        if route != "/api/v1"
        and not route.startswith("/api/v1/")
    ]

    assert legacy_routes == []


def test_api_routes_have_v1_as_the_only_registered_version():
    app = create_app("testing")

    versions = set()

    for route in _api_routes(app):
        match = API_ROUTE_PATTERN.match(route)

        assert match is not None, (
            f"API route does not contain a valid version segment: {route}"
        )

        versions.add(match.group("version"))

    assert versions == {"v1"}


def test_non_api_routes_are_not_treated_as_api_versions():
    app = create_app("testing")

    routes = [
        rule.rule
        for rule in app.url_map.iter_rules()
    ]

    non_api_routes = [
        route
        for route in routes
        if route.startswith("/")
        and not route.startswith("/api/")
    ]

    assert non_api_routes


def test_v1_api_request_passes_version_boundary():
    app = create_app("testing")

    client = app.test_client()

    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404

    payload = response.get_json()

    assert payload is not None
    assert payload.get("code") != "api_version_not_supported"


def test_v2_api_request_is_rejected_by_version_boundary():
    app = create_app("testing")

    client = app.test_client()

    response = client.get("/api/v2/does-not-exist")

    assert response.status_code == 404

    payload = response.get_json()

    assert payload is not None
    assert payload["success"] is False
    assert payload["error"] == "API version 'v2' is not supported."
    assert payload["code"] == "api_version_not_supported"


def test_v99_api_request_is_rejected_by_version_boundary():
    app = create_app("testing")

    client = app.test_client()

    response = client.get("/api/v99/anything")

    assert response.status_code == 404

    payload = response.get_json()

    assert payload is not None
    assert payload["success"] is False
    assert payload["code"] == "api_version_not_supported"


def test_api_patients_path_is_not_misinterpreted_as_version():
    app = create_app("testing")

    client = app.test_client()

    response = client.get("/api/patients")

    payload = response.get_json() or {}

    assert payload.get("code") != "api_version_not_supported"


def test_non_versioned_path_is_not_checked_by_api_version_boundary():
    app = create_app("testing")

    client = app.test_client()

    response = client.get("/patients")

    payload = response.get_json() or {}

    assert payload.get("code") != "api_version_not_supported"