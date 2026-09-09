import hashlib
import hmac
import json

import pytest

from app.modules.billing.services.gateways.paystack_gateway import (
    PaystackGateway,
)


@pytest.fixture
def paystack_app(app):
    app.config["PAYSTACK_SECRET_KEY"] = "sk_test_secret"
    return app


def _webhook_signature(
    payload: bytes,
    secret: str = "sk_test_secret",
) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha512,
    ).hexdigest()


def _webhook_payload(**overrides):
    payload = {
        "event": "charge.success",
        "data": {
            "id": 123456,
            "reference": "INV-001",
            "amount": 12550,
            "currency": "ngn",
            "status": "success",
            "domain": "test",
        },
    }

    for key, value in overrides.items():
        if key == "data":
            payload["data"].update(value)
        else:
            payload[key] = value

    return payload


# ---------------------------------------------------------------------------
# Webhook signature / configuration
# ---------------------------------------------------------------------------


def test_handle_webhook_success(
    paystack_app,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        payload = json.dumps(
            _webhook_payload(),
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        result = gateway.handle_webhook(
            payload=payload,
            signature=signature,
        )

    assert result == {
        "provider": "paystack",
        "event_id": "123456",
        "event_type": "charge.success",
        "livemode": False,
        "transaction_id": "123456",
        "reference": "INV-001",
        "amount": 12550,
        "currency": "NGN",
        "status": "successful",
    }


def test_handle_webhook_reads_signature_from_lowercase_header(
    paystack_app,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        payload = json.dumps(
            _webhook_payload(),
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        result = gateway.handle_webhook(
            payload=payload,
            headers={
                "x-paystack-signature": signature,
            },
        )

    assert result["status"] == "successful"
    assert result["transaction_id"] == "123456"


def test_handle_webhook_reads_signature_from_title_case_header(
    paystack_app,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        payload = json.dumps(
            _webhook_payload(),
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        result = gateway.handle_webhook(
            payload=payload,
            headers={
                "X-Paystack-Signature": signature,
            },
        )

    assert result["status"] == "successful"


def test_handle_webhook_explicit_signature_takes_precedence(
    paystack_app,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        payload = json.dumps(
            _webhook_payload(),
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        result = gateway.handle_webhook(
            payload=payload,
            signature=signature,
            headers={
                "x-paystack-signature": "wrong",
            },
        )

    assert result["status"] == "successful"


@pytest.mark.parametrize(
    "signature,expected_message",
    [
        (
            None,
            "Paystack webhook signature is required",
        ),
        (
            "",
            "Paystack webhook signature is required",
        ),
        (
            "   ",
            "Invalid Paystack webhook signature",
        ),
        (
            "invalid-signature",
            "Invalid Paystack webhook signature",
        ),
    ],
)
def test_handle_webhook_rejects_missing_or_invalid_signature(
    paystack_app,
    signature,
    expected_message,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        payload = json.dumps(
            _webhook_payload(),
            separators=(",", ":"),
        ).encode("utf-8")

        with pytest.raises(
            ValueError,
            match=expected_message,
        ):
            gateway.handle_webhook(
                payload=payload,
                signature=signature,
            )


def test_handle_webhook_rejects_tampered_payload(
    paystack_app,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        original_payload = json.dumps(
            _webhook_payload(),
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(
            original_payload
        )

        tampered_payload = json.dumps(
            _webhook_payload(
                data={
                    "amount": 999999,
                }
            ),
            separators=(",", ":"),
        ).encode("utf-8")

        with pytest.raises(
            ValueError,
            match="Invalid Paystack webhook signature",
        ):
            gateway.handle_webhook(
                payload=tampered_payload,
                signature=signature,
            )


def test_handle_webhook_requires_payload(
    paystack_app,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        with pytest.raises(
            ValueError,
            match="Webhook payload is required",
        ):
            gateway.handle_webhook(
                payload=b"",
                signature="anything",
            )


def test_handle_webhook_requires_secret_key(
    app,
):
    app.config.pop(
        "PAYSTACK_SECRET_KEY",
        None,
    )

    with app.app_context():
        with pytest.raises(
            ValueError,
            match="Paystack secret key is not configured",
        ):
            PaystackGateway()


# ---------------------------------------------------------------------------
# Payload parsing / event validation
# ---------------------------------------------------------------------------


def test_handle_webhook_rejects_invalid_json(
    paystack_app,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        payload = b"{not-valid-json}"
        signature = _webhook_signature(payload)

        with pytest.raises(
            ValueError,
            match="Invalid Paystack webhook payload",
        ):
            gateway.handle_webhook(
                payload=payload,
                signature=signature,
            )


def test_handle_webhook_rejects_invalid_utf8(
    paystack_app,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        payload = b"\xff\xfe\xfd"
        signature = _webhook_signature(payload)

        with pytest.raises(
            ValueError,
            match="Invalid Paystack webhook payload",
        ):
            gateway.handle_webhook(
                payload=payload,
                signature=signature,
            )


def test_handle_webhook_rejects_non_object_json(
    paystack_app,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        payload = b"[]"
        signature = _webhook_signature(payload)

        with pytest.raises(
            ValueError,
            match="Invalid Paystack webhook payload",
        ):
            gateway.handle_webhook(
                payload=payload,
                signature=signature,
            )


def test_handle_webhook_requires_event_type(
    paystack_app,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        event = _webhook_payload()
        event.pop("event")

        payload = json.dumps(
            event,
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        with pytest.raises(
            ValueError,
            match="Paystack webhook event type is missing",
        ):
            gateway.handle_webhook(
                payload=payload,
                signature=signature,
            )


@pytest.mark.parametrize(
    "event_data",
    [
        "invalid",
        123,
        True,
    ],
)
def test_handle_webhook_rejects_invalid_event_data(
    paystack_app,
    event_data,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        event = _webhook_payload()
        event["data"] = event_data

        payload = json.dumps(
            event,
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        with pytest.raises(
            ValueError,
            match="Invalid Paystack webhook data",
        ):
            gateway.handle_webhook(
                payload=payload,
                signature=signature,
            )


# ---------------------------------------------------------------------------
# Event normalization
# ---------------------------------------------------------------------------


def test_handle_webhook_uses_transaction_id_as_event_id(
    paystack_app,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        payload = json.dumps(
            _webhook_payload(
                data={
                    "id": 555555,
                }
            ),
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        result = gateway.handle_webhook(
            payload=payload,
            signature=signature,
        )

    assert result["event_id"] == "555555"


def test_handle_webhook_falls_back_to_payload_hash(
    paystack_app,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        event = _webhook_payload()
        event["data"].pop("id")

        payload = json.dumps(
            event,
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        result = gateway.handle_webhook(
            payload=payload,
            signature=signature,
        )

    assert result["event_id"] == hashlib.sha256(
        payload
    ).hexdigest()


def test_handle_webhook_sets_live_mode(
    paystack_app,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        event = _webhook_payload(
            data={
                "domain": "live",
            }
        )

        payload = json.dumps(
            event,
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        result = gateway.handle_webhook(
            payload=payload,
            signature=signature,
        )

    assert result["livemode"] is True


def test_handle_webhook_sets_test_mode(
    paystack_app,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        event = _webhook_payload(
            data={
                "domain": "test",
            }
        )

        payload = json.dumps(
            event,
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        result = gateway.handle_webhook(
            payload=payload,
            signature=signature,
        )

    assert result["livemode"] is False


@pytest.mark.parametrize(
    "status",
    [
        "failed",
        "abandoned",
        "reversed",
    ],
)
def test_handle_webhook_normalizes_failed_transactions(
    paystack_app,
    status,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        event = _webhook_payload(
            event="charge.failed",
            data={
                "status": status,
                "gateway_response": "Declined",
            },
        )

        payload = json.dumps(
            event,
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        result = gateway.handle_webhook(
            payload=payload,
            signature=signature,
        )

    assert result["status"] == "failed"
    assert result["failure_reason"] == "Declined"


def test_handle_webhook_uses_message_as_failure_reason(
    paystack_app,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        event = _webhook_payload(
            event="charge.failed",
            data={
                "status": "failed",
                "gateway_response": None,
                "message": "Card declined",
            },
        )

        payload = json.dumps(
            event,
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        result = gateway.handle_webhook(
            payload=payload,
            signature=signature,
        )

    assert result["status"] == "failed"
    assert result["failure_reason"] == "Card declined"


def test_handle_webhook_uses_default_failure_reason(
    paystack_app,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        event = _webhook_payload(
            event="charge.failed",
            data={
                "status": "failed",
                "gateway_response": None,
                "message": None,
            },
        )

        payload = json.dumps(
            event,
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        result = gateway.handle_webhook(
            payload=payload,
            signature=signature,
        )

    assert result["status"] == "failed"
    assert result["failure_reason"] == (
        "Paystack payment failed"
    )


@pytest.mark.parametrize(
    "event_type,status,expected_status",
    [
        (
            "charge.success",
            "success",
            "successful",
        ),
        (
            "charge.updated",
            "pending",
            "pending",
        ),
        (
            "charge.failed",
            "pending",
            "pending",
        ),
        (
            "transfer.pending",
            "pending",
            "pending",
        ),
    ],
)
def test_handle_webhook_normalizes_other_statuses(
    paystack_app,
    event_type,
    status,
    expected_status,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        event = _webhook_payload(
            event=event_type,
            data={
                "status": status,
            },
        )

        payload = json.dumps(
            event,
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        result = gateway.handle_webhook(
            payload=payload,
            signature=signature,
        )

    assert result["status"] == expected_status


def test_handle_webhook_normalizes_currency(
    paystack_app,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        event = _webhook_payload(
            data={
                "currency": "usd",
            }
        )

        payload = json.dumps(
            event,
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        result = gateway.handle_webhook(
            payload=payload,
            signature=signature,
        )

    assert result["currency"] == "USD"


def test_handle_webhook_allows_missing_optional_transaction_fields(
    paystack_app,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        event = {
            "event": "charge.updated",
            "data": {
                "status": "pending",
            },
        }

        payload = json.dumps(
            event,
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        result = gateway.handle_webhook(
            payload=payload,
            signature=signature,
        )

    assert result["provider"] == "paystack"
    assert result["event_type"] == "charge.updated"
    assert result["livemode"] is False
    assert result["transaction_id"] is None
    assert result["reference"] is None
    assert result["amount"] is None
    assert result["currency"] == ""
    assert result["status"] == "pending"