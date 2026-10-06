from app.core.exceptions import (
    ConflictError,
    ValidationError,
)
from app.modules.billing.routes import billing_route


def test_payment_webhook_is_public_and_forwards_provider_context(
    client,
    monkeypatch,
):
    captured = {}

    def fake_process_payment_webhook(
        **kwargs,
    ):
        captured.update(kwargs)

        return {
            "status": "processed_successful",
            "event_id": "evt-route-1",
            "payment_id": 10,
            "payment_status": "successful",
        }

    monkeypatch.setattr(
        billing_route,
        "process_payment_webhook",
        fake_process_payment_webhook,
    )

    payload = b'{"event":"charge.success","data":{"id":"TX-1"}}'

    response = client.post(
        "/api/v1/billing/webhooks/123/paystack",
        data=payload,
        headers={
            "X-Paystack-Signature": "signature-123",
        },
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["status"] == "processed_successful"
    assert body["data"]["event_id"] == "evt-route-1"

    assert captured["clinic_id"] == 123
    assert captured["gateway"] == "paystack"
    assert captured["payload"] == payload
    assert (
        captured["headers"]["X-Paystack-Signature"]
        == "signature-123"
    )


def test_payment_webhook_does_not_require_jwt(
    client,
    monkeypatch,
):
    captured = {}

    def fake_process_payment_webhook(
        **kwargs,
    ):
        captured.update(kwargs)

        return {
            "status": "pending",
            "event_id": "evt-public-1",
            "payment_id": 11,
            "payment_status": "pending",
        }

    monkeypatch.setattr(
        billing_route,
        "process_payment_webhook",
        fake_process_payment_webhook,
    )

    response = client.post(
        "/api/v1/billing/webhooks/456/stripe",
        data=b'{"type":"payment_intent.succeeded"}',
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True

    assert captured["clinic_id"] == 456
    assert captured["gateway"] == "stripe"
    assert captured["payload"] == (
        b'{"type":"payment_intent.succeeded"}'
    )


def test_payment_webhook_returns_domain_error_status(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        billing_route,
        "process_payment_webhook",
        lambda **kwargs: (
            (_ for _ in ()).throw(
                ValidationError(
                    "Invalid webhook signature"
                )
            )
        ),
    )

    response = client.post(
        "/api/v1/billing/webhooks/123/paystack",
        data=b"invalid",
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Invalid webhook signature"


def test_payment_webhook_preserves_conflict_status(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        billing_route,
        "process_payment_webhook",
        lambda **kwargs: (
            (_ for _ in ()).throw(
                ConflictError(
                    "Webhook amount does not match the payment"
                )
            )
        ),
    )

    response = client.post(
        "/api/v1/billing/webhooks/123/paystack",
        data=b'{"event":"charge.success"}',
    )

    assert response.status_code == 409

    body = response.get_json()

    assert body["success"] is False
    assert (
        body["error"]
        == "Webhook amount does not match the payment"
    )
