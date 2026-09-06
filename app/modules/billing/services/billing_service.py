from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from app.extensions import db, celery

from app.core.audit.services.audit_service import (
    create_audit_log,
)
from app.core.enums.audit_enums import AuditAction
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
from app.core.utils.decorators import transactional

from app.modules.appointment.models.appointment_model import (
    Appointment,
)
from app.modules.billing.models.billing_model import (
    Invoice,
    InvoiceItem,
    Payment,
)
from app.modules.patient.services.patient_service import (
    get_patient,
)


# ============================================================================
# Utilities
# ============================================================================


def _utcnow():
    return datetime.now(timezone.utc)


def _validate_positive_id(
    value,
    field_name,
):
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ValidationError(
            f"{field_name} must be a positive integer"
        )


def _to_decimal(
    value,
    field_name="amount",
):
    try:
        amount = Decimal(str(value))
    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        raise ValidationError(
            f"Invalid {field_name}"
        )

    if amount < Decimal("0"):
        raise ValidationError(
            f"{field_name} cannot be negative"
        )

    return amount


def _normalize_optional_string(
    value,
    field_name,
    max_length=None,
):
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValidationError(
            f"{field_name} must be a string"
        )

    value = value.strip()

    if not value:
        return None

    if (
        max_length is not None
        and len(value) > max_length
    ):
        raise ValidationError(
            f"{field_name} cannot exceed "
            f"{max_length} characters"
        )

    return value


# ============================================================================
# Invoice Helpers
# ============================================================================


def _get_invoice(
    invoice_id,
    clinic_id=None,
):
    _validate_positive_id(
        invoice_id,
        "Invoice ID",
    )

    query = Invoice.query.filter(
        Invoice.id == invoice_id
    )

    if clinic_id is not None:
        query = query.filter(
            Invoice.clinic_id == clinic_id
        )

    invoice = query.first()

    if invoice is None:
        raise NotFoundError(
            f"Invoice {invoice_id} not found"
        )

    return invoice


def _generate_invoice_number(clinic_id):
    today = date.today().strftime(
        "%Y%m%d"
    )

    unique_suffix = (
        uuid4().hex[:8].upper()
    )

    return (
        f"INV-{clinic_id}-"
        f"{today}-"
        f"{unique_suffix}"
    )


def _calculate_invoice_status(invoice):
    amount_paid = Decimal(
        invoice.amount_paid or 0
    )

    total_amount = Decimal(
        invoice.total_amount or 0
    )

    if amount_paid >= total_amount:
        return InvoiceStatus.PAID

    if amount_paid > Decimal("0"):
        return InvoiceStatus.PARTIALLY_PAID

    return InvoiceStatus.ISSUED


def _validate_invoice_items(items):
    if not items:
        raise ValidationError(
            "Invoice must contain at least one item"
        )

    normalized_items = []

    for item in items:
        if not isinstance(item, dict):
            raise ValidationError(
                "Each invoice item must be an object"
            )

        description = item.get(
            "description"
        )

        if not isinstance(
            description,
            str,
        ):
            raise ValidationError(
                "Each invoice item requires "
                "a description"
            )

        description = description.strip()

        if not description:
            raise ValidationError(
                "Each invoice item requires "
                "a description"
            )

        if len(description) > 255:
            raise ValidationError(
                "Invoice item description cannot "
                "exceed 255 characters"
            )

        quantity = item.get(
            "quantity",
            1,
        )

        if (
            isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or quantity <= 0
        ):
            raise ValidationError(
                "Invoice item quantity must be "
                "a positive integer"
            )

        unit_price = _to_decimal(
            item.get("unit_price"),
            "unit price",
        )

        normalized_items.append(
            {
                "description": description,
                "quantity": quantity,
                "unit_price": unit_price,
            }
        )

    return normalized_items


def _validate_invoice_relationships(
    clinic_id,
    patient_id,
    appointment_id=None,
):
    """
    Verify that referenced entities belong to the
    authenticated clinic.

    If an appointment is supplied, it must also belong
    to the specified patient.
    """

    patient = get_patient(
        patient_id
    )

    if patient.clinic_id != clinic_id:
        raise ValidationError(
            f"Patient {patient_id} does not belong "
            f"to clinic {clinic_id}"
        )

    appointment = None

    if appointment_id is not None:
        appointment = db.session.get(
            Appointment,
            appointment_id,
        )

        if appointment is None:
            raise NotFoundError(
                f"Appointment {appointment_id} not found"
            )

        if appointment.clinic_id != clinic_id:
            raise ValidationError(
                f"Appointment {appointment_id} does not "
                f"belong to clinic {clinic_id}"
            )

        if appointment.patient_id != patient_id:
            raise ValidationError(
                "Appointment does not belong "
                "to the specified patient"
            )

    return patient, appointment


# ============================================================================
# Create Invoice
# ============================================================================


