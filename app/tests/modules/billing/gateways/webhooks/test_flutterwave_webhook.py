import base64
import hashlib
import hmac
import json

import pytest

from app.modules.billing.services.gateways.flutterwave_gateway import (
    FlutterwaveGateway,
)


@pytest.fixture
def flutterwave_app(app):
    app.config["FLUTTERWAVE_SECRET_KEY"] = "flw_test_secret"
    app.config["FLUTTERWAVE_WEBHOOK_SECRET"] = "flw_webhook_secret"
    return app


def _webhook_signature(
    payload: bytes,
    secret: str = "flw_webhook_secret",
) -> str:
    return base64.b64encode(
        hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).digest()
    ).decode("utf-8")


def _webhook_payload(**overrides):
    payload = {
        "id": 987654,
        "event": "charge.completed",
        "data": {
            "id": 123456,
            "tx_ref": "INV-001",
            "amount": 100,
            "currency": "ngn",
            "status": "successful",
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
    flutterwave_app,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        event = _webhook_payload()

        payload = json.dumps(
            event,
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        result = gateway.handle_webhook(
            payload=payload,
            signature=signature,
        )

    assert result == {
        "provider": "flutterwave",
        "event_id": "987654",
        "event_type": "charge.completed",
        "transaction_id": "123456",
        "reference": "INV-001",
        "amount": 100,
        "currency": "NGN",
        "status": "successful",
    }


def test_handle_webhook_reads_signature_from_lowercase_header(
    flutterwave_app,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        payload = json.dumps(
            _webhook_payload(),
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        result = gateway.handle_webhook(
            payload=payload,
            headers={
                "flutterwave-signature": signature,
            },
        )

    assert result["status"] == "successful"
    assert result["transaction_id"] == "123456"


def test_handle_webhook_reads_signature_from_title_case_header(
    flutterwave_app,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        payload = json.dumps(
            _webhook_payload(),
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        result = gateway.handle_webhook(
            payload=payload,
            headers={
                "Flutterwave-Signature": signature,
            },
        )

    assert result["status"] == "successful"


def test_handle_webhook_explicit_signature_takes_precedence(
    flutterwave_app,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        payload = json.dumps(
            _webhook_payload(),
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        result = gateway.handle_webhook(
            payload=payload,
            signature=signature,
            headers={
                "flutterwave-signature": "wrong",
            },
        )

    assert result["status"] == "successful"


@pytest.mark.parametrize(
    "signature,expected_message",
    [
        (
            None,
            "Flutterwave webhook signature is required",
        ),
        (
            "",
            "Flutterwave webhook signature is required",
        ),
        (
            "   ",
            "Invalid Flutterwave webhook signature",
        ),
        (
            "invalid-signature",
            "Invalid Flutterwave webhook signature",
        ),
    ],
)
def test_handle_webhook_rejects_missing_or_invalid_signature(
    flutterwave_app,
    signature,
    expected_message,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

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
    flutterwave_app,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

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
            match="Invalid Flutterwave webhook signature",
        ):
            gateway.handle_webhook(
                payload=tampered_payload,
                signature=signature,
            )


def test_handle_webhook_requires_payload(
    flutterwave_app,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        with pytest.raises(
            ValueError,
            match="Webhook payload is required",
        ):
            gateway.handle_webhook(
                payload=b"",
                signature="anything",
            )


def test_handle_webhook_requires_webhook_secret(
    flutterwave_app,
):
    flutterwave_app.config.pop(
        "FLUTTERWAVE_WEBHOOK_SECRET",
        None,
    )

    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        payload = json.dumps(
            _webhook_payload(),
            separators=(",", ":"),
        ).encode("utf-8")

        with pytest.raises(
            ValueError,
            match=(
                "Flutterwave webhook secret is not configured"
            ),
        ):
            gateway.handle_webhook(
                payload=payload,
                signature="anything",
            )


# ---------------------------------------------------------------------------
# Payload parsing / event validation
# ---------------------------------------------------------------------------


def test_handle_webhook_rejects_invalid_json(
    flutterwave_app,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        payload = b"{not-valid-json}"
        signature = _webhook_signature(payload)

        with pytest.raises(
            ValueError,
            match="Invalid Flutterwave webhook payload",
        ):
            gateway.handle_webhook(
                payload=payload,
                signature=signature,
            )


def test_handle_webhook_rejects_invalid_utf8(
    flutterwave_app,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        payload = b"\xff\xfe\xfd"
        signature = _webhook_signature(payload)

        with pytest.raises(
            ValueError,
            match="Invalid Flutterwave webhook payload",
        ):
            gateway.handle_webhook(
                payload=payload,
                signature=signature,
            )


def test_handle_webhook_rejects_non_object_json(
    flutterwave_app,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        payload = b"[]"
        signature = _webhook_signature(payload)

        with pytest.raises(
            ValueError,
            match="Invalid Flutterwave webhook payload",
        ):
            gateway.handle_webhook(
                payload=payload,
                signature=signature,
            )


def test_handle_webhook_requires_event_type(
    flutterwave_app,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        event = _webhook_payload()
        event.pop("event")

        payload = json.dumps(
            event,
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        with pytest.raises(
            ValueError,
            match="Flutterwave webhook event type is missing",
        ):
            gateway.handle_webhook(
                payload=payload,
                signature=signature,
            )


def test_handle_webhook_accepts_type_alias(
    flutterwave_app,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        event = _webhook_payload()
        event.pop("event")
        event["type"] = "charge.completed"

        payload = json.dumps(
            event,
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        result = gateway.handle_webhook(
            payload=payload,
            signature=signature,
        )

    assert result["event_type"] == "charge.completed"


@pytest.mark.parametrize(
    "event_data",
    [
        "invalid",
        123,
        True,
    ],
)
def test_handle_webhook_rejects_invalid_event_data(
    flutterwave_app,
    event_data,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        event = _webhook_payload()
        event["data"] = event_data

        payload = json.dumps(
            event,
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        with pytest.raises(
            ValueError,
            match="Invalid Flutterwave webhook data",
        ):
            gateway.handle_webhook(
                payload=payload,
                signature=signature,
            )


# ---------------------------------------------------------------------------
# Event normalization
# ---------------------------------------------------------------------------


def test_handle_webhook_uses_event_id(
    flutterwave_app,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        payload = json.dumps(
            _webhook_payload(id="event-123"),
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        result = gateway.handle_webhook(
            payload=payload,
            signature=signature,
        )

    assert result["event_id"] == "event-123"


def test_handle_webhook_falls_back_to_transaction_id(
    flutterwave_app,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        event = _webhook_payload()
        event.pop("id")

        payload = json.dumps(
            event,
            separators=(",", ":"),
        ).encode("utf-8")

        signature = _webhook_signature(payload)

        result = gateway.handle_webhook(
            payload=payload,
            signature=signature,
        )

    assert result["event_id"] == "123456"


def test_handle_webhook_falls_back_to_payload_hash(
    flutterwave_app,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        event = _webhook_payload()
        event.pop("id")
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

    expected_event_id = hashlib.sha256(
        payload
    ).hexdigest()

    assert result["event_id"] == expected_event_id


@pytest.mark.parametrize(
    "status",
    [
        "failed",
        "cancelled",
        "canceled",
    ],
)
def test_handle_webhook_normalizes_failed_transactions(
    flutterwave_app,
    status,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        event = _webhook_payload(
            data={
                "status": status,
                "processor_response": (
                    "Insufficient funds"
                ),
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

    assert result["status"] == "failed"
    assert result["failure_reason"] == (
        "Insufficient funds"
    )


def test_handle_webhook_uses_message_as_failure_reason(
    flutterwave_app,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        event = _webhook_payload(
            data={
                "status": "failed",
                "processor_response": None,
                "message": "Card declined",
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

    assert result["status"] == "failed"
    assert result["failure_reason"] == "Card declined"


def test_handle_webhook_uses_default_failure_reason(
    flutterwave_app,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        event = _webhook_payload(
            data={
                "status": "failed",
                "processor_response": None,
                "message": None,
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

    assert result["status"] == "failed"
    assert result["failure_reason"] == (
        "Flutterwave payment failed"
    )


@pytest.mark.parametrize(
    "event_type,status,expected_status",
    [
        ("charge.completed", "successful", "successful"),
        ("charge.completed", "pending", "pending"),
        ("charge.updated", "pending", "pending"),
        ("payment.pending", "pending", "pending"),
    ],
)
def test_handle_webhook_normalizes_other_statuses(
    flutterwave_app,
    event_type,
    status,
    expected_status,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

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
    flutterwave_app,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

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
    flutterwave_app,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        event = {
            "event": "payment.pending",
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

    assert result["provider"] == "flutterwave"
    assert result["event_type"] == "payment.pending"
    assert result["transaction_id"] is None
    assert result["reference"] is None
    assert result["amount"] is None
    assert result["currency"] == ""
    assert result["status"] == "pending"