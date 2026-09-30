from __future__ import annotations

from unittest.mock import Mock, call

import pytest

import app.modules.billing.services.gateways.factory as factory
from app.core.enums.billing_enums import PaymentGateway
from app.modules.billing.services.gateways.factory import (
    get_payment_gateway,
)
from app.modules.billing.services.gateways.flutterwave_gateway import (
    FlutterwaveGateway,
)
from app.modules.billing.services.gateways.paystack_gateway import (
    PaystackGateway,
)
from app.modules.billing.services.gateways.stripe_gateway import (
    StripeGateway,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def clinic_id():
    return 42


@pytest.fixture
def credentials():
    return {
        "secret_key": "test-secret-key",
        "webhook_secret": "test-webhook-secret",
        "public_key": "test-public-key",
    }


# ---------------------------------------------------------------------------
# Gateway selection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "gateway_enum,gateway_class",
    [
        (
            PaymentGateway.PAYSTACK,
            PaystackGateway,
        ),
        (
            PaymentGateway.FLUTTERWAVE,
            FlutterwaveGateway,
        ),
        (
            PaymentGateway.STRIPE,
            StripeGateway,
        ),
    ],
)
def test_get_payment_gateway_returns_correct_gateway(
    monkeypatch,
    clinic_id,
    credentials,
    gateway_enum,
    gateway_class,
):
    mock_get_credentials = Mock(
        return_value=credentials
    )

    monkeypatch.setattr(
        factory,
        "get_integration_credentials",
        mock_get_credentials,
    )

    gateway = get_payment_gateway(
        gateway_enum,
        clinic_id=clinic_id,
    )

    assert isinstance(
        gateway,
        gateway_class,
    )

    mock_get_credentials.assert_called_once_with(
        clinic_id,
        gateway_enum.value,
    )


# ---------------------------------------------------------------------------
# String gateway normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "gateway_value,gateway_enum",
    [
        (
            "paystack",
            PaymentGateway.PAYSTACK,
        ),
        (
            "PAYSTACK",
            PaymentGateway.PAYSTACK,
        ),
        (
            " Paystack ",
            PaymentGateway.PAYSTACK,
        ),
        (
            "flutterwave",
            PaymentGateway.FLUTTERWAVE,
        ),
        (
            "FLUTTERWAVE",
            PaymentGateway.FLUTTERWAVE,
        ),
        (
            " Stripe ",
            PaymentGateway.STRIPE,
        ),
    ],
)
def test_get_payment_gateway_normalizes_string_value(
    monkeypatch,
    clinic_id,
    credentials,
    gateway_value,
    gateway_enum,
):
    mock_get_credentials = Mock(
        return_value=credentials
    )

    monkeypatch.setattr(
        factory,
        "get_integration_credentials",
        mock_get_credentials,
    )

    gateway = get_payment_gateway(
        gateway_value,
        clinic_id=clinic_id,
    )

    expected_classes = {
        PaymentGateway.PAYSTACK: PaystackGateway,
        PaymentGateway.FLUTTERWAVE: FlutterwaveGateway,
        PaymentGateway.STRIPE: StripeGateway,
    }

    assert gateway.__class__ is expected_classes[
        gateway_enum
    ]

    mock_get_credentials.assert_called_once_with(
        clinic_id,
        gateway_enum.value,
    )


# ---------------------------------------------------------------------------
# Credential propagation
# ---------------------------------------------------------------------------


def test_get_payment_gateway_passes_credentials_to_paystack(
    monkeypatch,
    clinic_id,
):
    credentials = {
        "secret_key": "sk_paystack_test",
    }

    mock_get_credentials = Mock(
        return_value=credentials
    )

    mock_gateway_class = Mock()

    monkeypatch.setattr(
        factory,
        "get_integration_credentials",
        mock_get_credentials,
    )

    monkeypatch.setitem(
        factory._GATEWAY_IMPLEMENTATIONS,
        PaymentGateway.PAYSTACK,
        mock_gateway_class,
    )

    result = get_payment_gateway(
        PaymentGateway.PAYSTACK,
        clinic_id=clinic_id,
    )

    assert result is mock_gateway_class.return_value

    mock_get_credentials.assert_called_once_with(
        clinic_id,
        "paystack",
    )

    mock_gateway_class.assert_called_once_with(
        credentials=credentials,
    )


