import json

import pytest
import requests

from decimal import Decimal
from unittest.mock import Mock

from app.modules.billing.services.gateways.paystack_gateway import (
    PaystackGateway,
)


@pytest.fixture
def paystack_app(app):
    app.config["PAYSTACK_SECRET_KEY"] = "sk_test_secret"
    return app


@pytest.fixture
def gateway(paystack_app):
    with paystack_app.app_context():
        return PaystackGateway()


class FakeResponse:
    def __init__(
        self,
        *,
        ok=True,
        status_code=200,
        json_data=None,
        json_error=None,
    ):
        self.ok = ok
        self.status_code = status_code
        self._json_data = json_data
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise self._json_error

        return self._json_data


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_gateway_requires_secret_key(app):
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
# Amount / normalization helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "amount,expected",
    [
        (Decimal("100"), 10000),
        (Decimal("100.50"), 10050),
        ("25.75", 2575),
    ],
)
def test_to_smallest_unit(
    gateway,
    amount,
    expected,
):
    assert gateway._to_smallest_unit(
        amount
    ) == expected


@pytest.mark.parametrize(
    "amount",
    [
        Decimal("0"),
        Decimal("-1"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        Decimal("10.001"),
    ],
)
def test_to_smallest_unit_rejects_invalid_amount(
    gateway,
    amount,
):
    with pytest.raises(ValueError):
        gateway._to_smallest_unit(amount)


@pytest.mark.parametrize(
    "currency,expected",
    [
        ("ngn", "NGN"),
        (" NGN ", "NGN"),
        ("usd", "USD"),
    ],
)
def test_normalize_currency(
    gateway,
    currency,
    expected,
):
    assert gateway._normalize_currency(
        currency
    ) == expected


@pytest.mark.parametrize(
    "currency",
    [
        "",
        "   ",
        None,
        123,
    ],
)
def test_normalize_currency_rejects_invalid_value(
    gateway,
    currency,
):
    with pytest.raises(
        ValueError,
        match="Currency is required",
    ):
        gateway._normalize_currency(currency)


@pytest.mark.parametrize(
    "email,expected",
    [
        (
            "user@example.com",
            "user@example.com",
        ),
        (
            " user@example.com ",
            "user@example.com",
        ),
    ],
)
def test_normalize_email(
    gateway,
    email,
    expected,
):
    assert gateway._normalize_email(
        email
    ) == expected


@pytest.mark.parametrize(
    "email",
    [
        "",
        "   ",
        None,
        123,
    ],
)
def test_normalize_email_rejects_invalid_value(
    gateway,
    email,
):
    with pytest.raises(
        ValueError,
        match="Customer email is required",
    ):
        gateway._normalize_email(email)


@pytest.mark.parametrize(
    "reference,expected",
    [
        (
            "INV-001",
            "INV-001",
        ),
        (
            " ref_123 ",
            "ref_123",
        ),
        (
            "payment=123",
            "payment=123",
        ),
        (
            "ABC.DEF-123",
            "ABC.DEF-123",
        ),
    ],
)
def test_normalize_reference(
    gateway,
    reference,
    expected,
):
    assert gateway._normalize_reference(
        reference
    ) == expected


@pytest.mark.parametrize(
    "reference",
    [
        "",
        "   ",
        None,
        123,
        "REF/123",
        "REF 123",
        "REF@123",
        "REF#123",
    ],
)
def test_normalize_reference_rejects_invalid_value(
    gateway,
    reference,
):
    with pytest.raises(
        ValueError,
    ):
        gateway._normalize_reference(reference)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


def test_initialize_payment_success(
    paystack_app,
    monkeypatch,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        response = FakeResponse(
            ok=True,
            json_data={
                "status": True,
                "message": "Authorization URL created",
                "data": {
                    "authorization_url": (
                        "https://checkout.paystack.com/test"
                    ),
                    "access_code": "access_123",
                    "reference": "INV-001",
                },
            },
        )

        mock_post = Mock(
            return_value=response
        )

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.paystack_gateway.requests.post",
            mock_post,
        )

        result = gateway.initialize_payment(
            reference="INV-001",
            amount=Decimal("125.50"),
            currency="ngn",
            customer_email=" patient@example.com ",
            callback_url=(
                "https://example.com/callback"
            ),
            metadata={
                "clinic_id": 10,
                "invoice_id": 25,
            },
        )

    assert result == {
        "provider": "paystack",
        "reference": "INV-001",
        "transaction_id": None,
        "status": "initialized",
        "amount": Decimal("125.50"),
        "currency": "NGN",
        "authorization_url": (
            "https://checkout.paystack.com/test"
        ),
        "access_code": "access_123",
    }

    mock_post.assert_called_once()

    args, kwargs = mock_post.call_args

    assert (
        args[0]
        == "https://api.paystack.co/"
        "transaction/initialize"
    )

    assert kwargs["headers"] == {
        "Authorization": (
            "Bearer sk_test_secret"
        ),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    assert kwargs["timeout"] == 30

    assert kwargs["json"] == {
        "email": "patient@example.com",
        "amount": "12550",
        "currency": "NGN",
        "reference": "INV-001",
        "metadata": json.dumps(
            {
                "reference": "INV-001",
                "clinic_id": 10,
                "invoice_id": 25,
            }
        ),
        "callback_url": (
            "https://example.com/callback"
        ),
    }


def test_initialize_payment_without_optional_fields(
    paystack_app,
    monkeypatch,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        response = FakeResponse(
            json_data={
                "status": True,
                "data": {
                    "reference": "REF-123",
                    "authorization_url": (
                        "https://checkout.paystack.com/test"
                    ),
                    "access_code": "access_123",
                },
            }
        )

        mock_post = Mock(
            return_value=response
        )

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.paystack_gateway.requests.post",
            mock_post,
        )

        result = gateway.initialize_payment(
            reference="REF-123",
            amount=Decimal("50"),
            currency="usd",
            customer_email="user@example.com",
        )

    assert result["provider"] == "paystack"
    assert result["reference"] == "REF-123"
    assert result["transaction_id"] is None
    assert result["amount"] == Decimal("50")
    assert result["currency"] == "USD"

    _, kwargs = mock_post.call_args

    assert "callback_url" not in kwargs["json"]

    metadata = json.loads(
        kwargs["json"]["metadata"]
    )

    assert metadata == {
        "reference": "REF-123",
    }


@pytest.mark.parametrize(
    "amount",
    [
        Decimal("0"),
        Decimal("-1"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        Decimal("10.001"),
    ],
)
def test_initialize_payment_rejects_invalid_amount(
    paystack_app,
    amount,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        with pytest.raises(
            ValueError,
        ):
            gateway.initialize_payment(
                reference="REF-1",
                amount=amount,
                currency="NGN",
                customer_email="user@example.com",
            )


def test_initialize_payment_handles_request_failure(
    paystack_app,
    monkeypatch,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        def raise_request_error(
            *args,
            **kwargs,
        ):
            raise requests.RequestException(
                "connection refused"
            )

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.paystack_gateway.requests.post",
            raise_request_error,
        )

        with pytest.raises(
            RuntimeError,
            match=(
                "Paystack payment initialization failed"
            ),
        ):
            gateway.initialize_payment(
                reference="REF-1",
                amount=Decimal("100"),
                currency="NGN",
                customer_email="user@example.com",
            )


def test_initialize_payment_handles_invalid_json(
    paystack_app,
    monkeypatch,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        response = FakeResponse(
            ok=True,
            json_error=ValueError(
                "invalid json"
            ),
        )

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.paystack_gateway.requests.post",
            Mock(return_value=response),
        )

        with pytest.raises(
            RuntimeError,
            match=(
                "Paystack returned an invalid response"
            ),
        ):
            gateway.initialize_payment(
                reference="REF-1",
                amount=Decimal("100"),
                currency="NGN",
                customer_email="user@example.com",
            )


def test_initialize_payment_handles_provider_failure(
    paystack_app,
    monkeypatch,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        response = FakeResponse(
            ok=False,
            status_code=400,
            json_data={
                "status": False,
                "message": "Invalid amount",
            },
        )

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.paystack_gateway.requests.post",
            Mock(return_value=response),
        )

        with pytest.raises(
            RuntimeError,
            match=(
                "Paystack payment initialization "
                "failed: Invalid amount"
            ),
        ):
            gateway.initialize_payment(
                reference="REF-1",
                amount=Decimal("100"),
                currency="NGN",
                customer_email="user@example.com",
            )


def test_initialize_payment_rejects_non_boolean_status(
    paystack_app,
    monkeypatch,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        response = FakeResponse(
            ok=True,
            json_data={
                "status": "true",
                "data": {},
            },
        )

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.paystack_gateway.requests.post",
            Mock(return_value=response),
        )

        with pytest.raises(
            RuntimeError,
            match=(
                "Paystack payment initialization failed"
            ),
        ):
            gateway.initialize_payment(
                reference="REF-1",
                amount=Decimal("100"),
                currency="NGN",
                customer_email="user@example.com",
            )


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def test_verify_payment_success(
    paystack_app,
    monkeypatch,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        response = FakeResponse(
            ok=True,
            json_data={
                "status": True,
                "message": "Verification successful",
                "data": {
                    "id": 987654,
                    "reference": "INV-001",
                    "status": "success",
                    "amount": 12550,
                    "currency": "ngn",
                },
            },
        )

        mock_get = Mock(
            return_value=response
        )

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.paystack_gateway.requests.get",
            mock_get,
        )

        result = gateway.verify_payment(
            reference="INV-001"
        )

    assert result == {
        "provider": "paystack",
        "reference": "INV-001",
        "transaction_id": "987654",
        "status": "success",
        "amount": 12550,
        "currency": "NGN",
        "paid": True,
    }

    mock_get.assert_called_once()

    args, kwargs = mock_get.call_args

    assert (
        args[0]
        == "https://api.paystack.co/"
        "transaction/verify/INV-001"
    )

    assert kwargs["headers"] == {
        "Authorization": (
            "Bearer sk_test_secret"
        ),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    assert kwargs["timeout"] == 30


def test_verify_payment_trims_reference(
    paystack_app,
    monkeypatch,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        response = FakeResponse(
            json_data={
                "status": True,
                "data": {
                    "id": 123,
                    "reference": "REF-123",
                    "status": "success",
                    "amount": 10000,
                    "currency": "NGN",
                },
            }
        )

        mock_get = Mock(
            return_value=response
        )

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.paystack_gateway.requests.get",
            mock_get,
        )

        result = gateway.verify_payment(
            reference=" REF-123 "
        )

    assert result["reference"] == "REF-123"

    args, _ = mock_get.call_args

    assert args[0].endswith(
        "/transaction/verify/REF-123"
    )


def test_verify_payment_handles_request_failure(
    paystack_app,
    monkeypatch,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        def raise_request_error(
            *args,
            **kwargs,
        ):
            raise requests.RequestException(
                "timeout"
            )

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.paystack_gateway.requests.get",
            raise_request_error,
        )

        with pytest.raises(
            RuntimeError,
            match=(
                "Paystack payment verification failed"
            ),
        ):
            gateway.verify_payment(
                reference="REF-1"
            )


def test_verify_payment_handles_invalid_json(
    paystack_app,
    monkeypatch,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        response = FakeResponse(
            ok=True,
            json_error=ValueError(
                "invalid json"
            ),
        )

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.paystack_gateway.requests.get",
            Mock(return_value=response),
        )

        with pytest.raises(
            RuntimeError,
            match=(
                "Paystack returned an invalid "
                "verification response"
            ),
        ):
            gateway.verify_payment(
                reference="REF-1"
            )


def test_verify_payment_handles_provider_failure(
    paystack_app,
    monkeypatch,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        response = FakeResponse(
            ok=False,
            status_code=404,
            json_data={
                "status": False,
                "message": "Transaction not found",
            },
        )

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.paystack_gateway.requests.get",
            Mock(return_value=response),
        )

        with pytest.raises(
            RuntimeError,
            match=(
                "Paystack payment verification "
                "failed: Transaction not found"
            ),
        ):
            gateway.verify_payment(
                reference="REF-1"
            )


@pytest.mark.parametrize(
    "status,paid",
    [
        ("success", True),
        ("failed", False),
        ("abandoned", False),
        ("pending", False),
    ],
)
def test_verify_payment_normalizes_paid_status(
    paystack_app,
    monkeypatch,
    status,
    paid,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        response = FakeResponse(
            json_data={
                "status": True,
                "data": {
                    "id": 123,
                    "reference": "REF-1",
                    "status": status,
                    "amount": 10000,
                    "currency": "ngn",
                },
            }
        )

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.paystack_gateway.requests.get",
            Mock(return_value=response),
        )

        result = gateway.verify_payment(
            reference="REF-1"
        )

    assert result["status"] == status
    assert result["paid"] is paid


def test_verify_payment_uses_input_reference_when_provider_reference_missing(
    paystack_app,
    monkeypatch,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        response = FakeResponse(
            json_data={
                "status": True,
                "data": {
                    "id": 123,
                    "status": "success",
                    "amount": 10000,
                    "currency": "ngn",
                },
            }
        )

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.paystack_gateway.requests.get",
            Mock(return_value=response),
        )

        result = gateway.verify_payment(
            reference="REF-1"
        )

    assert result["reference"] == "REF-1"


def test_verify_payment_handles_missing_transaction_id(
    paystack_app,
    monkeypatch,
):
    with paystack_app.app_context():
        gateway = PaystackGateway()

        response = FakeResponse(
            json_data={
                "status": True,
                "data": {
                    "reference": "REF-1",
                    "status": "success",
                    "amount": 10000,
                    "currency": "ngn",
                },
            }
        )

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.paystack_gateway.requests.get",
            Mock(return_value=response),
        )

        result = gateway.verify_payment(
            reference="REF-1"
        )

    assert result["transaction_id"] is None