@transactional
def create_invoice(
    clinic_id,
    patient_id,
    items: list[dict],
    appointment_id=None,
    due_date=None,
    is_insurance_claim=False,
    insurance_provider=None,
):
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    _validate_positive_id(
        patient_id,
        "Patient ID",
    )

    if appointment_id is not None:
        _validate_positive_id(
            appointment_id,
            "Appointment ID",
        )

    patient, appointment = (
        _validate_invoice_relationships(
            clinic_id=clinic_id,
            patient_id=patient_id,
            appointment_id=appointment_id,
        )
    )

    normalized_items = (
        _validate_invoice_items(items)
    )

    insurance_provider = (
        _normalize_optional_string(
            insurance_provider,
            "Insurance provider",
            max_length=120,
        )
    )

    if (
        is_insurance_claim
        and not insurance_provider
    ):
        raise ValidationError(
            "Insurance provider is required "
            "for an insurance claim"
        )

    if not is_insurance_claim:
        insurance_provider = None

    invoice = Invoice(
        clinic_id=clinic_id,
        patient_id=patient.id,
        appointment_id=(
            appointment.id
            if appointment is not None
            else None
        ),
        invoice_number=(
            _generate_invoice_number(
                clinic_id
            )
        ),
        status=InvoiceStatus.ISSUED,
        due_date=due_date,
        is_insurance_claim=(
            is_insurance_claim
        ),
        insurance_provider=(
            insurance_provider
        ),
        total_amount=Decimal("0"),
        amount_paid=Decimal("0"),
    )

    db.session.add(invoice)
    db.session.flush()

    total = Decimal("0")

    for item in normalized_items:
        subtotal = (
            item["unit_price"]
            * item["quantity"]
        )

        total += subtotal

        db.session.add(
            InvoiceItem(
                invoice_id=invoice.id,
                description=item["description"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                subtotal=subtotal,
            )
        )

    invoice.total_amount = total
    invoice.status = (
        _calculate_invoice_status(
            invoice
        )
    )

    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Invoice",
        entity_id=invoice.id,
        description=(
            f"Invoice {invoice.invoice_number} "
            f"created for patient {patient.id}"
        ),
        new_value={
            "clinic_id": clinic_id,
            "patient_id": patient.id,
            "appointment_id": (
                appointment.id
                if appointment is not None
                else None
            ),
            "total_amount": str(total),
            "amount_paid": str(
                invoice.amount_paid
            ),
            "status": invoice.status.value,
            "is_insurance_claim": (
                is_insurance_claim
            ),
            "insurance_provider": (
                insurance_provider
            ),
        },
    )

    return invoice


# ============================================================================
# Payment Helpers
# ============================================================================


def _normalize_payment_method(method):
    if isinstance(
        method,
        PaymentMethod,
    ):
        return method

    try:
        return PaymentMethod(method)
    except (
        ValueError,
        TypeError,
    ):
        raise ValidationError(
            "Invalid payment method"
        )


def _normalize_payment_gateway(gateway):
    if gateway is None:
        return None

    if isinstance(
        gateway,
        PaymentGateway,
    ):
        return gateway

    try:
        return PaymentGateway(gateway)
    except (
        ValueError,
        TypeError,
    ):
        raise ValidationError(
            "Invalid payment gateway"
        )


def _validate_gateway_method(
    method,
    gateway,
):
    electronic_methods = {
        PaymentMethod.CARD,
        PaymentMethod.BANK_TRANSFER,
        PaymentMethod.MOBILE_MONEY,
    }

    if (
        gateway is not None
        and method not in electronic_methods
    ):
        raise ValidationError(
            "Payment gateway cannot be used "
            f"with payment method "
            f"'{method.value}'"
        )


def _find_duplicate_gateway_payment(
    invoice_id,
    gateway_transaction_id,
):
    if not gateway_transaction_id:
        return None

    return Payment.query.filter(
        Payment.invoice_id == invoice_id,
        Payment.gateway_transaction_id
        == gateway_transaction_id,
        Payment.status
        == PaymentStatus.SUCCESSFUL,
    ).first()


# ============================================================================
# Record Payment
# ============================================================================


