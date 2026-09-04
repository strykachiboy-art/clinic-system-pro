import hashlib
import hmac
import json
from decimal import Decimal, InvalidOperation
from typing import Any

import requests
from flask import current_app

from app.modules.billing.services.gateways.base_gateway import PaymentGatewayBase


class FlutterwaveGateway(PaymentGatewayBase):
    """
    Flutterwave payment gateway implementation.

    This class is responsible only for communication with Flutterwave.
    It does not create or update Payment or Invoice records.

    Amounts received from the billing layer are treated as major
    currency units and converted to the smallest currency unit
    where applicable.
    """

    BASE_URL = "https://api.flutterwave.com/v3"

    def __init__(self):
        self.secret_key = current_app.config.get("FLUTTERWAVE_SECRET_KEY")

        if not self.secret_key:
            raise ValueError(
                "Flutterwave secret key is not configured"
            )

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

        return reference.strip()

    @staticmethod
    def _normalize_amount(amount: Decimal) -> Decimal:
        try:
            amount = Decimal(amount)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("Invalid payment amount") from exc

        if amount <= 0:
            raise ValueError(
                "Payment amount must be greater than zero"
            )

        return amount

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
        amount = self._normalize_amount(amount)
        currency = self._normalize_currency(currency)
        customer_email = self._normalize_email(customer_email)

        payload: dict[str, Any] = {
            "tx_ref": reference,
            "amount": str(amount),
            "currency": currency,
            "customer": {
                "email": customer_email,
            },
        }

        if callback_url:
            payload["redirect_url"] = callback_url

        if metadata:
            payload["meta"] = [
                {
                    "metaname": str(key),
                    "metavalue": str(value),
                }
                for key, value in metadata.items()
            ]

        try:
            response = requests.post(
                f"{self.BASE_URL}/payments",
                headers=self._headers(),
                json=payload,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Flutterwave payment initialization failed: {exc}"
            ) from exc

        try:
            response_data = response.json()
        except ValueError as exc:
            raise RuntimeError(
                "Flutterwave returned an invalid response"
            ) from exc

        if not response.ok or response_data.get("status") != "success":
            message = response_data.get(
                "message",
                "Flutterwave payment initialization failed",
            )

            raise RuntimeError(
                f"Flutterwave payment initialization failed: {message}"
            )

        data = response_data.get("data") or {}

        return {
            "provider": "flutterwave",
            "reference": reference,
            "transaction_id": None,
            "status": "initialized",
            "amount": amount,
            "currency": currency,
            "payment_link": data.get("link"),
        }

    def verify_payment(
        self,
        *,
        reference: str,
    ) -> dict[str, Any]:
        """
        Verify a Flutterwave transaction.

        Flutterwave's verification endpoint expects the provider's
        transaction ID, not the merchant tx_ref.

        Therefore, `reference` is treated as the Flutterwave
        transaction ID for this provider.
        """
        reference = self._normalize_reference(reference)

        try:
            transaction_id = int(reference)
        except ValueError as exc:
            raise ValueError(
                "Flutterwave verification requires a transaction ID"
            ) from exc

        try:
            response = requests.get(
                f"{self.BASE_URL}/transactions/{transaction_id}/verify",
                headers=self._headers(),
                timeout=30,
            )
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Flutterwave payment verification failed: {exc}"
            ) from exc

        try:
            response_data = response.json()
        except ValueError as exc:
            raise RuntimeError(
                "Flutterwave returned an invalid verification response"
            ) from exc

        if not response.ok or response_data.get("status") != "success":
            message = response_data.get(
                "message",
                "Flutterwave payment verification failed",
            )

            raise RuntimeError(
                f"Flutterwave payment verification failed: {message}"
            )

        data = response_data.get("data") or {}

        transaction_status = data.get("status")

        return {
            "provider": "flutterwave",
            "reference": data.get("tx_ref"),
            "transaction_id": (
                str(data["id"])
                if data.get("id") is not None
                else None
            ),
            "status": transaction_status,
            "amount": data.get("amount"),
            "charged_amount": data.get("charged_amount"),
            "currency": (
                data.get("currency") or ""
            ).upper(),
            "paid": transaction_status == "successful",
        }

    def handle_webhook(
        self,
        *,
        payload: bytes,
        signature: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Validate and normalize a Flutterwave webhook.

        The webhook secret/hash configuration is intentionally
        handled separately from the gateway implementation for now.
        """

        if not payload:
            raise ValueError("Webhook payload is required")

        webhook_signature = signature

        if not webhook_signature and headers:
            webhook_signature = (
                headers.get("flutterwave-signature")
                or headers.get("Flutterwave-Signature")
                or headers.get("verif-hash")
                or headers.get("Verif-Hash")
            )

        if not webhook_signature:
            raise ValueError(
                "Flutterwave webhook signature is required"
            )

        webhook_secret = current_app.config.get(
            "FLUTTERWAVE_WEBHOOK_SECRET"
        )

        if not webhook_secret:
            raise ValueError(
                "Flutterwave webhook secret is not configured"
            )

        expected_signature = hmac.new(
            webhook_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(
            expected_signature,
            webhook_signature,
        ):
            raise ValueError(
                "Invalid Flutterwave webhook signature"
            )

        try:
            event = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                "Invalid Flutterwave webhook payload"
            ) from exc

        event_type = event.get("event") or event.get("type")

        if not event_type:
            raise ValueError(
                "Flutterwave webhook event type is missing"
            )

        event_data = event.get("data") or {}

        transaction_id = event_data.get("id")

        normalized: dict[str, Any] = {
            "provider": "flutterwave",
            "event_id": (
                str(event.get("id"))
                if event.get("id") is not None
                else (
                    str(transaction_id)
                    if transaction_id is not None
                    else hashlib.sha256(payload).hexdigest()
                )
            ),
            "event_type": event_type,
            "livemode": (
                event_data.get("account_id") is not None
            ),
            "transaction_id": (
                str(transaction_id)
                if transaction_id is not None
                else None
            ),
            "reference": event_data.get("tx_ref"),
            "amount": event_data.get("amount"),
            "currency": (
                event_data.get("currency") or ""
            ).upper(),
        }

        transaction_status = event_data.get("status")

        if (
            event_type == "charge.completed"
            and transaction_status == "successful"
        ):
            normalized["status"] = "successful"

        elif transaction_status in {
            "failed",
            "cancelled",
            "canceled",
        }:
            normalized["status"] = "failed"
            normalized["failure_reason"] = (
                event_data.get("processor_response")
                or event_data.get("message")
                or "Flutterwave payment failed"
            )

        else:
            normalized["status"] = transaction_status

        return normalized