from decimal import Decimal, InvalidOperation
from typing import Any

import stripe
from flask import current_app

from app.modules.billing.services.gateways.base_gateway import PaymentGatewayBase


class StripeGateway(PaymentGatewayBase):
    """
    Stripe payment gateway implementation.

    This class is responsible only for communication with Stripe.
    It does not create or update Payment or Invoice records.

    Amounts received from the billing layer are treated as major
    currency units and converted to Stripe's smallest currency unit
    before making API requests.
    """

    def __init__(self):
        self.secret_key = current_app.config.get("STRIPE_SECRET_KEY")
        self.webhook_secret = current_app.config.get("STRIPE_WEBHOOK_SECRET")

        if not self.secret_key:
            raise ValueError("Stripe secret key is not configured")

        stripe.api_key = self.secret_key

    @staticmethod
    def _to_smallest_unit(amount: Decimal, currency: str) -> int:
        try:
            amount = Decimal(amount)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("Invalid payment amount") from exc

        if amount <= 0:
            raise ValueError("Payment amount must be greater than zero")

        currency = currency.upper()

        zero_decimal_currencies = {
            "BIF",
            "CLP",
            "DJF",
            "GNF",
            "JPY",
            "KMF",
            "KRW",
            "MGA",
            "PYG",
            "RWF",
            "UGX",
            "VND",
            "VUV",
            "XAF",
            "XOF",
            "XPF",
        }

        if currency in zero_decimal_currencies:
            if amount != amount.to_integral_value():
                raise ValueError(
                    f"{currency} does not support fractional amounts"
                )

            return int(amount)

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

        return currency.strip().lower()

    @staticmethod
    def _normalize_email(email: str) -> str:
        if not email or not email.strip():
            raise ValueError("Customer email is required")

        return email.strip()

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
        if not reference or not reference.strip():
            raise ValueError("Payment reference is required")

        currency = self._normalize_currency(currency)
        customer_email = self._normalize_email(customer_email)

        amount_in_smallest_unit = self._to_smallest_unit(
            amount,
            currency,
        )

        payment_metadata = {
            "reference": reference.strip(),
        }

        if metadata:
            payment_metadata.update(
                {
                    str(key): str(value)
                    for key, value in metadata.items()
                }
            )

        params: dict[str, Any] = {
            "amount": amount_in_smallest_unit,
            "currency": currency,
            "automatic_payment_methods": {
                "enabled": True,
            },
            "receipt_email": customer_email,
            "metadata": payment_metadata,
        }

        # Stripe PaymentIntent does not use callback_url directly.
        # Preserve it as metadata so the application can retain it.
        if callback_url:
            params["metadata"]["callback_url"] = callback_url

        try:
            intent = stripe.PaymentIntent.create(**params)
        except stripe.StripeError as exc:
            raise RuntimeError(
                f"Stripe payment initialization failed: {exc}"
            ) from exc

        return {
            "provider": "stripe",
            "reference": reference.strip(),
            "transaction_id": intent.id,
            "status": intent.status,
            "amount": amount,
            "currency": currency.upper(),
            "client_secret": intent.client_secret,
        }

    def verify_payment(
        self,
        *,
        reference: str,
    ) -> dict[str, Any]:
        if not reference or not reference.strip():
            raise ValueError("Payment reference is required")

        try:
            intent = stripe.PaymentIntent.retrieve(
                reference.strip()
            )
        except stripe.StripeError as exc:
            raise RuntimeError(
                f"Stripe payment verification failed: {exc}"
            ) from exc

        return {
            "provider": "stripe",
            "reference": reference.strip(),
            "transaction_id": intent.id,
            "status": intent.status,
            "amount": intent.amount,
            "currency": intent.currency.upper(),
            "paid": intent.status == "succeeded",
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

        if not self.webhook_secret:
            raise ValueError(
                "Stripe webhook secret is not configured"
            )

        webhook_signature = signature

        if not webhook_signature and headers:
            webhook_signature = headers.get("Stripe-Signature")

        if not webhook_signature:
            raise ValueError(
                "Stripe webhook signature is required"
            )

        try:
            event = stripe.Webhook.construct_event(
                payload,
                webhook_signature,
                self.webhook_secret,
            )
        except ValueError as exc:
            raise ValueError(
                "Invalid Stripe webhook payload"
            ) from exc
        except stripe.SignatureVerificationError as exc:
            raise ValueError(
                "Invalid Stripe webhook signature"
            ) from exc

        event_type = event["type"]
        event_object = event["data"]["object"]

        normalized: dict[str, Any] = {
            "provider": "stripe",
            "event_id": event["id"],
            "event_type": event_type,
            "livemode": event.get("livemode", False),
            "transaction_id": event_object.get("id"),
        }

        metadata = event_object.get("metadata") or {}
        normalized["reference"] = metadata.get("reference")

        if event_type == "payment_intent.succeeded":
            normalized.update(
                {
                    "status": "successful",
                    "amount": event_object.get("amount"),
                    "currency": (
                        event_object.get("currency") or ""
                    ).upper(),
                }
            )

        elif event_type == "payment_intent.payment_failed":
            last_error = event_object.get(
                "last_payment_error"
            ) or {}

            normalized.update(
                {
                    "status": "failed",
                    "amount": event_object.get("amount"),
                    "currency": (
                        event_object.get("currency") or ""
                    ).upper(),
                    "failure_reason": (
                        last_error.get("message")
                        or "Stripe payment failed"
                    ),
                }
            )

        else:
            normalized["status"] = event_object.get("status")

        return normalized