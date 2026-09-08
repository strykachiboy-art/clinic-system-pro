from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.enums.billing_enums import (
    InvoiceStatus,
    PaymentGateway,
    PaymentMethod,
    PaymentStatus,
)
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.billing.models.billing_model import (
    Invoice,
    InvoiceItem,
)
from app.modules.billing.services import billing_service


# ============================================================================
# Utility Helpers
# ============================================================================


class FakeQuery:
    def __init__(self, result=None, results=None):
        self.result = result
        self.results = results or []

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def first(self):
        return self.result

    def all(self):
        return self.results


# ============================================================================
# _validate_positive_id
# ============================================================================


@pytest.mark.parametrize(
    "value",
    [
        0,
        -1,
        -100,
        True,
        False,
        1.5,
        "1",
        None,
    ],
)
def test_validate_positive_id_rejects_invalid_values(
    value,
):
    with pytest.raises(
        ValidationError,
        match="Clinic ID must be a positive integer",
    ):
        billing_service._validate_positive_id(
            value,
            "Clinic ID",
        )


@pytest.mark.parametrize(
    "value",
    [
        1,
        2,
        100,
        999999,
    ],
)
def test_validate_positive_id_accepts_positive_integers(
    value,
):
    assert (
        billing_service._validate_positive_id(
            value,
            "Clinic ID",
        )
        is None
    )


# ============================================================================
# _to_decimal
# ============================================================================


@pytest.mark.parametrize(
    "value,expected",
    [
        ("10", Decimal("10")),
        ("10.50", Decimal("10.50")),
        (10, Decimal("10")),
        (10.25, Decimal("10.25")),
        (Decimal("25.75"), Decimal("25.75")),
        ("0", Decimal("0")),
    ],
)
def test_to_decimal_converts_valid_values(
    value,
    expected,
):
    assert (
        billing_service._to_decimal(value)
        == expected
    )


@pytest.mark.parametrize(
    "value",
    [
        "-1",
        "-10.50",
        -1,
        Decimal("-5.00"),
    ],
)
def test_to_decimal_rejects_negative_values(
    value,
):
    with pytest.raises(
        ValidationError,
        match="amount cannot be negative",
    ):
        billing_service._to_decimal(value)


@pytest.mark.parametrize(
    "value",
    [
        "not-a-number",
        None,
        object(),
    ],
)
def test_to_decimal_rejects_invalid_values(
    value,
):
    with pytest.raises(
        ValidationError,
        match="Invalid amount",
    ):
        billing_service._to_decimal(value)


# ============================================================================
# _normalize_optional_string
# ============================================================================


def test_normalize_optional_string_returns_none_for_none():
    assert (
        billing_service._normalize_optional_string(
            None,
            "Reference",
        )
        is None
    )


def test_normalize_optional_string_strips_whitespace():
    assert (
        billing_service._normalize_optional_string(
            "  REF-123  ",
            "Reference",
        )
        == "REF-123"
    )


def test_normalize_optional_string_returns_none_for_blank():
    assert (
        billing_service._normalize_optional_string(
            "   ",
            "Reference",
        )
        is None
    )


def test_normalize_optional_string_rejects_non_string():
    with pytest.raises(
        ValidationError,
        match="Reference must be a string",
    ):
        billing_service._normalize_optional_string(
            123,
            "Reference",
        )


def test_normalize_optional_string_rejects_excessive_length():
    with pytest.raises(
        ValidationError,
        match="Reference cannot exceed 5 characters",
    ):
        billing_service._normalize_optional_string(
            "123456",
            "Reference",
            max_length=5,
        )


# ============================================================================
# _generate_invoice_number
# ============================================================================


def test_generate_invoice_number_format(
    monkeypatch,
):
    class FakeDate:
        @classmethod
        def today(cls):
            return date(2026, 9, 7)

    class FakeUUID:
        hex = "abcdef1234567890"

    monkeypatch.setattr(
        billing_service,
        "date",
        FakeDate,
    )

    monkeypatch.setattr(
        billing_service,
        "uuid4",
        lambda: FakeUUID(),
    )

    result = (
        billing_service._generate_invoice_number(
            42,
        )
    )

    assert (
        result
        == "INV-42-20260907-ABCDEF12"
    )


# ============================================================================
# _calculate_invoice_status
# ============================================================================


