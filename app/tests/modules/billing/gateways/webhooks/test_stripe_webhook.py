from decimal import Decimal
from unittest.mock import Mock

import pytest
import stripe

from app.modules.billing.services.gateways.stripe_gateway import (
    StripeGateway,
)


@pytest.fixture
def stripe_app(app):
    app.config["STRIPE_SECRET_KEY"] = "sk_test_secret"
    app.config["STRIPE_WEBHOOK_SECRET"] = (
        "whsec_test_secret"
    )
    return app


@pytest.fixture
def gateway(stripe_app):
    with stripe_app.app_context():
        return StripeGateway()


def _event_payload(
    *,
    event_id="evt_123",
    event_type="payment_intent.succeeded",
    livemode=False,
    payment_intent=None,
):
    if payment_intent is None:
        payment_intent = {
            "id": "pi_123",
            "amount": 12550,
            "currency": "ngn",
            "status": "succeeded",
            "metadata": {
                "reference": "INV-001",
            },
        }

    return {
        "id": event_id,
        "type": event_type,
        "livemode": livemode,
        "data": {
            "object": payment_intent,
        },
    }


# ---------------------------------------------------------------------------
# Signature / configuration
# ---------------------------------------------------------------------------


def test_handle_webhook_success(
    stripe_app,
    monkeypatch,
):
    with stripe_app.app_context():
        gateway = StripeGateway()

        expected_event = _event_payload()

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.stripe_gateway.stripe.Webhook.construct_event",
            Mock(return_value=expected_event),
        )

        result = gateway.handle_webhook(
            payload=b'{"stripe":"payload"}',
            signature="t=123,v1=valid",
        )

    assert result == {
        "provider": "stripe",
        "event_id": "evt_123",
        "event_type": (
            "payment_intent.succeeded"
        ),
        "livemode": False,
        "transaction_id": "pi_123",
        "reference": "INV-001",
        "amount": Decimal("125.5"),
        "currency": "NGN",
        "status": "successful",
    }


def test_handle_webhook_reads_signature_from_header(
    stripe_app,
    monkeypatch,
):
    with stripe_app.app_context():
        gateway = StripeGateway()

        expected_event = _event_payload()

        mock_construct = Mock(
            return_value=expected_event
        )

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.stripe_gateway.stripe.Webhook.construct_event",
            mock_construct,
        )

        payload = b'{"stripe":"payload"}'

        result = gateway.handle_webhook(
            payload=payload,
            headers={
                "Stripe-Signature": "t=123,v1=valid",
            },
        )

    assert result["status"] == "successful"

    mock_construct.assert_called_once_with(
        payload,
        "t=123,v1=valid",
        "whsec_test_secret",
    )


def test_handle_webhook_explicit_signature_takes_precedence(
    stripe_app,
    monkeypatch,
):
    with stripe_app.app_context():
        gateway = StripeGateway()

        expected_event = _event_payload()

        mock_construct = Mock(
            return_value=expected_event
        )

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.stripe_gateway.stripe.Webhook.construct_event",
            mock_construct,
        )

        gateway.handle_webhook(
            payload=b'{"stripe":"payload"}',
            signature="explicit-signature",
            headers={
                "Stripe-Signature": "header-signature",
            },
        )

    mock_construct.assert_called_once_with(
        b'{"stripe":"payload"}',
        "explicit-signature",
        "whsec_test_secret",
    )


@pytest.mark.parametrize(
    "signature,expected_message",
    [
        (
            None,
            "Stripe webhook signature is required",
        ),
        (
            "",
            "Stripe webhook signature is required",
        ),
        (
            "   ",
            "Invalid Stripe webhook signature",
        ),
        (
            "invalid-signature",
            "Invalid Stripe webhook signature",
        ),
    ],
)
def test_handle_webhook_rejects_missing_or_invalid_signature(
    stripe_app,
    monkeypatch,
    signature,
    expected_message,
):
    with stripe_app.app_context():
        gateway = StripeGateway()

        if signature not in (None, "", "   "):
            monkeypatch.setattr(
                "app.modules.billing.services.gateways.stripe_gateway.stripe.Webhook.construct_event",
                Mock(
                    side_effect=stripe.SignatureVerificationError(
                        "invalid signature",
                        "sig_header",
                    )
                ),
            )

        elif signature == "   ":
            monkeypatch.setattr(
                "app.modules.billing.services.gateways.stripe_gateway.stripe.Webhook.construct_event",
                Mock(
                    side_effect=stripe.SignatureVerificationError(
                        "invalid signature",
                        "sig_header",
                    )
                ),
            )

        with pytest.raises(
            ValueError,
            match=expected_message,
        ):
            gateway.handle_webhook(
                payload=b"{}",
                signature=signature,
            )


