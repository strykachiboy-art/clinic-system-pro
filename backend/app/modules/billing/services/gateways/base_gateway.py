from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any


class GatewayRejectedError(RuntimeError):
    """The payment provider explicitly rejected the request."""


class GatewayUnknownOutcomeError(RuntimeError):
    """The payment provider outcome cannot be known safely."""

class PaymentGatewayBase(ABC):
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
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def verify_payment(
        self,
        *,
        reference: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def handle_webhook(
        self,
        *,
        payload: bytes,
        signature: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError