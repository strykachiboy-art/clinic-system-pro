from app.core.audit.services.audit_redaction import (
    REDACTED_VALUE,
    redact_audit_payload,
)


def test_redacts_top_level_sensitive_keys():
    payload = {
        "password": "secret",
        "password_hash": "hash",
        "access_token": "token",
        "refresh_token": "refresh",
        "api_key": "key",
        "client_secret": "secret",
        "authorization": "Bearer token",
        "status": "active",
    }

    result = redact_audit_payload(payload)

    assert result["password"] == REDACTED_VALUE
    assert result["password_hash"] == REDACTED_VALUE
    assert result["access_token"] == REDACTED_VALUE
    assert result["refresh_token"] == REDACTED_VALUE
    assert result["api_key"] == REDACTED_VALUE
    assert result["client_secret"] == REDACTED_VALUE
    assert result["authorization"] == REDACTED_VALUE
    assert result["status"] == "active"


def test_redacts_nested_sensitive_keys():
    payload = {
        "profile": {
            "email": "user@test.com",
            "credentials": {
                "password": "secret",
                "api_key": "key",
            },
        },
    }

    result = redact_audit_payload(payload)

    assert result["profile"]["email"] == "user@test.com"
    assert (
        result["profile"]["credentials"]["password"]
        == REDACTED_VALUE
    )
    assert (
        result["profile"]["credentials"]["api_key"]
        == REDACTED_VALUE
    )


def test_redacts_sensitive_keys_inside_lists():
    payload = [
        {
            "name": "one",
            "token": "secret",
        },
        {
            "name": "two",
            "password": "secret",
        },
    ]

    result = redact_audit_payload(payload)

    assert result[0]["name"] == "one"
    assert result[0]["token"] == REDACTED_VALUE
    assert result[1]["name"] == "two"
    assert result[1]["password"] == REDACTED_VALUE


def test_redacts_suffix_sensitive_keys():
    payload = {
        "session_token": "secret",
        "oauth_secret": "secret",
        "service_api_key": "secret",
        "status": "active",
    }

    result = redact_audit_payload(payload)

    assert result["session_token"] == REDACTED_VALUE
    assert result["oauth_secret"] == REDACTED_VALUE
    assert result["service_api_key"] == REDACTED_VALUE
    assert result["status"] == "active"


def test_normalizes_sensitive_key_formatting():
    payload = {
        "access-token": "secret",
        "client secret": "secret",
        "API_KEY": "secret",
    }

    result = redact_audit_payload(payload)

    assert result["access-token"] == REDACTED_VALUE
    assert result["client secret"] == REDACTED_VALUE
    assert result["API_KEY"] == REDACTED_VALUE


def test_preserves_non_mapping_values():
    assert redact_audit_payload(None) is None
    assert redact_audit_payload("hello") == "hello"
    assert redact_audit_payload(123) == 123
    assert redact_audit_payload(True) is True


def test_preserves_tuples():
    payload = (
        {"status": "active"},
        {"token": "secret"},
    )

    result = redact_audit_payload(payload)

    assert result[0]["status"] == "active"
    assert result[1]["token"] == REDACTED_VALUE


def test_does_not_mutate_original_payload():
    payload = {
        "password": "secret",
        "status": "active",
    }

    result = redact_audit_payload(payload)

    assert payload["password"] == "secret"
    assert result["password"] == REDACTED_VALUE