@pytest.mark.parametrize(
    "total,paid,expected",
    [
        (
            Decimal("100.00"),
            Decimal("0.00"),
            InvoiceStatus.ISSUED,
        ),
        (
            Decimal("100.00"),
            Decimal("25.00"),
            InvoiceStatus.PARTIALLY_PAID,
        ),
        (
            Decimal("100.00"),
            Decimal("100.00"),
            InvoiceStatus.PAID,
        ),
        (
            Decimal("100.00"),
            Decimal("125.00"),
            InvoiceStatus.PAID,
        ),
    ],
)
def test_calculate_invoice_status(
    total,
    paid,
    expected,
):
    invoice = SimpleNamespace(
        total_amount=total,
        amount_paid=paid,
    )

    assert (
        billing_service._calculate_invoice_status(
            invoice
        )
        == expected
    )


# ============================================================================
# _validate_invoice_items
# ============================================================================


def test_validate_invoice_items_success():
    result = (
        billing_service._validate_invoice_items(
            [
                {
                    "description": " Consultation ",
                    "quantity": 2,
                    "unit_price": "50.00",
                }
            ]
        )
    )

    assert result == [
        {
            "description": "Consultation",
            "quantity": 2,
            "unit_price": Decimal("50.00"),
        }
    ]


def test_validate_invoice_items_defaults_quantity():
    result = (
        billing_service._validate_invoice_items(
            [
                {
                    "description": "Consultation",
                    "unit_price": "100.00",
                }
            ]
        )
    )

    assert result == [
        {
            "description": "Consultation",
            "quantity": 1,
            "unit_price": Decimal("100.00"),
        }
    ]


def test_validate_invoice_items_requires_items():
    with pytest.raises(
        ValidationError,
        match="Invoice must contain at least one item",
    ):
        billing_service._validate_invoice_items([])


def test_validate_invoice_items_rejects_non_dict():
    with pytest.raises(
        ValidationError,
        match="Each invoice item must be an object",
    ):
        billing_service._validate_invoice_items(
            ["invalid"]
        )


def test_validate_invoice_items_requires_description():
    with pytest.raises(
        ValidationError,
        match="Each invoice item requires a description",
    ):
        billing_service._validate_invoice_items(
            [
                {
                    "quantity": 1,
                    "unit_price": "100",
                }
            ]
        )


def test_validate_invoice_items_rejects_blank_description():
    with pytest.raises(
        ValidationError,
        match="Each invoice item requires a description",
    ):
        billing_service._validate_invoice_items(
            [
                {
                    "description": "   ",
                    "quantity": 1,
                    "unit_price": "100",
                }
            ]
        )


def test_validate_invoice_items_rejects_long_description():
    with pytest.raises(
        ValidationError,
        match="Invoice item description cannot exceed 255 characters",
    ):
        billing_service._validate_invoice_items(
            [
                {
                    "description": "x" * 256,
                    "quantity": 1,
                    "unit_price": "100",
                }
            ]
        )


@pytest.mark.parametrize(
    "quantity",
    [
        0,
        -1,
        True,
        False,
        1.5,
        "2",
    ],
)
def test_validate_invoice_items_rejects_invalid_quantity(
    quantity,
):
    with pytest.raises(
        ValidationError,
        match="Invoice item quantity must be a positive integer",
    ):
        billing_service._validate_invoice_items(
            [
                {
                    "description": "Consultation",
                    "quantity": quantity,
                    "unit_price": "100",
                }
            ]
        )


# ============================================================================
# _get_invoice
# ============================================================================


def test_get_invoice_rejects_invalid_id():
    with pytest.raises(
        ValidationError,
        match="Invoice ID must be a positive integer",
    ):
        billing_service._get_invoice(0)


def test_get_invoice_returns_invoice(
    app,
    monkeypatch,
):
    invoice = SimpleNamespace(
        id=10,
        clinic_id=5,
    )

    monkeypatch.setattr(
        billing_service.Invoice,
        "query",
        FakeQuery(result=invoice),
    )

    with app.app_context():
        result = billing_service._get_invoice(10)

    assert result is invoice


def test_get_invoice_applies_clinic_filter(
    app,
    monkeypatch,
):
    invoice = SimpleNamespace(
        id=10,
        clinic_id=5,
    )

    query = FakeQuery(result=invoice)

    monkeypatch.setattr(
        billing_service.Invoice,
        "query",
        query,
    )

    with app.app_context():
        result = billing_service._get_invoice(
            10,
            clinic_id=5,
        )

    assert result is invoice


def test_get_invoice_raises_not_found(
    app,
    monkeypatch,
):
    monkeypatch.setattr(
        billing_service.Invoice,
        "query",
        FakeQuery(result=None),
    )

    with app.app_context():
        with pytest.raises(
            NotFoundError,
            match="Invoice 10 not found",
        ):
            billing_service._get_invoice(10)