def test_handle_webhook_rejects_tampered_signature(
    stripe_app,
    monkeypatch,
):
    with stripe_app.app_context():
        gateway = StripeGateway()

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.stripe_gateway.stripe.Webhook.construct_event",
            Mock(
                side_effect=stripe.SignatureVerificationError(
                    "signature mismatch",
                    "sig_header",
                )
            ),
        )

        with pytest.raises(
            ValueError,
            match="Invalid Stripe webhook signature",
        ):
            gateway.handle_webhook(
                payload=b'{"amount":999999}',
                signature="tampered-signature",
            )


def test_handle_webhook_requires_payload(
    stripe_app,
):
    with stripe_app.app_context():
        gateway = StripeGateway()

        with pytest.raises(
            ValueError,
            match="Webhook payload is required",
        ):
            gateway.handle_webhook(
                payload=b"",
                signature="anything",
            )


def test_handle_webhook_requires_webhook_secret(
    app,
):
    app.config["STRIPE_SECRET_KEY"] = (
        "sk_test_secret"
    )
    app.config.pop(
        "STRIPE_WEBHOOK_SECRET",
        None,
    )

    with app.app_context():
        gateway = StripeGateway()

        with pytest.raises(
            ValueError,
            match=(
                "Stripe webhook secret is not configured"
            ),
        ):
            gateway.handle_webhook(
                payload=b"{}",
                signature="anything",
            )


# ---------------------------------------------------------------------------
# Stripe event construction / payload validation
# ---------------------------------------------------------------------------


def test_handle_webhook_rejects_invalid_payload(
    stripe_app,
    monkeypatch,
):
    with stripe_app.app_context():
        gateway = StripeGateway()

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.stripe_gateway.stripe.Webhook.construct_event",
            Mock(
                side_effect=ValueError(
                    "invalid payload"
                )
            ),
        )

        with pytest.raises(
            ValueError,
            match="Invalid Stripe webhook payload",
        ):
            gateway.handle_webhook(
                payload=b"invalid",
                signature="signature",
            )


def test_handle_webhook_rejects_non_dict_event(
    stripe_app,
    monkeypatch,
):
    with stripe_app.app_context():
        gateway = StripeGateway()

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.stripe_gateway.stripe.Webhook.construct_event",
            Mock(return_value=[]),
        )

        with pytest.raises(
            ValueError,
            match="Invalid Stripe webhook event",
        ):
            gateway.handle_webhook(
                payload=b"[]",
                signature="signature",
            )


def test_handle_webhook_requires_event_type(
    stripe_app,
    monkeypatch,
):
    with stripe_app.app_context():
        gateway = StripeGateway()

        event = _event_payload()
        event.pop("type")

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.stripe_gateway.stripe.Webhook.construct_event",
            Mock(return_value=event),
        )

        with pytest.raises(
            ValueError,
            match=(
                "Stripe webhook event type is missing"
            ),
        ):
            gateway.handle_webhook(
                payload=b"{}",
                signature="signature",
            )


