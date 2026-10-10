from __future__ import annotations

import base64
import json
import time

import pytest


def _base64url_json(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        separators=(",", ":"),
    ).encode("utf-8")

    return (
        base64.urlsafe_b64encode(encoded)
        .rstrip(b"=")
        .decode("ascii")
    )


def _forged_access_token() -> str:
    now = int(time.time())

    header = _base64url_json({
        "alg": "HS256",
        "typ": "JWT",
    })
    payload = _base64url_json({
        "sub": "42",
        "type": "access",
        "iat": now - 60,
        "exp": now + 3600,
        "jti": "forged-token-security-test",
        "token_version": 0,
    })

    # This is deliberately not a signature generated with the application's
    # signing key. The token is structurally JWT-shaped but must not authenticate.
    invalid_signature = "bm90LWEtdmFsaWQtc2lnbmF0dXJl"

    return f"{header}.{payload}.{invalid_signature}"


@pytest.mark.parametrize(
    ("case_name", "token"),
    [
        ("malformed", "not-a-jwt"),
        ("forged-signature", _forged_access_token()),
    ],
)
def test_protected_clinic_context_rejects_invalid_bearer_tokens(
    client,
    case_name: str,
    token: str,
):
    response = client.get(
        "/api/v1/auth/clinic-context",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code in {401, 422}, (
        f"The protected route did not reject the {case_name} token; "
        f"received HTTP {response.status_code}."
    )

    body = response.get_json(silent=True)
    assert not (isinstance(body, dict) and body.get("success") is True), (
        f"The protected route reported success for a {case_name} token."
    )