@transactional
def record_payment(
    clinic_id,
    invoice_id,
    amount,
    method,
    reference=None,
    gateway=None,
    gateway_transaction_id=None,
):
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    _validate_positive_id(
        invoice_id,
        "Invoice ID",
    )

    invoice = _get_invoice(
        invoice_id,
        clinic_id=clinic_id,
    )

    if (
        invoice.status
        == InvoiceStatus.CANCELLED
    ):
        raise ConflictError(
            "Cannot record payment for "
            f"cancelled invoice "
            f"{invoice.invoice_number}"
        )

    if (
        invoice.status
        == InvoiceStatus.PAID
    ):
        raise ConflictError(
            f"Invoice {invoice.invoice_number} "
            "is already fully paid"
        )

    amount = _to_decimal(
        amount,
        "payment amount",
    )

    if amount <= Decimal("0"):
        raise ValidationError(
            "Payment amount must be greater "
            "than zero"
        )

    method = _normalize_payment_method(
        method
    )

    gateway = _normalize_payment_gateway(
        gateway
    )

    _validate_gateway_method(
        method,
        gateway,
    )

    reference = _normalize_optional_string(
        reference,
        "Payment reference",
        max_length=120,
    )

    gateway_transaction_id = (
        _normalize_optional_string(
            gateway_transaction_id,
            "Gateway transaction ID",
            max_length=255,
        )
    )

    if (
        gateway is not None
        and not gateway_transaction_id
    ):
        raise ValidationError(
            "Gateway transaction ID is required "
            "for gateway payments"
        )

    duplicate_payment = (
        _find_duplicate_gateway_payment(
            invoice.id,
            gateway_transaction_id,
        )
    )

    if duplicate_payment is not None:
        raise ConflictError(
            "A successful payment with this "
            "gateway transaction ID has already "
            "been recorded"
        )

    total_amount = Decimal(
        invoice.total_amount
    )

    amount_paid = Decimal(
        invoice.amount_paid
    )

    remaining_balance = (
        total_amount - amount_paid
    )

    if amount > remaining_balance:
        raise ValidationError(
            "Payment amount exceeds the remaining "
            "invoice balance of "
            f"{remaining_balance}"
        )

    old_status = invoice.status.value
    old_amount_paid = amount_paid

    payment = Payment(
        invoice_id=invoice.id,
        amount=amount,
        method=method,
        status=PaymentStatus.SUCCESSFUL,
        gateway=gateway,
        reference=reference,
        gateway_transaction_id=(
            gateway_transaction_id
        ),
    )

    payment.paid_at = _utcnow()

    db.session.add(payment)

    invoice.amount_paid = (
        amount_paid + amount
    )

    invoice.status = (
        _calculate_invoice_status(
            invoice
        )
    )

    db.session.flush()

    create_audit_log(
        action=AuditAction.PAYMENT,
        entity_type="Invoice",
        entity_id=invoice.id,
        description=(
            f"Payment of {amount} recorded "
            f"via {method.value}"
        ),
        old_value={
            "status": old_status,
            "amount_paid": str(
                old_amount_paid
            ),
        },
        new_value={
            "amount_paid": str(
                invoice.amount_paid
            ),
            "status": invoice.status.value,
            "payment_method": method.value,
            "payment_gateway": (
                gateway.value
                if gateway
                else None
            ),
            "gateway_transaction_id": (
                gateway_transaction_id
            ),
        },
    )

    return payment


# ============================================================================
# Outstanding Invoices
# ============================================================================


def get_outstanding_invoices(
    clinic_id=None,
):
    query = Invoice.query.filter(
        Invoice.status.in_(
            [
                InvoiceStatus.ISSUED,
                InvoiceStatus.PARTIALLY_PAID,
                InvoiceStatus.OVERDUE,
            ]
        )
    )

    if clinic_id is not None:
        _validate_positive_id(
            clinic_id,
            "Clinic ID",
        )

        query = query.filter(
            Invoice.clinic_id == clinic_id
        )

    return query.order_by(
        Invoice.due_date.asc(),
        Invoice.created_at.asc(),
    ).all()


# ============================================================================
# Overdue Invoice Processing
# ============================================================================


def _mark_overdue_invoices(
    clinic_id=None,
):
    today = date.today()

    query = Invoice.query.filter(
        Invoice.due_date.isnot(None),
        Invoice.due_date < today,
        Invoice.status.in_(
            [
                InvoiceStatus.ISSUED,
                InvoiceStatus.PARTIALLY_PAID,
            ]
        ),
    )

    if clinic_id is not None:
        _validate_positive_id(
            clinic_id,
            "Clinic ID",
        )

        query = query.filter(
            Invoice.clinic_id == clinic_id
        )

    overdue = query.all()

    for invoice in overdue:
        old_status = invoice.status.value

        invoice.status = (
            InvoiceStatus.OVERDUE
        )

        create_audit_log(
            action=AuditAction.STATUS_CHANGE,
            entity_type="Invoice",
            entity_id=invoice.id,
            description=(
                "Invoice marked overdue"
                + (
                    " (automated)"
                    if clinic_id is None
                    else ""
                )
            ),
            old_value={
                "status": old_status,
            },
            new_value={
                "status": (
                    InvoiceStatus.OVERDUE.value
                ),
            },
        )

    return len(overdue)


@transactional
def mark_overdue_invoices(
    clinic_id=None,
):
    """
    Clinic-scoped operation used by the HTTP route.
    """

    return _mark_overdue_invoices(
        clinic_id=clinic_id
    )


@celery.task(name="mark_overdue_invoices")
def mark_overdue_invoices_task():
    """
    Global scheduled operation.

    Processes overdue invoices across all clinics.
    """

    try:
        updated_count = (
            _mark_overdue_invoices()
        )

        db.session.commit()

        return updated_count

    except Exception:
        db.session.rollback()
        raise