def test_get_payment_gateway_passes_credentials_to_flutterwave(
    monkeypatch,
    clinic_id,
):
    credentials = {
        "secret_key": "flw_test_secret",
        "webhook_secret": "flw_webhook_secret",
    }

    mock_get_credentials = Mock(
        return_value=credentials
    )

    mock_gateway_class = Mock()

    monkeypatch.setattr(
        factory,
        "get_integration_credentials",
        mock_get_credentials,
    )

    monkeypatch.setitem(
        factory._GATEWAY_IMPLEMENTATIONS,
        PaymentGateway.FLUTTERWAVE,
        mock_gateway_class,
    )

    result = get_payment_gateway(
        PaymentGateway.FLUTTERWAVE,
        clinic_id=clinic_id,
    )

    assert result is mock_gateway_class.return_value

    mock_get_credentials.assert_called_once_with(
        clinic_id,
        "flutterwave",
    )

    mock_gateway_class.assert_called_once_with(
        credentials=credentials,
    )


def test_get_payment_gateway_passes_credentials_to_stripe(
    monkeypatch,
    clinic_id,
):
    credentials = {
        "secret_key": "sk_stripe_test",
        "webhook_secret": "whsec_test",
    }

    mock_get_credentials = Mock(
        return_value=credentials
    )

    mock_gateway_class = Mock()

    monkeypatch.setattr(
        factory,
        "get_integration_credentials",
        mock_get_credentials,
    )

    monkeypatch.setitem(
        factory._GATEWAY_IMPLEMENTATIONS,
        PaymentGateway.STRIPE,
        mock_gateway_class,
    )

    result = get_payment_gateway(
        PaymentGateway.STRIPE,
        clinic_id=clinic_id,
    )

    assert result is mock_gateway_class.return_value

    mock_get_credentials.assert_called_once_with(
        clinic_id,
        "stripe",
    )

    mock_gateway_class.assert_called_once_with(
        credentials=credentials,
    )


# ---------------------------------------------------------------------------
# Unsupported gateways
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "gateway_value",
    [
        "paypal",
        "unknown",
        "",
        "   ",
        "not-a-gateway",
    ],
)
def test_get_payment_gateway_rejects_unsupported_string(
    gateway_value,
    clinic_id,
):
    with pytest.raises(
        ValueError,
        match="Unsupported payment gateway",
    ):
        get_payment_gateway(
            gateway_value,
            clinic_id=clinic_id,
        )


# ---------------------------------------------------------------------------
# Credential service errors
# ---------------------------------------------------------------------------


def test_get_payment_gateway_propagates_credential_error(
    monkeypatch,
    clinic_id,
):
    def raise_error(*args, **kwargs):
        raise ValueError(
            "Integration credentials are not configured"
        )

    monkeypatch.setattr(
        factory,
        "get_integration_credentials",
        raise_error,
    )

    with pytest.raises(
        ValueError,
        match="Integration credentials are not configured",
    ):
        get_payment_gateway(
            PaymentGateway.PAYSTACK,
            clinic_id=clinic_id,
        )


def test_get_payment_gateway_propagates_disabled_integration_error(
    monkeypatch,
    clinic_id,
):
    def raise_error(*args, **kwargs):
        raise ValueError(
            "Integration configuration is disabled"
        )

    monkeypatch.setattr(
        factory,
        "get_integration_credentials",
        raise_error,
    )

    with pytest.raises(
        ValueError,
        match="Integration configuration is disabled",
    ):
        get_payment_gateway(
            PaymentGateway.STRIPE,
            clinic_id=clinic_id,
        )


# ---------------------------------------------------------------------------
# Clinic isolation
# ---------------------------------------------------------------------------


def test_get_payment_gateway_uses_supplied_clinic_id(
    monkeypatch,
    credentials,
):
    mock_get_credentials = Mock(
        return_value=credentials
    )

    monkeypatch.setattr(
        factory,
        "get_integration_credentials",
        mock_get_credentials,
    )

    get_payment_gateway(
        PaymentGateway.PAYSTACK,
        clinic_id=101,
    )

    get_payment_gateway(
        PaymentGateway.PAYSTACK,
        clinic_id=202,
    )

    assert mock_get_credentials.call_args_list == [
        call(
            101,
            "paystack",
        ),
        call(
            202,
            "paystack",
        ),
    ]