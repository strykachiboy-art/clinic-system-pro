import pytest

from decimal import Decimal
from unittest.mock import Mock

import requests

from app.modules.billing.services.gateways.flutterwave_gateway import (
    FlutterwaveGateway,
)


@pytest.fixture
def flutterwave_app(app):
    app.config["FLUTTERWAVE_SECRET_KEY"] = "flw_test_secret"
    app.config["FLUTTERWAVE_WEBHOOK_SECRET"] = "flw_webhook_secret"
    return app


@pytest.fixture
def gateway(flutterwave_app):
    with flutterwave_app.app_context():
        return FlutterwaveGateway()


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
# Initialization
# ---------------------------------------------------------------------------


def test_initialize_payment_success(
    flutterwave_app,
    monkeypatch,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        response = FakeResponse(
            ok=True,
            json_data={
                "status": "success",
                "message": "Payment link generated",
                "data": {
                    "id": 987654,
                    "link": "https://checkout.flutterwave.com/test",
                },
            },
        )

        mock_post = Mock(return_value=response)

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.flutterwave_gateway.requests.post",
            mock_post,
        )

        result = gateway.initialize_payment(
            reference="INV-001",
            amount=Decimal("125.50"),
            currency="ngn",
            customer_email=" patient@example.com ",
            callback_url="https://example.com/callback",
            metadata={
                "clinic_id": 10,
                "invoice_id": 25,
            },
        )

    assert result == {
        "provider": "flutterwave",
        "reference": "INV-001",
        "transaction_id": "987654",
        "status": "initialized",
        "amount": Decimal("125.50"),
        "currency": "NGN",
        "payment_link": "https://checkout.flutterwave.com/test",
    }

    mock_post.assert_called_once()

    _, kwargs = mock_post.call_args

    assert kwargs["headers"] == {
        "Authorization": "Bearer flw_test_secret",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    assert kwargs["timeout"] == 30

    assert kwargs["json"] == {
        "tx_ref": "INV-001",
        "amount": "125.50",
        "currency": "NGN",
        "customer": {
            "email": "patient@example.com",
        },
        "redirect_url": "https://example.com/callback",
        "meta": [
            {
                "metaname": "clinic_id",
                "metavalue": "10",
            },
            {
                "metaname": "invoice_id",
                "metavalue": "25",
            },
        ],
    }


def test_initialize_payment_without_optional_fields(
    flutterwave_app,
    monkeypatch,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        response = FakeResponse(
            json_data={
                "status": "success",
                "data": {
                    "id": 123,
                },
            },
        )

        mock_post = Mock(return_value=response)

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.flutterwave_gateway.requests.post",
            mock_post,
        )

        result = gateway.initialize_payment(
            reference="REF-123",
            amount=Decimal("50"),
            currency="usd",
            customer_email="user@example.com",
        )

    assert result["provider"] == "flutterwave"
    assert result["reference"] == "REF-123"
    assert result["transaction_id"] == "123"
    assert result["amount"] == Decimal("50")
    assert result["currency"] == "USD"

    _, kwargs = mock_post.call_args

    assert "redirect_url" not in kwargs["json"]
    assert "meta" not in kwargs["json"]


@pytest.mark.parametrize(
    "reference",
    [
        "",
        "   ",
        None,
        123,
    ],
)
def test_initialize_payment_rejects_invalid_reference(
    flutterwave_app,
    reference,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        with pytest.raises(
            ValueError,
            match="Payment reference is required",
        ):
            gateway.initialize_payment(
                reference=reference,
                amount=Decimal("100"),
                currency="NGN",
                customer_email="user@example.com",
            )


@pytest.mark.parametrize(
    "currency",
    [
        "",
        "   ",
        None,
        123,
    ],
)
def test_initialize_payment_rejects_invalid_currency(
    flutterwave_app,
    currency,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        with pytest.raises(
            ValueError,
            match="Currency is required",
        ):
            gateway.initialize_payment(
                reference="REF-1",
                amount=Decimal("100"),
                currency=currency,
                customer_email="user@example.com",
            )


@pytest.mark.parametrize(
    "email",
    [
        "",
        "   ",
        None,
        123,
    ],
)
def test_initialize_payment_rejects_invalid_email(
    flutterwave_app,
    email,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        with pytest.raises(
            ValueError,
            match="Customer email is required",
        ):
            gateway.initialize_payment(
                reference="REF-1",
                amount=Decimal("100"),
                currency="NGN",
                customer_email=email,
            )


@pytest.mark.parametrize(
    "amount",
    [
        Decimal("0"),
        Decimal("-1"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_initialize_payment_rejects_invalid_amount(
    flutterwave_app,
    amount,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

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
    flutterwave_app,
    monkeypatch,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        def raise_request_error(*args, **kwargs):
            raise requests.RequestException(
                "connection refused"
            )

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.flutterwave_gateway.requests.post",
            raise_request_error,
        )

        with pytest.raises(
            RuntimeError,
            match="Flutterwave payment initialization failed",
        ):
            gateway.initialize_payment(
                reference="REF-1",
                amount=Decimal("100"),
                currency="NGN",
                customer_email="user@example.com",
            )


def test_initialize_payment_handles_invalid_json(
    flutterwave_app,
    monkeypatch,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        response = FakeResponse(
            ok=True,
            json_error=ValueError("invalid json"),
        )

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.flutterwave_gateway.requests.post",
            Mock(return_value=response),
        )

        with pytest.raises(
            RuntimeError,
            match="Flutterwave returned an invalid response",
        ):
            gateway.initialize_payment(
                reference="REF-1",
                amount=Decimal("100"),
                currency="NGN",
                customer_email="user@example.com",
            )


def test_initialize_payment_handles_provider_failure(
    flutterwave_app,
    monkeypatch,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        response = FakeResponse(
            ok=False,
            status_code=400,
            json_data={
                "status": "error",
                "message": "Invalid currency",
            },
        )

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.flutterwave_gateway.requests.post",
            Mock(return_value=response),
        )

        with pytest.raises(
            RuntimeError,
            match=(
                "Flutterwave payment initialization "
                "failed: Invalid currency"
            ),
        ):
            gateway.initialize_payment(
                reference="REF-1",
                amount=Decimal("100"),
                currency="NGN",
                customer_email="user@example.com",
            )


@pytest.mark.parametrize(
    "response_data",
    [
        {},
        {"status": "error"},
        {"status": "pending"},
        {"status": "success", "data": None},
    ],
)
def test_initialize_payment_rejects_invalid_provider_response(
    flutterwave_app,
    monkeypatch,
    response_data,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        response = FakeResponse(
            ok=True,
            json_data=response_data,
        )

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.flutterwave_gateway.requests.post",
            Mock(return_value=response),
        )

        if response_data.get("status") == "success":
            result = gateway.initialize_payment(
                reference="REF-1",
                amount=Decimal("100"),
                currency="NGN",
                customer_email="user@example.com",
            )

            assert result["transaction_id"] is None
        else:
            with pytest.raises(RuntimeError):
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
    flutterwave_app,
    monkeypatch,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        response = FakeResponse(
            ok=True,
            json_data={
                "status": "success",
                "data": {
                    "id": 987654,
                    "tx_ref": "INV-001",
                    "status": "successful",
                    "amount": 125.50,
                    "charged_amount": 127.00,
                    "currency": "ngn",
                },
            },
        )

        mock_get = Mock(return_value=response)

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.flutterwave_gateway.requests.get",
            mock_get,
        )

        result = gateway.verify_payment(
            reference="987654"
        )

    assert result == {
        "provider": "flutterwave",
        "reference": "INV-001",
        "transaction_id": "987654",
        "status": "successful",
        "amount": 125.50,
        "charged_amount": 127.00,
        "currency": "NGN",
        "paid": True,
    }

    mock_get.assert_called_once()

    args, kwargs = mock_get.call_args

    assert (
        args[0]
        == "https://api.flutterwave.com/v3/"
        "transactions/987654/verify"
    )

    assert kwargs["headers"] == {
        "Authorization": "Bearer flw_test_secret",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    assert kwargs["timeout"] == 30


def test_verify_payment_accepts_numeric_string_with_whitespace(
    flutterwave_app,
    monkeypatch,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        response = FakeResponse(
            ok=True,
            json_data={
                "status": "success",
                "data": {
                    "id": 123,
                    "tx_ref": "REF-123",
                    "status": "successful",
                    "amount": 100,
                    "charged_amount": 100,
                    "currency": "NGN",
                },
            },
        )

        mock_get = Mock(return_value=response)

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.flutterwave_gateway.requests.get",
            mock_get,
        )

        result = gateway.verify_payment(
            reference=" 123 "
        )

    assert result["transaction_id"] == "123"
    assert result["paid"] is True

    args, _ = mock_get.call_args

    assert args[0].endswith(
        "/transactions/123/verify"
    )


@pytest.mark.parametrize(
    "reference,expected_message",
    [
        (
            "ABC-123",
            "Flutterwave verification requires a transaction ID",
        ),
        (
            "0",
            "Flutterwave transaction ID must be positive",
        ),
        (
            "-10",
            "Flutterwave transaction ID must be positive",
        ),
    ],
)
def test_verify_payment_rejects_invalid_transaction_id(
    flutterwave_app,
    reference,
    expected_message,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        with pytest.raises(
            ValueError,
            match=expected_message,
        ):
            gateway.verify_payment(
                reference=reference
            )


def test_verify_payment_handles_request_failure(
    flutterwave_app,
    monkeypatch,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        def raise_request_error(*args, **kwargs):
            raise requests.RequestException(
                "timeout"
            )

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.flutterwave_gateway.requests.get",
            raise_request_error,
        )

        with pytest.raises(
            RuntimeError,
            match="Flutterwave payment verification failed",
        ):
            gateway.verify_payment(
                reference="123"
            )


def test_verify_payment_handles_invalid_json(
    flutterwave_app,
    monkeypatch,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        response = FakeResponse(
            ok=True,
            json_error=ValueError("invalid json"),
        )

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.flutterwave_gateway.requests.get",
            Mock(return_value=response),
        )

        with pytest.raises(
            RuntimeError,
            match=(
                "Flutterwave returned an invalid "
                "verification response"
            ),
        ):
            gateway.verify_payment(
                reference="123"
            )


def test_verify_payment_handles_provider_failure(
    flutterwave_app,
    monkeypatch,
):
    with flutterwave_app.app_context():
        gateway = FlutterwaveGateway()

        response = FakeResponse(
            ok=False,
            status_code=404,
            json_data={
                "status": "error",
                "message": "Transaction not found",
            },
        )

        monkeypatch.setattr(
            "app.modules.billing.services.gateways.flutterwave_gateway.requests.get",
            Mock(return_value=response),
        )

        with pytest.raises(
            RuntimeError,
            match=(
                "Flutterwave payment verification "
                "failed: Transaction not found"
            ),
        ):
            gateway.verify_payment(
                reference="123"
            )


# ---------------------------------------------------------------------------
# Constructor / configuration
# ---------------------------------------------------------------------------


def test_gateway_requires_secret_key(app):
    app.config.pop(
        "FLUTTERWAVE_SECRET_KEY",
        None,
    )

    with app.app_context():
        with pytest.raises(
            ValueError,
            match="Flutterwave secret key is not configured",
        ):
            FlutterwaveGateway()