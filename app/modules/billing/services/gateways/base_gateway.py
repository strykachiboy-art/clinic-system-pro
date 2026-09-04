from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any


class PaymentGatewayBase(ABC):
    """
    Provider-agnostic contract for payment gateway integrations.

    Concrete gateways such as Stripe, Paystack, and Flutterwave
    must implement this interface.
    """

    @abstractmethod
    def initialize_payment(
        self,
        *,
        reference: str,
        amount: Decimal,
        currency: str,
        customer_email: str,
        callback_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Initialize a payment with the provider.
        Returns provider-specific checkout/payment information.
        """
        raise NotImplementedError

    @abstractmethod
    def verify_payment(
        self,
        *,
        reference: str,
    ) -> dict[str, Any]:
        """
        Verify the status of a payment with the provider.
        Returns normalized provider payment information.
        """
        raise NotImplementedError

    @abstractmethod
    def handle_webhook(
        self,
        *,
        payload: bytes,
        signature: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Validate and process a provider webhook payload.
        """
        raise NotImplementedError