# ============================================================================
# _validate_invoice_relationships
# ============================================================================


def test_validate_invoice_relationships_rejects_wrong_patient_clinic(
    monkeypatch,
):
    patient = SimpleNamespace(
        id=20,
        clinic_id=99,
    )

    monkeypatch.setattr(
        billing_service,
        "get_patient",
        lambda patient_id: patient,
    )

    with pytest.raises(
        ValidationError,
        match="Patient 20 does not belong to clinic 10",
    ):
        billing_service._validate_invoice_relationships(
            clinic_id=10,
            patient_id=20,
        )


def test_validate_invoice_relationships_returns_patient_without_appointment(
    monkeypatch,
):
    patient = SimpleNamespace(
        id=20,
        clinic_id=10,
    )

    monkeypatch.setattr(
        billing_service,
        "get_patient",
        lambda patient_id: patient,
    )

    result = (
        billing_service._validate_invoice_relationships(
            clinic_id=10,
            patient_id=20,
        )
    )

    assert result == (patient, None)


def test_validate_invoice_relationships_rejects_missing_appointment(
    app,
    monkeypatch,
):
    patient = SimpleNamespace(
        id=20,
        clinic_id=10,
    )

    monkeypatch.setattr(
        billing_service,
        "get_patient",
        lambda patient_id: patient,
    )

    monkeypatch.setattr(
        billing_service.db.session,
        "get",
        lambda model, object_id: None,
    )

    with app.app_context():
        with pytest.raises(
            NotFoundError,
            match="Appointment 30 not found",
        ):
            billing_service._validate_invoice_relationships(
                clinic_id=10,
                patient_id=20,
                appointment_id=30,
            )


def test_validate_invoice_relationships_rejects_wrong_appointment_clinic(
    app,
    monkeypatch,
):
    patient = SimpleNamespace(
        id=20,
        clinic_id=10,
    )

    appointment = SimpleNamespace(
        id=30,
        clinic_id=99,
        patient_id=20,
    )

    monkeypatch.setattr(
        billing_service,
        "get_patient",
        lambda patient_id: patient,
    )

    monkeypatch.setattr(
        billing_service.db.session,
        "get",
        lambda model, object_id: appointment,
    )

    with app.app_context():
        with pytest.raises(
            ValidationError,
            match="Appointment 30 does not belong to clinic 10",
        ):
            billing_service._validate_invoice_relationships(
                clinic_id=10,
                patient_id=20,
                appointment_id=30,
            )


def test_validate_invoice_relationships_rejects_wrong_appointment_patient(
    app,
    monkeypatch,
):
    patient = SimpleNamespace(
        id=20,
        clinic_id=10,
    )

    appointment = SimpleNamespace(
        id=30,
        clinic_id=10,
        patient_id=99,
    )

    monkeypatch.setattr(
        billing_service,
        "get_patient",
        lambda patient_id: patient,
    )

    monkeypatch.setattr(
        billing_service.db.session,
        "get",
        lambda model, object_id: appointment,
    )

    with app.app_context():
        with pytest.raises(
            ValidationError,
            match="Appointment does not belong to the specified patient",
        ):
            billing_service._validate_invoice_relationships(
                clinic_id=10,
                patient_id=20,
                appointment_id=30,
            )


def test_validate_invoice_relationships_success_with_appointment(
    app,
    monkeypatch,
):
    patient = SimpleNamespace(
        id=20,
        clinic_id=10,
    )

    appointment = SimpleNamespace(
        id=30,
        clinic_id=10,
        patient_id=20,
    )

    monkeypatch.setattr(
        billing_service,
        "get_patient",
        lambda patient_id: patient,
    )

    monkeypatch.setattr(
        billing_service.db.session,
        "get",
        lambda model, object_id: appointment,
    )

    with app.app_context():
        result = (
            billing_service._validate_invoice_relationships(
                clinic_id=10,
                patient_id=20,
                appointment_id=30,
            )
        )

    assert result == (
        patient,
        appointment,
    )


# ============================================================================
# create_invoice
# ============================================================================