@pytest.mark.parametrize(
    "event_data",
    [
        None,
        [],
        "invalid",
        123,
    ],
)
def test_handle_webhook_rejects_invalid_event_data(
    stripe_app,
    monkeypatch,
    event_data,
):
    with stripe_app.app_context():
        gateway = StripeGateway()

        event = {
            "id": "evt_123",
            "type": "payment_intent.succeeded",
            "livemode": False,
            "data": event_data,
        }

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.stripe_gateway.stripe.Webhook.construct_event",
            Mock(return_value=event),
        )

        if event_data is None:
            # The gateway normalizes falsey data to {}.
            expected_message = (
                "Invalid Stripe webhook event data"
            )
        else:
            expected_message = (
                "Invalid Stripe webhook event data"
            )

        with pytest.raises(
            ValueError,
            match=expected_message,
        ):
            gateway.handle_webhook(
                payload=b"{}",
                signature="signature",
            )


def test_handle_webhook_rejects_missing_event_object(
    stripe_app,
    monkeypatch,
):
    with stripe_app.app_context():
        gateway = StripeGateway()

        event = {
            "id": "evt_123",
            "type": "payment_intent.succeeded",
            "livemode": False,
            "data": {},
        }

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.stripe_gateway.stripe.Webhook.construct_event",
            Mock(return_value=event),
        )

        with pytest.raises(
            ValueError,
            match=(
                "Invalid Stripe webhook event data"
            ),
        ):
            gateway.handle_webhook(
                payload=b"{}",
                signature="signature",
            )


# ---------------------------------------------------------------------------
# Successful payment events
# ---------------------------------------------------------------------------


def test_handle_webhook_normalizes_successful_payment(
    gateway,
    monkeypatch,
):
    event = _event_payload(
        event_id="evt_success",
        event_type="payment_intent.succeeded",
        livemode=True,
    )

    mock_construct = Mock(
        return_value=event
    )

    monkeypatch.setattr(
        "app.modules.billing.services.gateways.stripe_gateway.stripe.Webhook.construct_event",
        mock_construct,
    )

    result = gateway.handle_webhook(
        payload=b"raw-payload",
        signature="valid-signature",
    )

    assert result["provider"] == "stripe"
    assert result["event_id"] == "evt_success"
    assert result["event_type"] == (
        "payment_intent.succeeded"
    )
    assert result["livemode"] is True
    assert result["transaction_id"] == "pi_123"
    assert result["reference"] == "INV-001"
    assert result["amount"] == Decimal("125.5")
    assert result["currency"] == "NGN"
    assert result["status"] == "successful"


# ---------------------------------------------------------------------------
# Failed payment events
# ---------------------------------------------------------------------------


def test_handle_webhook_normalizes_failed_payment(
    gateway,
    monkeypatch,
):
    event = _event_payload(
        event_id="evt_failed",
        event_type="payment_intent.payment_failed",
        payment_intent={
            "id": "pi_failed",
            "amount": 5000,
            "currency": "usd",
            "status": "requires_payment_method",
            "metadata": {
                "reference": "INV-FAILED",
            },
            "last_payment_error": {
                "message": "Card declined",
            },
        },
    )

    monkeypatch.setattr(
        "app.modules.billing.services.gateways.stripe_gateway.stripe.Webhook.construct_event",
        Mock(return_value=event),
    )

    result = gateway.handle_webhook(
        payload=b"raw-payload",
        signature="valid-signature",
    )

    assert result["provider"] == "stripe"
    assert result["event_id"] == "evt_failed"
    assert result["event_type"] == (
        "payment_intent.payment_failed"
    )
    assert result["transaction_id"] == "pi_failed"
    assert result["reference"] == "INV-FAILED"
    assert result["amount"] == Decimal("50")
    assert result["currency"] == "USD"
    assert result["status"] == "failed"
    assert result["failure_reason"] == (
        "Card declined"
    )


def test_handle_webhook_uses_default_failure_reason(
    gateway,
    monkeypatch,
):
    event = _event_payload(
        event_type="payment_intent.payment_failed",
        payment_intent={
            "id": "pi_failed",
            "amount": 5000,
            "currency": "usd",
            "status": "requires_payment_method",
            "metadata": {
                "reference": "INV-FAILED",
            },
            "last_payment_error": {},
        },
    )

    monkeypatch.setattr(
        "app.modules.billing.services.gateways.stripe_gateway.stripe.Webhook.construct_event",
        Mock(return_value=event),
    )

    result = gateway.handle_webhook(
        payload=b"raw-payload",
        signature="valid-signature",
    )

    assert result["status"] == "failed"
    assert result["failure_reason"] == (
        "Stripe payment failed"
    )


