from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.audit.models.audit_model import AuditLog
from app.core.enums.audit_enums import AuditAction
from app.core.enums.billing_enums import (
    InvoiceStatus,
    PaymentGateway,
    PaymentMethod,
    PaymentStatus,
)
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.billing.models.billing_model import (
    Invoice,
    InvoiceItem,
    Payment,
)
from app.modules.billing.services.billing_service import (
    _calculate_invoice_status,
    _generate_invoice_number,
    _get_invoice,
    _normalize_payment_gateway,
    _normalize_payment_method,
    _to_decimal,
    _validate_gateway_method,
    create_invoice,
    get_outstanding_invoices,
    mark_overdue_invoices,
    record_payment,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_invoice_directly(
    db,
    clinic,
    patient,
    *,
    total_amount=Decimal("10000.00"),
    amount_paid=Decimal("0.00"),
    status=InvoiceStatus.ISSUED,
    due_date=None,
    appointment_id=None,
    is_insurance_claim=False,
    insurance_provider=None,
    invoice_number=None,
):
    invoice = Invoice(
        clinic_id=clinic.id,
        patient_id=patient.id,
        appointment_id=appointment_id,
        invoice_number=invoice_number
        or f"TEST-{clinic.id}-{patient.id}-{id(object())}",
        total_amount=total_amount,
        amount_paid=amount_paid,
        status=status,
        due_date=due_date,
        is_insurance_claim=is_insurance_claim,
        insurance_provider=insurance_provider,
    )

    db.session.add(invoice)
    db.session.commit()

    return invoice


# ===========================================================================
# Private helper tests
# ===========================================================================


class TestToDecimal:

    def test_converts_valid_integer(self):
        assert _to_decimal(5000) == Decimal("5000")

    def test_converts_valid_string(self):
        assert _to_decimal("5000.50") == Decimal("5000.50")

    def test_accepts_decimal(self):
        value = Decimal("2500.75")

        assert _to_decimal(value) == value

    def test_rejects_negative_value(self):
        with pytest.raises(
            ValidationError,
            match="amount cannot be negative",
        ):
            _to_decimal("-10")

    def test_rejects_invalid_value(self):
        with pytest.raises(
            ValidationError,
            match="Invalid amount",
        ):
            _to_decimal("not-a-number")

    def test_uses_custom_field_name_in_error(self):
        with pytest.raises(
            ValidationError,
            match="Invalid unit price",
        ):
            _to_decimal("invalid", "unit price")


class TestGetInvoice:

    def test_returns_existing_invoice(self, db, clinic, patient):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
        )

        result = _get_invoice(invoice.id)

        assert result.id == invoice.id

    def test_raises_not_found_for_missing_invoice(self):
        with pytest.raises(
            NotFoundError,
            match="Invoice 999999 not found",
        ):
            _get_invoice(999999)


class TestPaymentNormalization:

    def test_accepts_payment_method_enum(self):
        result = _normalize_payment_method(PaymentMethod.CASH)

        assert result is PaymentMethod.CASH

    def test_converts_payment_method_string(self):
        result = _normalize_payment_method("cash")

        assert result is PaymentMethod.CASH

    def test_rejects_invalid_payment_method(self):
        with pytest.raises(
            ValidationError,
            match="Invalid payment method",
        ):
            _normalize_payment_method("bitcoin")

    def test_accepts_none_gateway(self):
        assert _normalize_payment_gateway(None) is None

    def test_accepts_gateway_enum(self):
        result = _normalize_payment_gateway(
            PaymentGateway.PAYSTACK
        )

        assert result is PaymentGateway.PAYSTACK

    def test_converts_gateway_string(self):
        result = _normalize_payment_gateway("paystack")

        assert result is PaymentGateway.PAYSTACK

    def test_rejects_invalid_gateway(self):
        with pytest.raises(
            ValidationError,
            match="Invalid payment gateway",
        ):
            _normalize_payment_gateway("paypal")