def test_create_invoice_success(
    app,
    db_session,
    make_clinic,
    make_patient,
    monkeypatch,
):
    clinic = make_clinic()
    patient = make_patient(
        clinic=clinic,
    )

    monkeypatch.setattr(
        billing_service,
        "create_audit_log",
        lambda **kwargs: None,
    )

    monkeypatch.setattr(
        billing_service,
        "_generate_invoice_number",
        lambda clinic_id: "INV-10-20260907-ABC12345",
    )

    with app.app_context():
        invoice = billing_service.create_invoice(
            clinic_id=clinic.id,
            patient_id=patient.id,
            items=[
                {
                    "description": "Consultation",
                    "quantity": 2,
                    "unit_price": "50.00",
                },
                {
                    "description": "Lab",
                    "quantity": 1,
                    "unit_price": "25.00",
                },
            ],
        )

        assert invoice.id is not None
        assert invoice.clinic_id == clinic.id
        assert invoice.patient_id == patient.id
        assert invoice.appointment_id is None
        assert (
            invoice.invoice_number
            == "INV-10-20260907-ABC12345"
        )
        assert invoice.total_amount == Decimal("125.00")
        assert invoice.amount_paid == Decimal("0.00")
        assert invoice.status == InvoiceStatus.ISSUED

        db_session.flush()

        items = (
            InvoiceItem.query
            .filter(
                InvoiceItem.invoice_id
                == invoice.id
            )
            .all()
        )

        assert len(items) == 2

        assert items[0].description == "Consultation"
        assert items[0].quantity == 2
        assert items[0].unit_price == Decimal("50.00")
        assert items[0].subtotal == Decimal("100.00")

        assert items[1].description == "Lab"
        assert items[1].quantity == 1
        assert items[1].unit_price == Decimal("25.00")
        assert items[1].subtotal == Decimal("25.00")


def test_create_invoice_with_appointment(
    app,
    db_session,
    make_clinic,
    make_patient,
    make_user,
    monkeypatch,
):
    clinic = make_clinic()
    patient = make_patient(
        clinic=clinic,
    )

    user = make_user(
        clinic=clinic,
    )

    appointment = SimpleNamespace(
        id=30,
        clinic_id=clinic.id,
        patient_id=patient.id,
    )

    monkeypatch.setattr(
        billing_service.db.session,
        "get",
        lambda model, object_id: appointment,
    )

    monkeypatch.setattr(
        billing_service,
        "create_audit_log",
        lambda **kwargs: None,
    )

    with app.app_context():
        invoice = billing_service.create_invoice(
            clinic_id=clinic.id,
            patient_id=patient.id,
            appointment_id=appointment.id,
            items=[
                {
                    "description": "Consultation",
                    "quantity": 1,
                    "unit_price": "100.00",
                }
            ],
        )

        assert invoice.appointment_id == 30
        assert invoice.total_amount == Decimal("100.00")


def test_create_invoice_requires_insurance_provider_for_claim(
    app,
    make_clinic,
    make_patient,
):
    clinic = make_clinic()
    patient = make_patient(
        clinic=clinic,
    )

    with app.app_context():
        with pytest.raises(
            ValidationError,
            match="Insurance provider is required for an insurance claim",
        ):
            billing_service.create_invoice(
                clinic_id=clinic.id,
                patient_id=patient.id,
                is_insurance_claim=True,
                items=[
                    {
                        "description": "Treatment",
                        "quantity": 1,
                        "unit_price": "100.00",
                    }
                ],
            )


def test_create_invoice_normalizes_insurance_provider(
    app,
    make_clinic,
    make_patient,
    monkeypatch,
):
    clinic = make_clinic()
    patient = make_patient(
        clinic=clinic,
    )

    monkeypatch.setattr(
        billing_service,
        "create_audit_log",
        lambda **kwargs: None,
    )

    with app.app_context():
        invoice = billing_service.create_invoice(
            clinic_id=clinic.id,
            patient_id=patient.id,
            is_insurance_claim=True,
            insurance_provider="  NHIA  ",
            items=[
                {
                    "description": "Treatment",
                    "quantity": 1,
                    "unit_price": "100.00",
                }
            ],
        )

        assert invoice.insurance_provider == "NHIA"


def test_create_invoice_clears_provider_for_non_insurance_claim(
    app,
    make_clinic,
    make_patient,
    monkeypatch,
):
    clinic = make_clinic()
    patient = make_patient(
        clinic=clinic,
    )

    monkeypatch.setattr(
        billing_service,
        "create_audit_log",
        lambda **kwargs: None,
    )

    with app.app_context():
        invoice = billing_service.create_invoice(
            clinic_id=clinic.id,
            patient_id=patient.id,
            is_insurance_claim=False,
            insurance_provider="Private Insurance",
            items=[
                {
                    "description": "Treatment",
                    "quantity": 1,
                    "unit_price": "100.00",
                }
            ],
        )

        assert invoice.insurance_provider is None


# ============================================================================
# Payment Normalization
# ============================================================================