# ---------------------------------------------------------------------------
# Other event statuses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "event_type,payment_status,expected_status",
    [
        (
            "payment_intent.processing",
            "processing",
            "processing",
        ),
        (
            "payment_intent.requires_action",
            "requires_action",
            "requires_action",
        ),
        (
            "payment_intent.canceled",
            "canceled",
            "canceled",
        ),
    ],
)
def test_handle_webhook_normalizes_other_statuses(
    gateway,
    monkeypatch,
    event_type,
    payment_status,
    expected_status,
):
    event = _event_payload(
        event_type=event_type,
        payment_intent={
            "id": "pi_other",
            "amount": 10000,
            "currency": "usd",
            "status": payment_status,
            "metadata": {},
        },
    )

    monkeypatch.setattr(
        "app.modules.billing.services.gateways.stripe_gateway.stripe.Webhook.construct_event",
        Mock(return_value=event),
    )

    result = gateway.handle_webhook(
        payload=b"raw-payload",
        signature="valid-signature",
    )

    assert result["status"] == expected_status


# ---------------------------------------------------------------------------
# Metadata / amount / currency normalization
# ---------------------------------------------------------------------------


def test_handle_webhook_uses_missing_reference_as_none(
    gateway,
    monkeypatch,
):
    event = _event_payload(
        payment_intent={
            "id": "pi_no_ref",
            "amount": 10000,
            "currency": "usd",
            "status": "succeeded",
            "metadata": {},
        },
    )

    monkeypatch.setattr(
        "app.modules.billing.services.gateways.stripe_gateway.stripe.Webhook.construct_event",
        Mock(return_value=event),
    )

    result = gateway.handle_webhook(
        payload=b"raw-payload",
        signature="valid-signature",
    )

    assert result["reference"] is None


def test_handle_webhook_handles_non_dict_metadata(
    gateway,
    monkeypatch,
):
    event = _event_payload(
        payment_intent={
            "id": "pi_bad_meta",
            "amount": 10000,
            "currency": "usd",
            "status": "succeeded",
            "metadata": "invalid",
        },
    )

    monkeypatch.setattr(
        "app.modules.billing.services.gateways.stripe_gateway.stripe.Webhook.construct_event",
        Mock(return_value=event),
    )

    result = gateway.handle_webhook(
        payload=b"raw-payload",
        signature="valid-signature",
    )

    assert result["reference"] is None


@pytest.mark.parametrize(
    "amount,currency,expected",
    [
        (10000, "usd", Decimal("100")),
        (12550, "ngn", Decimal("125.5")),
        (5000, "jpy", Decimal("5000")),
    ],
)
def test_handle_webhook_normalizes_amount(
    gateway,
    monkeypatch,
    amount,
    currency,
    expected,
):
    event = _event_payload(
        payment_intent={
            "id": "pi_amount",
            "amount": amount,
            "currency": currency,
            "status": "succeeded",
            "metadata": {
                "reference": "REF-1",
            },
        },
    )

    monkeypatch.setattr(
        "app.modules.billing.services.gateways.stripe_gateway.stripe.Webhook.construct_event",
        Mock(return_value=event),
    )

    result = gateway.handle_webhook(
        payload=b"raw-payload",
        signature="valid-signature",
    )

    assert result["amount"] == expected
    assert result["currency"] == currency.upper()


def test_handle_webhook_allows_missing_amount(
    gateway,
    monkeypatch,
):
    event = _event_payload(
        payment_intent={
            "id": "pi_no_amount",
            "currency": "usd",
            "status": "succeeded",
            "metadata": {
                "reference": "REF-1",
            },
        },
    )

    monkeypatch.setattr(
        "app.modules.billing.services.gateways.stripe_gateway.stripe.Webhook.construct_event",
        Mock(return_value=event),
    )

    result = gateway.handle_webhook(
        payload=b"raw-payload",
        signature="valid-signature",
    )

    assert result["amount"] is None
    assert result["currency"] == "USD"