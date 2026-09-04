import hashlib
import hmac
import json
from decimal import Decimal, InvalidOperation
from typing import Any

import requests
from flask import current_app

from app.modules.billing.services.gateways.base_gateway import PaymentGatewayBase


class PaystackGateway(PaymentGatewayBase):
    """
    Paystack payment gateway implementation.

    This class is responsible only for communication with Paystack.
    It does not create or update Payment or Invoice records.

    Amounts received from the billing layer are treated as major
    currency units and converted to Paystack's smallest currency unit
    before making API requests.
    """

    BASE_URL = "https://api.paystack.co"

    def __init__(self):
        self.secret_key = current_app.config.get("PAYSTACK_SECRET_KEY")

        if not self.secret_key:
            raise ValueError("Paystack secret key is not configured")

    @staticmethod
    def _to_smallest_unit(amount: Decimal) -> int:
        try:
            amount = Decimal(amount)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("Invalid payment amount") from exc

        if amount <= 0:
            raise ValueError("Payment amount must be greater than zero")

        smallest_unit = amount * Decimal("100")

        if smallest_unit != smallest_unit.to_integral_value():
            raise ValueError(
                "Amount has more precision than the currency supports"
            )

        return int(smallest_unit)

    @staticmethod
    def _normalize_currency(currency: str) -> str:
        if not currency or not currency.strip():
            raise ValueError("Currency is required")

        return currency.strip().upper()

    @staticmethod
    def _normalize_email(email: str) -> str:
        if not email or not email.strip():
            raise ValueError("Customer email is required")

        return email.strip()

    @staticmethod
    def _normalize_reference(reference: str) -> str:
        if not reference or not reference.strip():
            raise ValueError("Payment reference is required")

        reference = reference.strip()

        allowed_characters = set(
            "abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789"
            "-._="
        )

        if any(character not in allowed_characters for character in reference):
            raise ValueError(
                "Payment reference contains unsupported characters"
            )

        return reference

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

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
        reference = self._normalize_reference(reference)
        customer_email = self._normalize_email(customer_email)
        currency = self._normalize_currency(currency)

        amount_in_smallest_unit = self._to_smallest_unit(amount)

        payment_metadata: dict[str, Any] = {
            "reference": reference,
        }

        if metadata:
            payment_metadata.update(metadata)

        payload: dict[str, Any] = {
            "email": customer_email,
            "amount": str(amount_in_smallest_unit),
            "currency": currency,
            "reference": reference,
            "metadata": json.dumps(payment_metadata),
        }

        if callback_url:
            payload["callback_url"] = callback_url

        try:
            response = requests.post(
                f"{self.BASE_URL}/transaction/initialize",
                headers=self._headers(),
                json=payload,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Paystack payment initialization failed: {exc}"
            ) from exc

        try:
            response_data = response.json()
        except ValueError as exc:
            raise RuntimeError(
                "Paystack returned an invalid response"
            ) from exc

        if not response.ok or not response_data.get("status"):
            message = response_data.get(
                "message",
                "Paystack payment initialization failed",
            )

            raise RuntimeError(
                f"Paystack payment initialization failed: {message}"
            )

        data = response_data.get("data") or {}

        return {
            "provider": "paystack",
            "reference": data.get("reference", reference),
            "transaction_id": None,
            "status": "initialized",
            "amount": amount,
            "currency": currency,
            "authorization_url": data.get("authorization_url"),
            "access_code": data.get("access_code"),
        }

    def verify_payment(
        self,
        *,
        reference: str,
    ) -> dict[str, Any]:
        reference = self._normalize_reference(reference)

        try:
            response = requests.get(
                f"{self.BASE_URL}/transaction/verify/{reference}",
                headers=self._headers(),
                timeout=30,
            )
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Paystack payment verification failed: {exc}"
            ) from exc

        try:
            response_data = response.json()
        except ValueError as exc:
            raise RuntimeError(
                "Paystack returned an invalid verification response"
            ) from exc

        if not response.ok or not response_data.get("status"):
            message = response_data.get(
                "message",
                "Paystack payment verification failed",
            )

            raise RuntimeError(
                f"Paystack payment verification failed: {message}"
            )

        data = response_data.get("data") or {}

        transaction_status = data.get("status")

        return {
            "provider": "paystack",
            "reference": data.get("reference", reference),
            "transaction_id": (
                str(data["id"])
                if data.get("id") is not None
                else None
            ),
            "status": transaction_status,
            "amount": data.get("amount"),
            "currency": (
                data.get("currency") or ""
            ).upper(),
            "paid": transaction_status == "success",
        }

    def handle_webhook(
        self,
        *,
        payload: bytes,
        signature: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not payload:
            raise ValueError("Webhook payload is required")

        webhook_signature = signature

        if not webhook_signature and headers:
            webhook_signature = (
                headers.get("x-paystack-signature")
                or headers.get("X-Paystack-Signature")
            )

        if not webhook_signature:
            raise ValueError(
                "Paystack webhook signature is required"
            )

        expected_signature = hmac.new(
            self.secret_key.encode("utf-8"),
            payload,
            hashlib.sha512,
        ).hexdigest()

        if not hmac.compare_digest(
            expected_signature,
            webhook_signature,
        ):
            raise ValueError(
                "Invalid Paystack webhook signature"
            )

        try:
            event = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                "Invalid Paystack webhook payload"
            ) from exc

        event_type = event.get("event")

        if not event_type:
            raise ValueError(
                "Paystack webhook event type is missing"
            )

        event_data = event.get("data") or {}

        transaction_id = event_data.get("id")

        normalized: dict[str, Any] = {
            "provider": "paystack",
            "event_id": (
                str(transaction_id)
                if transaction_id is not None
                else hashlib.sha256(payload).hexdigest()
            ),
            "event_type": event_type,
            "livemode": event_data.get("domain") == "live",
            "transaction_id": (
                str(transaction_id)
                if transaction_id is not None
                else None
            ),
            "reference": event_data.get("reference"),
        }

        transaction_status = event_data.get("status")

        if event_type == "charge.success":
            normalized.update(
                {
                    "status": "successful",
                    "amount": event_data.get("amount"),
                    "currency": (
                        event_data.get("currency") or ""
                    ).upper(),
                }
            )

        elif transaction_status in {
            "failed",
            "abandoned",
            "reversed",
        }:
            normalized.update(
                {
                    "status": "failed",
                    "amount": event_data.get("amount"),
                    "currency": (
                        event_data.get("currency") or ""
                    ).upper(),
                    "failure_reason": (
                        event_data.get("gateway_response")
                        or event_data.get("message")
                        or "Paystack payment failed"
                    ),
                }
            )

        else:
            normalized.update(
                {
                    "status": transaction_status,
                    "amount": event_data.get("amount"),
                    "currency": (
                        event_data.get("currency") or ""
                    ).upper(),
                }
            )

        return normalized