@pytest.mark.parametrize(
    "value,expected",
    [
        (
            PaymentMethod.CASH,
            PaymentMethod.CASH,
        ),
        (
            "cash",
            PaymentMethod.CASH,
        ),
        (
            "card",
            PaymentMethod.CARD,
        ),
        (
            "bank_transfer",
            PaymentMethod.BANK_TRANSFER,
        ),
        (
            "insurance",
            PaymentMethod.INSURANCE,
        ),
        (
            "mobile_money",
            PaymentMethod.MOBILE_MONEY,
        ),
    ],
)
def test_normalize_payment_method(
    value,
    expected,
):
    assert (
        billing_service._normalize_payment_method(
            value
        )
        == expected
    )


def test_normalize_payment_method_rejects_invalid():
    with pytest.raises(
        ValidationError,
        match="Invalid payment method",
    ):
        billing_service._normalize_payment_method(
            "bitcoin"
        )


@pytest.mark.parametrize(
    "value,expected",
    [
        (
            PaymentGateway.PAYSTACK,
            PaymentGateway.PAYSTACK,
        ),
        (
            "paystack",
            PaymentGateway.PAYSTACK,
        ),
        (
            "stripe",
            PaymentGateway.STRIPE,
        ),
        (
            "flutterwave",
            PaymentGateway.FLUTTERWAVE,
        ),
    ],
)
def test_normalize_payment_gateway(
    value,
    expected,
):
    assert (
        billing_service._normalize_payment_gateway(
            value
        )
        == expected
    )


def test_normalize_payment_gateway_accepts_none():
    assert (
        billing_service._normalize_payment_gateway(
            None
        )
        is None
    )


def test_normalize_payment_gateway_rejects_invalid():
    with pytest.raises(
        ValidationError,
        match="Invalid payment gateway",
    ):
        billing_service._normalize_payment_gateway(
            "bitcoin"
        )


# ============================================================================
# Gateway / Method Compatibility
# ============================================================================


@pytest.mark.parametrize(
    "method",
    [
        PaymentMethod.CARD,
        PaymentMethod.BANK_TRANSFER,
        PaymentMethod.MOBILE_MONEY,
    ],
)
def test_gateway_allowed_for_electronic_methods(
    method,
):
    assert (
        billing_service._validate_gateway_method(
            method,
            PaymentGateway.PAYSTACK,
        )
        is None
    )


@pytest.mark.parametrize(
    "method",
    [
        PaymentMethod.CASH,
        PaymentMethod.INSURANCE,
    ],
)
def test_gateway_rejected_for_non_electronic_methods(
    method,
):
    with pytest.raises(
        ValidationError,
        match="Payment gateway cannot be used",
    ):
        billing_service._validate_gateway_method(
            method,
            PaymentGateway.PAYSTACK,
        )


def test_gateway_none_allowed_for_cash():
    assert (
        billing_service._validate_gateway_method(
            PaymentMethod.CASH,
            None,
        )
        is None
    )


# ============================================================================
# Duplicate Gateway Payment
# ============================================================================


def test_find_duplicate_gateway_payment_returns_none_without_transaction_id():
    result = (
        billing_service._find_duplicate_gateway_payment(
            invoice_id=10,
            gateway_transaction_id=None,
        )
    )

    assert result is None


def test_find_duplicate_gateway_payment_returns_successful_payment(
    app,
    monkeypatch,
):
    payment = SimpleNamespace(
        id=50,
        invoice_id=10,
        gateway_transaction_id="TX-123",
        status=PaymentStatus.SUCCESSFUL,
    )

    monkeypatch.setattr(
        billing_service.Payment,
        "query",
        FakeQuery(result=payment),
    )

    with app.app_context():
        result = (
            billing_service._find_duplicate_gateway_payment(
                invoice_id=10,
                gateway_transaction_id="TX-123",
            )
        )

    assert result is payment


def test_find_duplicate_gateway_payment_returns_none_when_not_found(
    app,
    monkeypatch,
):
    monkeypatch.setattr(
        billing_service.Payment,
        "query",
        FakeQuery(result=None),
    )

    with app.app_context():
        result = (
            billing_service._find_duplicate_gateway_payment(
                invoice_id=10,
                gateway_transaction_id="TX-123",
            )
        )

    assert result is None


# ============================================================================
# record_payment
# ============================================================================


def _make_payment_invoice(
    clinic_id=10,
    invoice_id=100,
    total=Decimal("100.00"),
    paid=Decimal("0.00"),
    status=InvoiceStatus.ISSUED,
):
    return Invoice(
        id=invoice_id,
        clinic_id=clinic_id,
        patient_id=20,
        invoice_number="INV-10-20260907-ABC12345",
        total_amount=total,
        amount_paid=paid,
        status=status,
    )


