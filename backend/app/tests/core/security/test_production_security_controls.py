def test_security_headers_present(
    client,
):
    response = client.get(
        "/api/v1/nonexistent-security-test-route"
    )

    assert response.headers[
        "X-Content-Type-Options"
    ] == "nosniff"

    assert response.headers[
        "X-Frame-Options"
    ] == "DENY"

    assert response.headers[
        "Referrer-Policy"
    ] == "no-referrer"

    assert response.headers[
        "Permissions-Policy"
    ] == (
        "camera=(), "
        "microphone=(), "
        "geolocation=(), "
        "payment=()"
    )


def test_hsts_is_not_sent_over_plain_http(
    client,
):
    response = client.get("/")

    assert "Strict-Transport-Security" not in (
        response.headers
    )


def test_production_security_limits_are_configured(
    app,
):
    assert (
        app.config[
            "AUTH_LOGIN_RATE_LIMIT"
        ]
        == "5 per minute"
    )

    assert (
        app.config[
            "AUTH_REGISTER_RATE_LIMIT"
        ]
        == "10 per minute"
    )

    assert (
        app.config[
            "AUTH_GOOGLE_RATE_LIMIT"
        ]
        == "10 per minute"
    )

    assert (
        app.config[
            "AUTH_REFRESH_RATE_LIMIT"
        ]
        == "20 per minute"
    )

    assert (
        app.config[
            "AUTH_LOGOUT_RATE_LIMIT"
        ]
        == "20 per minute"
    )


def test_testing_environment_disables_timing_sensitive_rate_limits(
    app,
):
    assert (
        app.config["RATELIMIT_ENABLED"]
        is False
    )