class TestGatewayMethodValidation:

    @pytest.mark.parametrize(
        "method",
        [
            PaymentMethod.CARD,
            PaymentMethod.BANK_TRANSFER,
            PaymentMethod.MOBILE_MONEY,
        ],
    )
    def test_allows_electronic_methods_with_gateway(self, method):
        _validate_gateway_method(
            method,
            PaymentGateway.PAYSTACK,
        )

    @pytest.mark.parametrize(
        "method",
        [
            PaymentMethod.CASH,
            PaymentMethod.INSURANCE,
        ],
    )
    def test_rejects_manual_methods_with_gateway(self, method):
        with pytest.raises(
            ValidationError,
            match="Payment gateway cannot be used",
        ):
            _validate_gateway_method(
                method,
                PaymentGateway.PAYSTACK,
            )

    def test_allows_cash_without_gateway(self):
        _validate_gateway_method(
            PaymentMethod.CASH,
            None,
        )

    def test_allows_insurance_without_gateway(self):
        _validate_gateway_method(
            PaymentMethod.INSURANCE,
            None,
        )


class TestInvoiceNumber:

    def test_generates_expected_format(self):
        invoice_number = _generate_invoice_number(42)

        parts = invoice_number.split("-")

        assert parts[0] == "INV"
        assert parts[1] == "42"
        assert parts[2] == date.today().strftime("%Y%m%d")
        assert len(parts[3]) == 8
        assert parts[3].isalnum()
        assert parts[3] == parts[3].upper()

    def test_generates_unique_numbers(self):
        first = _generate_invoice_number(1)
        second = _generate_invoice_number(1)

        assert first != second


class TestCalculateInvoiceStatus:

    def test_returns_paid_when_fully_paid(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            total_amount=Decimal("10000"),
            amount_paid=Decimal("10000"),
        )

        assert (
            _calculate_invoice_status(invoice)
            == InvoiceStatus.PAID
        )

    def test_returns_paid_when_overpaid(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            total_amount=Decimal("10000"),
            amount_paid=Decimal("11000"),
        )

        assert (
            _calculate_invoice_status(invoice)
            == InvoiceStatus.PAID
        )

    def test_returns_partially_paid(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            total_amount=Decimal("10000"),
            amount_paid=Decimal("5000"),
        )

        assert (
            _calculate_invoice_status(invoice)
            == InvoiceStatus.PARTIALLY_PAID
        )

    def test_returns_issued_when_unpaid(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            total_amount=Decimal("10000"),
            amount_paid=Decimal("0"),
        )

        assert (
            _calculate_invoice_status(invoice)
            == InvoiceStatus.ISSUED
        )


# ===========================================================================
# create_invoice
# ===========================================================================