def test_record_payment_success(
    app,
    monkeypatch,
):
    invoice = _make_payment_invoice()

    monkeypatch.setattr(
        billing_service,
        "_get_invoice",
        lambda invoice_id, clinic_id=None: invoice,
    )

    monkeypatch.setattr(
        billing_service,
        "_find_duplicate_gateway_payment",
        lambda invoice_id, transaction_id: None,
    )

    monkeypatch.setattr(
        billing_service,
        "create_audit_log",
        lambda **kwargs: None,
    )

    with app.app_context():
        payment = billing_service.record_payment(
            clinic_id=10,
            invoice_id=100,
            amount="40.00",
            method="cash",
            reference="  CASH-001  ",
        )

        assert payment.id is not None
        assert payment.invoice_id == 100
        assert payment.amount == Decimal("40.00")
        assert payment.method == PaymentMethod.CASH
        assert payment.status == PaymentStatus.SUCCESSFUL
        assert payment.gateway is None
        assert payment.reference == "CASH-001"
        assert payment.gateway_transaction_id is None
        assert payment.paid_at is not None

        assert invoice.amount_paid == Decimal("40.00")
        assert (
            invoice.status
            == InvoiceStatus.PARTIALLY_PAID
        )


def test_record_payment_fully_pays_invoice(
    app,
    monkeypatch,
):
    invoice = _make_payment_invoice()

    monkeypatch.setattr(
        billing_service,
        "_get_invoice",
        lambda invoice_id, clinic_id=None: invoice,
    )

    monkeypatch.setattr(
        billing_service,
        "_find_duplicate_gateway_payment",
        lambda invoice_id, transaction_id: None,
    )

    monkeypatch.setattr(
        billing_service,
        "create_audit_log",
        lambda **kwargs: None,
    )

    with app.app_context():
        payment = billing_service.record_payment(
            clinic_id=10,
            invoice_id=100,
            amount="100.00",
            method=PaymentMethod.CARD,
        )

        assert payment.amount == Decimal("100.00")
        assert invoice.amount_paid == Decimal("100.00")
        assert invoice.status == InvoiceStatus.PAID


def test_record_payment_rejects_cancelled_invoice(
    app,
    monkeypatch,
):
    invoice = _make_payment_invoice(
        status=InvoiceStatus.CANCELLED,
    )

    monkeypatch.setattr(
        billing_service,
        "_get_invoice",
        lambda invoice_id, clinic_id=None: invoice,
    )

    with app.app_context():
        with pytest.raises(
            ConflictError,
            match="Cannot record payment for cancelled invoice",
        ):
            billing_service.record_payment(
                clinic_id=10,
                invoice_id=100,
                amount="50.00",
                method=PaymentMethod.CASH,
            )


def test_record_payment_rejects_paid_invoice(
    app,
    monkeypatch,
):
    invoice = _make_payment_invoice(
        paid=Decimal("100.00"),
        status=InvoiceStatus.PAID,
    )

    monkeypatch.setattr(
        billing_service,
        "_get_invoice",
        lambda invoice_id, clinic_id=None: invoice,
    )

    with app.app_context():
        with pytest.raises(
            ConflictError,
            match="already fully paid",
        ):
            billing_service.record_payment(
                clinic_id=10,
                invoice_id=100,
                amount="10.00",
                method=PaymentMethod.CASH,
            )


def test_record_payment_rejects_zero_amount(
    app,
    monkeypatch,
):
    invoice = _make_payment_invoice()

    monkeypatch.setattr(
        billing_service,
        "_get_invoice",
        lambda invoice_id, clinic_id=None: invoice,
    )

    with app.app_context():
        with pytest.raises(
            ValidationError,
            match="Payment amount must be greater than zero",
        ):
            billing_service.record_payment(
                clinic_id=10,
                invoice_id=100,
                amount=0,
                method=PaymentMethod.CASH,
            )


@pytest.mark.parametrize(
    "amount",
    [
        "-1",
        "-10.00",
    ],
)
def test_record_payment_rejects_negative_amount(
    app,
    monkeypatch,
    amount,
):
    invoice = _make_payment_invoice()

    monkeypatch.setattr(
        billing_service,
        "_get_invoice",
        lambda invoice_id, clinic_id=None: invoice,
    )

    with app.app_context():
        with pytest.raises(
            ValidationError,
            match="payment amount cannot be negative",
        ):
            billing_service.record_payment(
                clinic_id=10,
                invoice_id=100,
                amount=amount,
                method=PaymentMethod.CASH,
            )


