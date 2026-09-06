from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums.billing_enums import (
    InvoiceStatus,
    PaymentGateway,
    PaymentMethod,
    PaymentStatus,
)


# ============================================================================
# Invoice Item Schemas
# ============================================================================


class InvoiceItemRequest(BaseModel):
    """
    Data required to add an item to an invoice.
    """

    description: str = Field(
        ...,
        min_length=1,
        max_length=255,
    )

    quantity: int = Field(
        default=1,
        ge=1,
    )

    unit_price: Decimal = Field(
        ...,
        ge=0,
    )

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "Description cannot be empty"
            )

        return value


class InvoiceItemResponse(BaseModel):
    """
    Invoice item returned by the API.
    """

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    invoice_id: int
    description: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal


# ============================================================================
# Invoice Schemas
# ============================================================================


class CreateInvoiceRequest(BaseModel):
    """
    Data required to create an invoice.

    clinic_id is intentionally excluded.

    The clinic is derived from the authenticated user's
    clinic assignment.
    """

    patient_id: int = Field(
        ...,
        gt=0,
    )

    appointment_id: int | None = Field(
        default=None,
        gt=0,
    )

    due_date: date | None = None

    is_insurance_claim: bool = False

    insurance_provider: str | None = Field(
        default=None,
        max_length=120,
    )

    items: list[InvoiceItemRequest] = Field(
        ...,
        min_length=1,
    )

    @field_validator("insurance_provider")
    @classmethod
    def validate_insurance_provider(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None

    @field_validator("items")
    @classmethod
    def validate_items(
        cls,
        value: list[InvoiceItemRequest],
    ) -> list[InvoiceItemRequest]:
        if not value:
            raise ValueError(
                "At least one invoice item is required"
            )

        return value


class InvoiceResponse(BaseModel):
    """
    Complete invoice representation returned by the API.
    """

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    clinic_id: int
    patient_id: int
    appointment_id: int | None

    invoice_number: str

    total_amount: Decimal
    amount_paid: Decimal

    status: InvoiceStatus

    due_date: date | None

    is_insurance_claim: bool
    insurance_provider: str | None

    created_at: datetime
    updated_at: datetime

    items: list[InvoiceItemResponse] = Field(
        default_factory=list
    )


class OutstandingInvoiceResponse(BaseModel):
    """
    Invoice representation used when returning
    outstanding invoices.
    """

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    clinic_id: int
    patient_id: int
    appointment_id: int | None

    invoice_number: str

    total_amount: Decimal
    amount_paid: Decimal

    status: InvoiceStatus

    due_date: date | None

    is_insurance_claim: bool
    insurance_provider: str | None

    created_at: datetime
    updated_at: datetime


# ============================================================================
# Payment Schemas
# ============================================================================


class RecordPaymentRequest(BaseModel):
    """
    Data required to record a successful payment.

    clinic_id is intentionally excluded.

    The invoice's clinic is derived from the authenticated
    user's clinic assignment.
    """

    invoice_id: int = Field(
        ...,
        gt=0,
    )

    amount: Decimal = Field(
        ...,
        gt=0,
    )

    method: PaymentMethod

    gateway: PaymentGateway | None = None

    reference: str | None = Field(
        default=None,
        max_length=120,
    )

    gateway_transaction_id: str | None = Field(
        default=None,
        max_length=255,
    )

    @field_validator(
        "reference",
        "gateway_transaction_id",
    )
    @classmethod
    def normalize_optional_strings(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None


class PaymentResponse(BaseModel):
    """
    Payment representation returned by the API.
    """

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    invoice_id: int

    amount: Decimal

    method: PaymentMethod
    status: PaymentStatus

    gateway: PaymentGateway | None

    reference: str | None
    gateway_transaction_id: str | None

    failure_reason: str | None

    created_at: datetime
    updated_at: datetime
    paid_at: datetime | None