class TestCreateInvoice:

    def test_creates_invoice_successfully(
        self,
        db,
        clinic,
        patient,
    ):
        due_date = date.today() + timedelta(days=7)

        invoice = create_invoice(
            clinic_id=clinic.id,
            patient_id=patient.id,
            due_date=due_date,
            items=[
                {
                    "description": "Consultation",
                    "quantity": 1,
                    "unit_price": Decimal("5000.00"),
                }
            ],
        )

        assert invoice.id is not None
        assert invoice.clinic_id == clinic.id
        assert invoice.patient_id == patient.id
        assert invoice.due_date == due_date
        assert invoice.status == InvoiceStatus.ISSUED
        assert invoice.amount_paid == Decimal("0")
        assert invoice.total_amount == Decimal("5000.00")

    def test_generates_invoice_number(
        self,
        clinic,
        patient,
    ):
        invoice = create_invoice(
            clinic_id=clinic.id,
            patient_id=patient.id,
            items=[
                {
                    "description": "Consultation",
                    "quantity": 1,
                    "unit_price": Decimal("5000"),
                }
            ],
        )

        assert invoice.invoice_number.startswith(
            f"INV-{clinic.id}-"
        )

    def test_creates_invoice_items(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice(
            clinic_id=clinic.id,
            patient_id=patient.id,
            items=[
                {
                    "description": "Consultation",
                    "quantity": 2,
                    "unit_price": Decimal("5000"),
                },
                {
                    "description": "Laboratory",
                    "quantity": 3,
                    "unit_price": Decimal("1500"),
                },
            ],
        )

        items = (
            InvoiceItem.query
            .filter_by(invoice_id=invoice.id)
            .order_by(InvoiceItem.id)
            .all()
        )

        assert len(items) == 2

        assert items[0].description == "Consultation"
        assert items[0].quantity == 2
        assert items[0].unit_price == Decimal("5000")
        assert items[0].subtotal == Decimal("10000")

        assert items[1].description == "Laboratory"
        assert items[1].quantity == 3
        assert items[1].unit_price == Decimal("1500")
        assert items[1].subtotal == Decimal("4500")

    def test_calculates_total_for_multiple_items(
        self,
        clinic,
        patient,
    ):
        invoice = create_invoice(
            clinic_id=clinic.id,
            patient_id=patient.id,
            items=[
                {
                    "description": "Consultation",
                    "quantity": 2,
                    "unit_price": Decimal("5000"),
                },
                {
                    "description": "Medication",
                    "quantity": 3,
                    "unit_price": Decimal("1000"),
                },
            ],
        )

        assert invoice.total_amount == Decimal("13000")

    def test_defaults_quantity_to_one(
        self,
        clinic,
        patient,
    ):
        invoice = create_invoice(
            clinic_id=clinic.id,
            patient_id=patient.id,
            items=[
                {
                    "description": "Consultation",
                    "unit_price": Decimal("5000"),
                }
            ],
        )

        assert invoice.items[0].quantity == 1
        assert invoice.items[0].subtotal == Decimal("5000")

    def test_supports_appointment(
        self,
        clinic,
        patient,
    ):
        invoice = create_invoice(
            clinic_id=clinic.id,
            patient_id=patient.id,
            appointment_id=123,
            items=[
                {
                    "description": "Consultation",
                    "quantity": 1,
                    "unit_price": Decimal("5000"),
                }
            ],
        )

        assert invoice.appointment_id == 123

    def test_supports_insurance_claim(
        self,
        clinic,
        patient,
    ):
        invoice = create_invoice(
            clinic_id=clinic.id,
            patient_id=patient.id,
            is_insurance_claim=True,
            insurance_provider="Test Health Insurance",
            items=[
                {
                    "description": "Consultation",
                    "quantity": 1,
                    "unit_price": Decimal("5000"),
                }
            ],
        )

        assert invoice.is_insurance_claim is True
        assert (
            invoice.insurance_provider
            == "Test Health Insurance"
        )

    def test_creates_audit_log(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice(
            clinic_id=clinic.id,
            patient_id=patient.id,
            items=[
                {
                    "description": "Consultation",
                    "quantity": 1,
                    "unit_price": Decimal("5000"),
                }
            ],
        )

        audit = AuditLog.query.filter_by(
            entity_type="Invoice",
            entity_id=invoice.id,
            action=AuditAction.CREATE,
        ).first()

        assert audit is not None
        assert "created for patient" in audit.description
        assert audit.new_value["total_amount"] == "5000"
        assert audit.new_value["amount_paid"] == "0"
        assert (
            audit.new_value["status"]
            == InvoiceStatus.ISSUED.value
        )

    @pytest.mark.parametrize(
        "clinic_id",
        [None, 0],
    )
    def test_rejects_missing_clinic_id(
        self,
        clinic,
        patient,
        clinic_id,
    ):
        with pytest.raises(
            ValidationError,
            match="Clinic ID is required",
        ):
            create_invoice(
                clinic_id=clinic_id,
                patient_id=patient.id,
                items=[
                    {
                        "description": "Consultation",
                        "quantity": 1,
                        "unit_price": Decimal("5000"),
                    }
                ],
            )

    @pytest.mark.parametrize(
        "patient_id",
        [None, 0],
    )
    def test_rejects_missing_patient_id(
        self,
        clinic,
        patient,
        patient_id,
    ):
        with pytest.raises(
            ValidationError,
            match="Patient ID is required",
        ):
            create_invoice(
                clinic_id=clinic.id,
                patient_id=patient_id,
                items=[
                    {
                        "description": "Consultation",
                        "quantity": 1,
                        "unit_price": Decimal("5000"),
                    }
                ],
            )

    def test_rejects_empty_items(
        self,
        clinic,
        patient,
    ):
        with pytest.raises(
            ValidationError,
            match="at least one item",
        ):
            create_invoice(
                clinic_id=clinic.id,
                patient_id=patient.id,
                items=[],
            )

    def test_rejects_missing_description(
        self,
        clinic,
        patient,
    ):
        with pytest.raises(
            ValidationError,
            match="requires a description",
        ):
            create_invoice(
                clinic_id=clinic.id,
                patient_id=patient.id,
                items=[
                    {
                        "quantity": 1,
                        "unit_price": Decimal("5000"),
                    }
                ],
            )

    def test_rejects_blank_description(
        self,
        clinic,
        patient,
    ):
        with pytest.raises(
            ValidationError,
            match="requires a description",
        ):
            create_invoice(
                clinic_id=clinic.id,
                patient_id=patient.id,
                items=[
                    {
                        "description": "",
                        "quantity": 1,
                        "unit_price": Decimal("5000"),
                    }
                ],
            )

    @pytest.mark.parametrize(
        "quantity",
        [0, -1, 1.5, "2", None],
    )
    def test_rejects_invalid_quantity(
        self,
        clinic,
        patient,
        quantity,
    ):
        with pytest.raises(
            ValidationError,
            match="positive integer",
        ):
            create_invoice(
                clinic_id=clinic.id,
                patient_id=patient.id,
                items=[
                    {
                        "description": "Consultation",
                        "quantity": quantity,
                        "unit_price": Decimal("5000"),
                    }
                ],
            )

    @pytest.mark.parametrize(
        "unit_price",
        [
            Decimal("-1"),
            "-10",
            "invalid",
            None,
        ],
    )
    def test_rejects_invalid_unit_price(
        self,
        clinic,
        patient,
        unit_price,
    ):
        with pytest.raises(ValidationError):
            create_invoice(
                clinic_id=clinic.id,
                patient_id=patient.id,
                items=[
                    {
                        "description": "Consultation",
                        "quantity": 1,
                        "unit_price": unit_price,
                    }
                ],
            )

    def test_rejects_insurance_claim_without_provider(
        self,
        clinic,
        patient,
    ):
        with pytest.raises(
            ValidationError,
            match="Insurance provider is required",
        ):
            create_invoice(
                clinic_id=clinic.id,
                patient_id=patient.id,
                is_insurance_claim=True,
                items=[
                    {
                        "description": "Consultation",
                        "quantity": 1,
                        "unit_price": Decimal("5000"),
                    }
                ],
            )

    def test_does_not_persist_invoice_when_item_validation_fails(
        self,
        db,
        clinic,
        patient,
    ):
        with pytest.raises(ValidationError):
            create_invoice(
                clinic_id=clinic.id,
                patient_id=patient.id,
                items=[
                    {
                        "description": "Valid item",
                        "quantity": 1,
                        "unit_price": Decimal("5000"),
                    },
                    {
                        "description": "",
                        "quantity": 1,
                        "unit_price": Decimal("1000"),
                    },
                ],
            )

        db.session.rollback()

        assert Invoice.query.count() == 0
        assert InvoiceItem.query.count() == 0


# ===========================================================================
# record_payment
# ===========================================================================


class TestRecordPayment:

    def test_records_cash_payment(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            total_amount=Decimal("10000"),
        )

        payment = record_payment(
            invoice_id=invoice.id,
            amount=Decimal("2000"),
            method=PaymentMethod.CASH,
        )

        db.session.refresh(invoice)

        assert payment.id is not None
        assert payment.invoice_id == invoice.id
        assert payment.amount == Decimal("2000")
        assert payment.method == PaymentMethod.CASH
        assert payment.status == PaymentStatus.SUCCESSFUL
        assert payment.gateway is None
        assert payment.paid_at is not None
        assert invoice.amount_paid == Decimal("2000")
        assert (
            invoice.status
            == InvoiceStatus.PARTIALLY_PAID
        )

    def test_records_full_payment(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            total_amount=Decimal("5000"),
        )

        payment = record_payment(
            invoice_id=invoice.id,
            amount=Decimal("5000"),
            method=PaymentMethod.CASH,
        )

        db.session.refresh(invoice)

        assert payment.status == PaymentStatus.SUCCESSFUL
        assert invoice.amount_paid == Decimal("5000")
        assert invoice.status == InvoiceStatus.PAID

    def test_records_card_gateway_payment(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            total_amount=Decimal("10000"),
        )

        payment = record_payment(
            invoice_id=invoice.id,
            amount=Decimal("5000"),
            method=PaymentMethod.CARD,
            gateway=PaymentGateway.PAYSTACK,
            gateway_transaction_id="TXN-12345",
            reference="REF-12345",
        )

        assert payment.method == PaymentMethod.CARD
        assert payment.gateway == PaymentGateway.PAYSTACK
        assert (
            payment.gateway_transaction_id
            == "TXN-12345"
        )
        assert payment.reference == "REF-12345"

    @pytest.mark.parametrize(
        "method",
        [
            PaymentMethod.CARD,
            PaymentMethod.BANK_TRANSFER,
            PaymentMethod.MOBILE_MONEY,
        ],
    )
    def test_supports_all_electronic_payment_methods(
        self,
        db,
        clinic,
        patient,
        method,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            total_amount=Decimal("10000"),
        )

        payment = record_payment(
            invoice.id,
            Decimal("1000"),
            method,
            gateway=PaymentGateway.PAYSTACK,
            gateway_transaction_id="TXN-123",
        )

        assert payment.method == method

    def test_accepts_payment_method_string(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            total_amount=Decimal("5000"),
        )

        payment = record_payment(
            invoice.id,
            amount="1000",
            method="cash",
        )

        assert payment.method == PaymentMethod.CASH

    def test_accepts_gateway_string(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            total_amount=Decimal("5000"),
        )

        payment = record_payment(
            invoice.id,
            amount="1000",
            method="card",
            gateway="paystack",
            gateway_transaction_id="TXN-123",
        )

        assert payment.gateway == PaymentGateway.PAYSTACK

    def test_updates_amount_for_multiple_payments(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            total_amount=Decimal("10000"),
        )

        record_payment(
            invoice.id,
            Decimal("2000"),
            PaymentMethod.CASH,
        )

        record_payment(
            invoice.id,
            Decimal("3000"),
            PaymentMethod.CASH,
        )

        db.session.refresh(invoice)

        assert invoice.amount_paid == Decimal("5000")
        assert (
            invoice.status
            == InvoiceStatus.PARTIALLY_PAID
        )

    def test_creates_payment_audit_log(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            total_amount=Decimal("5000"),
        )

        payment = record_payment(
            invoice.id,
            Decimal("2000"),
            PaymentMethod.CASH,
        )

        audit = AuditLog.query.filter_by(
            entity_type="Invoice",
            entity_id=invoice.id,
            action=AuditAction.PAYMENT,
        ).first()

        assert audit is not None
        assert payment.id is not None
        assert (
            "Payment of 2000 recorded via cash"
            in audit.description
        )
        assert (
            audit.old_value["status"]
            == InvoiceStatus.ISSUED.value
        )

        # SQLAlchemy Numeric(10, 2) persists monetary values
        # with two decimal places.
        assert audit.old_value["amount_paid"] == "0.00"
        assert audit.new_value["amount_paid"] == "2000.00"

        assert (
            audit.new_value["status"]
            == InvoiceStatus.PARTIALLY_PAID.value
        )
        assert (
            audit.new_value["payment_method"]
            == PaymentMethod.CASH.value
        )
        assert audit.new_value["payment_gateway"] is None

    def test_rejects_missing_invoice(self):
        with pytest.raises(
            NotFoundError,
            match="Invoice 999999 not found",
        ):
            record_payment(
                invoice_id=999999,
                amount=Decimal("100"),
                method=PaymentMethod.CASH,
            )

    def test_rejects_cancelled_invoice(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            status=InvoiceStatus.CANCELLED,
        )

        with pytest.raises(
            ConflictError,
            match="Cannot record payment for cancelled invoice",
        ):
            record_payment(
                invoice.id,
                Decimal("100"),
                PaymentMethod.CASH,
            )

    def test_rejects_already_paid_invoice(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            total_amount=Decimal("5000"),
            amount_paid=Decimal("5000"),
            status=InvoiceStatus.PAID,
        )

        with pytest.raises(
            ConflictError,
            match="already fully paid",
        ):
            record_payment(
                invoice.id,
                Decimal("100"),
                PaymentMethod.CASH,
            )

    @pytest.mark.parametrize(
        "amount, expected_message",
        [
            (
                Decimal("0"),
                "Payment amount must be greater than zero",
            ),
            (
                Decimal("-1"),
                "amount cannot be negative",
            ),
        ],
    )
    def test_rejects_non_positive_amount(
        self,
        db,
        clinic,
        patient,
        amount,
        expected_message,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            total_amount=Decimal("5000"),
        )

        with pytest.raises(
            ValidationError,
            match=expected_message,
        ):
            record_payment(
                invoice.id,
                amount,
                PaymentMethod.CASH,
            )

    def test_rejects_invalid_amount(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            total_amount=Decimal("5000"),
        )

        with pytest.raises(
            ValidationError,
            match="Invalid amount",
        ):
            record_payment(
                invoice.id,
                "invalid",
                PaymentMethod.CASH,
            )

    def test_rejects_invalid_payment_method(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            total_amount=Decimal("5000"),
        )

        with pytest.raises(
            ValidationError,
            match="Invalid payment method",
        ):
            record_payment(
                invoice.id,
                Decimal("100"),
                "bitcoin",
            )

    def test_rejects_invalid_gateway(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            total_amount=Decimal("5000"),
        )

        with pytest.raises(
            ValidationError,
            match="Invalid payment gateway",
        ):
            record_payment(
                invoice.id,
                Decimal("100"),
                PaymentMethod.CARD,
                gateway="paypal",
            )

    @pytest.mark.parametrize(
        "method",
        [
            PaymentMethod.CASH,
            PaymentMethod.INSURANCE,
        ],
    )
    def test_rejects_gateway_for_non_electronic_method(
        self,
        db,
        clinic,
        patient,
        method,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            total_amount=Decimal("5000"),
        )

        with pytest.raises(
            ValidationError,
            match="Payment gateway cannot be used",
        ):
            record_payment(
                invoice.id,
                Decimal("100"),
                method,
                gateway=PaymentGateway.PAYSTACK,
            )

    def test_rejects_gateway_without_transaction_id(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            total_amount=Decimal("5000"),
        )

        with pytest.raises(
            ValidationError,
            match="Gateway transaction ID is required",
        ):
            record_payment(
                invoice.id,
                Decimal("100"),
                PaymentMethod.CARD,
                gateway=PaymentGateway.PAYSTACK,
            )

    def test_rejects_overpayment(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            total_amount=Decimal("5000"),
            amount_paid=Decimal("4000"),
            status=InvoiceStatus.PARTIALLY_PAID,
        )

        with pytest.raises(
            ValidationError,
            match="exceeds the remaining invoice balance",
        ):
            record_payment(
                invoice.id,
                Decimal("1001"),
                PaymentMethod.CASH,
            )

    def test_allows_payment_equal_to_remaining_balance(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            total_amount=Decimal("5000"),
            amount_paid=Decimal("4000"),
            status=InvoiceStatus.PARTIALLY_PAID,
        )

        record_payment(
            invoice.id,
            Decimal("1000"),
            PaymentMethod.CASH,
        )

        db.session.refresh(invoice)

        assert invoice.amount_paid == Decimal("5000")
        assert invoice.status == InvoiceStatus.PAID

    def test_records_reference(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            total_amount=Decimal("5000"),
        )

        payment = record_payment(
            invoice.id,
            Decimal("1000"),
            PaymentMethod.CASH,
            reference="CASH-REF-001",
        )

        assert payment.reference == "CASH-REF-001"


# ===========================================================================
# get_outstanding_invoices
# ===========================================================================


class TestGetOutstandingInvoices:

    def test_returns_issued_invoices(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            status=InvoiceStatus.ISSUED,
        )

        result = get_outstanding_invoices()

        assert invoice in result

    def test_returns_partially_paid_invoices(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            status=InvoiceStatus.PARTIALLY_PAID,
            amount_paid=Decimal("2000"),
        )

        result = get_outstanding_invoices()

        assert invoice in result

    def test_returns_overdue_invoices(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            status=InvoiceStatus.OVERDUE,
        )

        result = get_outstanding_invoices()

        assert invoice in result

    @pytest.mark.parametrize(
        "status",
        [
            InvoiceStatus.DRAFT,
            InvoiceStatus.PAID,
            InvoiceStatus.CANCELLED,
        ],
    )
    def test_excludes_non_outstanding_statuses(
        self,
        db,
        clinic,
        patient,
        status,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            status=status,
        )

        result = get_outstanding_invoices()

        assert invoice not in result

    def test_filters_by_clinic(
        self,
        db,
        clinic,
        patient,
        make_clinic,
        make_patient,
    ):
        other_clinic = make_clinic(
            name="Other Clinic"
        )
        other_patient = make_patient(other_clinic)

        current_invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            status=InvoiceStatus.ISSUED,
        )

        other_invoice = create_invoice_directly(
            db,
            other_clinic,
            other_patient,
            status=InvoiceStatus.ISSUED,
        )

        result = get_outstanding_invoices(
            clinic_id=clinic.id,
        )

        assert current_invoice in result
        assert other_invoice not in result

    def test_orders_by_due_date(
        self,
        db,
        clinic,
        patient,
    ):
        later = create_invoice_directly(
            db,
            clinic,
            patient,
            invoice_number="ORDER-LATER",
            due_date=date.today() + timedelta(days=10),
        )

        earlier = create_invoice_directly(
            db,
            clinic,
            patient,
            invoice_number="ORDER-EARLIER",
            due_date=date.today() + timedelta(days=2),
        )

        result = get_outstanding_invoices()

        assert result.index(earlier) < result.index(later)


# ===========================================================================
# mark_overdue_invoices
# ===========================================================================


class TestMarkOverdueInvoices:

    def test_marks_expired_issued_invoice_overdue(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            status=InvoiceStatus.ISSUED,
            due_date=date.today() - timedelta(days=1),
        )

        result = mark_overdue_invoices()

        db.session.refresh(invoice)

        assert result == 1
        assert invoice.status == InvoiceStatus.OVERDUE

    def test_marks_expired_partially_paid_invoice_overdue(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            status=InvoiceStatus.PARTIALLY_PAID,
            amount_paid=Decimal("2000"),
            due_date=date.today() - timedelta(days=1),
        )

        result = mark_overdue_invoices()

        db.session.refresh(invoice)

        assert result == 1
        assert invoice.status == InvoiceStatus.OVERDUE

    def test_does_not_mark_future_invoice(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            status=InvoiceStatus.ISSUED,
            due_date=date.today() + timedelta(days=1),
        )

        result = mark_overdue_invoices()

        db.session.refresh(invoice)

        assert result == 0
        assert invoice.status == InvoiceStatus.ISSUED

    @pytest.mark.parametrize(
        "status",
        [
            InvoiceStatus.PAID,
            InvoiceStatus.CANCELLED,
            InvoiceStatus.DRAFT,
        ],
    )
    def test_does_not_mark_ineligible_statuses(
        self,
        db,
        clinic,
        patient,
        status,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            status=status,
            due_date=date.today() - timedelta(days=1),
        )

        result = mark_overdue_invoices()

        db.session.refresh(invoice)

        assert result == 0
        assert invoice.status == status

    def test_ignores_invoice_without_due_date(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            status=InvoiceStatus.ISSUED,
            due_date=None,
        )

        result = mark_overdue_invoices()

        db.session.refresh(invoice)

        assert result == 0
        assert invoice.status == InvoiceStatus.ISSUED

    def test_marks_multiple_invoices_and_returns_count(
        self,
        db,
        clinic,
        patient,
    ):
        first = create_invoice_directly(
            db,
            clinic,
            patient,
            invoice_number="OVERDUE-1",
            due_date=date.today() - timedelta(days=3),
        )

        second = create_invoice_directly(
            db,
            clinic,
            patient,
            invoice_number="OVERDUE-2",
            status=InvoiceStatus.PARTIALLY_PAID,
            amount_paid=Decimal("1000"),
            due_date=date.today() - timedelta(days=2),
        )

        future = create_invoice_directly(
            db,
            clinic,
            patient,
            invoice_number="FUTURE-1",
            due_date=date.today() + timedelta(days=3),
        )

        result = mark_overdue_invoices()

        db.session.refresh(first)
        db.session.refresh(second)
        db.session.refresh(future)

        assert result == 2
        assert first.status == InvoiceStatus.OVERDUE
        assert second.status == InvoiceStatus.OVERDUE
        assert future.status == InvoiceStatus.ISSUED

    def test_creates_status_change_audit_log(
        self,
        db,
        clinic,
        patient,
    ):
        invoice = create_invoice_directly(
            db,
            clinic,
            patient,
            due_date=date.today() - timedelta(days=1),
        )

        mark_overdue_invoices()

        audit = AuditLog.query.filter_by(
            entity_type="Invoice",
            entity_id=invoice.id,
            action=AuditAction.STATUS_CHANGE,
        ).first()

        assert audit is not None
        assert (
            audit.description
            == "Invoice marked overdue (automated)"
        )
        assert (
            audit.old_value["status"]
            == InvoiceStatus.ISSUED.value
        )
        assert (
            audit.new_value["status"]
            == InvoiceStatus.OVERDUE.value
        )

    def test_returns_zero_when_nothing_is_overdue(
        self,
        db,
        clinic,
        patient,
    ):
        create_invoice_directly(
            db,
            clinic,
            patient,
            due_date=date.today() + timedelta(days=5),
        )

        assert mark_overdue_invoices() == 0