def test_record_payment_rejects_gateway_without_transaction_id(
    app,
    monkeypatch,
):
    invoice = _make_payment_invoice()

    monkeypatch.setattr(
        billing_service,
        "_get_invoice",
        lambda invoice_id, clinic_id=None: invoice,
    )

    with app.app_context():
        with pytest.raises(
            ValidationError,
            match="Gateway transaction ID is required",
        ):
            billing_service.record_payment(
                clinic_id=10,
                invoice_id=100,
                amount="50.00",
                method=PaymentMethod.CARD,
                gateway=PaymentGateway.PAYSTACK,
            )


def test_record_payment_rejects_gateway_for_cash(
    app,
    monkeypatch,
):
    invoice = _make_payment_invoice()

    monkeypatch.setattr(
        billing_service,
        "_get_invoice",
        lambda invoice_id, clinic_id=None: invoice,
    )

    with app.app_context():
        with pytest.raises(
            ValidationError,
            match="Payment gateway cannot be used",
        ):
            billing_service.record_payment(
                clinic_id=10,
                invoice_id=100,
                amount="50.00",
                method=PaymentMethod.CASH,
                gateway=PaymentGateway.PAYSTACK,
                gateway_transaction_id="TX-123",
            )


def test_record_payment_rejects_duplicate_gateway_transaction(
    app,
    monkeypatch,
):
    invoice = _make_payment_invoice()

    duplicate = SimpleNamespace(
        id=500,
        gateway_transaction_id="TX-123",
        status=PaymentStatus.SUCCESSFUL,
    )

    monkeypatch.setattr(
        billing_service,
        "_get_invoice",
        lambda invoice_id, clinic_id=None: invoice,
    )

    monkeypatch.setattr(
        billing_service,
        "_find_duplicate_gateway_payment",
        lambda invoice_id, transaction_id: duplicate,
    )

    with app.app_context():
        with pytest.raises(
            ConflictError,
            match="successful payment with this gateway transaction ID",
        ):
            billing_service.record_payment(
                clinic_id=10,
                invoice_id=100,
                amount="50.00",
                method=PaymentMethod.CARD,
                gateway=PaymentGateway.PAYSTACK,
                gateway_transaction_id="TX-123",
            )


def test_record_payment_rejects_overpayment(
    app,
    monkeypatch,
):
    invoice = _make_payment_invoice(
        total=Decimal("100.00"),
        paid=Decimal("75.00"),
    )

    monkeypatch.setattr(
        billing_service,
        "_get_invoice",
        lambda invoice_id, clinic_id=None: invoice,
    )

    monkeypatch.setattr(
        billing_service,
        "_find_duplicate_gateway_payment",
        lambda invoice_id, transaction_id: None,
    )

    with app.app_context():
        with pytest.raises(
            ValidationError,
            match="Payment amount exceeds the remaining invoice balance",
        ):
            billing_service.record_payment(
                clinic_id=10,
                invoice_id=100,
                amount="30.00",
                method=PaymentMethod.CASH,
            )


def test_record_payment_gateway_success(
    app,
    monkeypatch,
):
    invoice = _make_payment_invoice()

    monkeypatch.setattr(
        billing_service,
        "_get_invoice",
        lambda invoice_id, clinic_id=None: invoice,
    )

    monkeypatch.setattr(
        billing_service,
        "_find_duplicate_gateway_payment",
        lambda invoice_id, transaction_id: None,
    )

    monkeypatch.setattr(
        billing_service,
        "create_audit_log",
        lambda **kwargs: None,
    )

    with app.app_context():
        payment = billing_service.record_payment(
            clinic_id=10,
            invoice_id=100,
            amount="100.00",
            method="card",
            gateway="paystack",
            gateway_transaction_id=" TX-123 ",
        )

        assert payment.amount == Decimal("100.00")
        assert payment.method == PaymentMethod.CARD
        assert payment.gateway == PaymentGateway.PAYSTACK
        assert (
            payment.gateway_transaction_id
            == "TX-123"
        )
        assert payment.status == PaymentStatus.SUCCESSFUL
        assert invoice.status == InvoiceStatus.PAID


# ============================================================================
# get_outstanding_invoices
# ============================================================================


def test_get_outstanding_invoices_filters_clinic(
    app,
    monkeypatch,
):
    invoices = [
        SimpleNamespace(id=1),
        SimpleNamespace(id=2),
    ]

    query = FakeQuery(
        results=invoices,
    )

    monkeypatch.setattr(
        billing_service.Invoice,
        "query",
        query,
    )

    with app.app_context():
        result = (
            billing_service.get_outstanding_invoices(
                clinic_id=10,
            )
        )

    assert result == invoices


def test_get_outstanding_invoices_without_clinic(
    app,
    monkeypatch,
):
    query = FakeQuery(
        results=[
            SimpleNamespace(id=1),
        ]
    )

    monkeypatch.setattr(
        billing_service.Invoice,
        "query",
        query,
    )

    with app.app_context():
        result = (
            billing_service.get_outstanding_invoices()
        )

    assert len(result) == 1
    assert result[0].id == 1


def test_get_outstanding_invoices_rejects_invalid_clinic_id(app):
    with app.app_context():
        with pytest.raises(
            ValidationError,
            match="Clinic ID must be a positive integer",
        ):
            billing_service.get_outstanding_invoices(
                clinic_id=0,
            )


# ============================================================================
# _mark_overdue_invoices
# ============================================================================


def test_mark_overdue_invoices_marks_expired_invoices(
    app,
    monkeypatch,
):
    invoice_one = SimpleNamespace(
        id=1,
        status=InvoiceStatus.ISSUED,
    )

    invoice_two = SimpleNamespace(
        id=2,
        status=InvoiceStatus.PARTIALLY_PAID,
    )

    query = FakeQuery(
        results=[
            invoice_one,
            invoice_two,
        ]
    )

    monkeypatch.setattr(
        billing_service.Invoice,
        "query",
        query,
    )

    monkeypatch.setattr(
        billing_service,
        "create_audit_log",
        lambda **kwargs: None,
    )

    class FakeDate:
        @classmethod
        def today(cls):
            return date(2026, 9, 7)

    monkeypatch.setattr(
        billing_service,
        "date",
        FakeDate,
    )

    with app.app_context():
        result = (
            billing_service._mark_overdue_invoices(
                clinic_id=10,
            )
        )

    assert result == 2
    assert (
        invoice_one.status
        == InvoiceStatus.OVERDUE
    )
    assert (
        invoice_two.status
        == InvoiceStatus.OVERDUE
    )


def test_mark_overdue_invoices_returns_zero_when_none_found(
    app,
    monkeypatch,
):
    query = FakeQuery(
        results=[],
    )

    monkeypatch.setattr(
        billing_service.Invoice,
        "query",
        query,
    )

    with app.app_context():
        result = (
            billing_service._mark_overdue_invoices(
                clinic_id=10,
            )
        )

    assert result == 0


def test_mark_overdue_invoices_rejects_invalid_clinic(app):
    with app.app_context():
        with pytest.raises(
            ValidationError,
            match="Clinic ID must be a positive integer",
        ):
            billing_service._mark_overdue_invoices(
                clinic_id=0,
            )

# ============================================================================
# mark_overdue_invoices
# ============================================================================


def test_mark_overdue_invoices_delegates_to_internal_function(
    app,
    monkeypatch,
):
    captured = {}

    def fake_mark_overdue(
        clinic_id=None,
    ):
        captured["clinic_id"] = clinic_id
        return 7

    monkeypatch.setattr(
        billing_service,
        "_mark_overdue_invoices",
        fake_mark_overdue,
    )

    with app.app_context():
        result = (
            billing_service.mark_overdue_invoices(
                clinic_id=10,
            )
        )

    assert result == 7
    assert captured["clinic_id"] == 10


# ============================================================================
# Celery Task
# ============================================================================


def test_mark_overdue_invoices_task_commits(
    monkeypatch,
):
    commit_called = []

    monkeypatch.setattr(
        billing_service,
        "_mark_overdue_invoices",
        lambda: 4,
    )

    monkeypatch.setattr(
        billing_service.db.session,
        "commit",
        lambda: commit_called.append(True),
    )

    result = (
        billing_service.mark_overdue_invoices_task()
    )

    assert result == 4
    assert commit_called == [True]


def test_mark_overdue_invoices_task_rolls_back_on_error(
    monkeypatch,
):
    rollback_called = []

    monkeypatch.setattr(
        billing_service,
        "_mark_overdue_invoices",
        lambda: (_ for _ in ()).throw(
            RuntimeError("database failure")
        ),
    )

    monkeypatch.setattr(
        billing_service.db.session,
        "rollback",
        lambda: rollback_called.append(True),
    )

    with pytest.raises(
        RuntimeError,
        match="database failure",
    ):
        billing_service.mark_overdue_invoices_task()

    assert rollback_called == [True]