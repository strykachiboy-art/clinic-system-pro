from datetime import date, timezone, datetime
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from app.extensions import db, celery
from app.modules.billing.models.billing_model import Invoice, InvoiceItem, Payment
from app.core.enums.billing_enums import (
    InvoiceStatus,
    PaymentGateway,
    PaymentMethod,
    PaymentStatus,
)
from app.core.audit.services.audit_services import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.exceptions import ConflictError, NotFoundError, ValidationError


def _utcnow():
    return datetime.now(timezone.utc)


def _to_decimal(value, field_name="amount"):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(f"Invalid {field_name}")

    if amount < Decimal("0"):
        raise ValidationError(f"{field_name} cannot be negative")

    return amount


def _get_invoice(invoice_id):
    invoice = db.session.get(Invoice, invoice_id)

    if invoice is None:
        raise NotFoundError(f"Invoice {invoice_id} not found")

    return invoice


def _normalize_payment_method(method):
    if isinstance(method, PaymentMethod):
        return method

    try:
        return PaymentMethod(method)
    except (ValueError, TypeError):
        raise ValidationError("Invalid payment method")


def _normalize_payment_gateway(gateway):
    if gateway is None:
        return None

    if isinstance(gateway, PaymentGateway):
        return gateway

    try:
        return PaymentGateway(gateway)
    except (ValueError, TypeError):
        raise ValidationError("Invalid payment gateway")


def _validate_gateway_method(method, gateway):
    """
    Gateways are only relevant to electronic payments.

    Manual payment methods such as cash and insurance should not
    be associated with an electronic payment gateway.
    """
    electronic_methods = {
        PaymentMethod.CARD,
        PaymentMethod.BANK_TRANSFER,
        PaymentMethod.MOBILE_MONEY,
    }

    if gateway is not None and method not in electronic_methods:
        raise ValidationError(
            f"Payment gateway cannot be used with payment method '{method.value}'"
        )


def _generate_invoice_number(clinic_id):
    """
    Generate a unique invoice number without relying on Invoice.query.count().

    The previous count()+1 approach could produce duplicate invoice numbers
    under concurrent requests or after records are deleted.
    """
    today = date.today().strftime("%Y%m%d")
    unique_suffix = uuid4().hex[:8].upper()

    return f"INV-{clinic_id}-{today}-{unique_suffix}"


def _calculate_invoice_status(invoice):
    if invoice.amount_paid >= invoice.total_amount:
        return InvoiceStatus.PAID

    if invoice.amount_paid > Decimal("0"):
        return InvoiceStatus.PARTIALLY_PAID

    return InvoiceStatus.ISSUED


def create_invoice(
    clinic_id,
    patient_id,
    items: list[dict],
    appointment_id=None,
    due_date=None,
    is_insurance_claim=False,
    insurance_provider=None,
):
    """
    Create and issue an invoice.

    Expected item structure:

        {
            "description": str,
            "quantity": int,
            "unit_price": Decimal
        }
    """

    if not clinic_id:
        raise ValidationError("Clinic ID is required")

    if not patient_id:
        raise ValidationError("Patient ID is required")

    if not items:
        raise ValidationError("Invoice must contain at least one item")

    if is_insurance_claim and not insurance_provider:
        raise ValidationError(
            "Insurance provider is required for an insurance claim"
        )

    invoice = Invoice(
        clinic_id=clinic_id,
        patient_id=patient_id,
        appointment_id=appointment_id,
        invoice_number=_generate_invoice_number(clinic_id),
        status=InvoiceStatus.ISSUED,
        due_date=due_date,
        is_insurance_claim=is_insurance_claim,
        insurance_provider=insurance_provider,
        total_amount=Decimal("0"),
        amount_paid=Decimal("0"),
    )

    db.session.add(invoice)
    db.session.flush()

    total = Decimal("0")

    for item in items:
        description = item.get("description")
        quantity = item.get("quantity", 1)
        unit_price = item.get("unit_price")

        if not description:
            raise ValidationError(
                "Each invoice item requires a description"
            )

        if not isinstance(quantity, int) or quantity <= 0:
            raise ValidationError(
                "Invoice item quantity must be a positive integer"
            )

        unit_price = _to_decimal(
            unit_price,
            "unit price",
        )

        subtotal = unit_price * quantity
        total += subtotal

        db.session.add(
            InvoiceItem(
                invoice_id=invoice.id,
                description=description,
                quantity=quantity,
                unit_price=unit_price,
                subtotal=subtotal,
            )
        )

    invoice.total_amount = total

    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Invoice",
        entity_id=invoice.id,
        description=(
            f"Invoice {invoice.invoice_number} created "
            f"for patient {patient_id}"
        ),
        new_value={
            "total_amount": str(total),
            "amount_paid": str(invoice.amount_paid),
            "status": invoice.status.value,
        },
    )

    db.session.commit()

    return invoice


def record_payment(
    invoice_id,
    amount,
    method,
    reference=None,
    gateway=None,
    gateway_transaction_id=None,
):
    """
    Record a successful payment.

    This function is intended for payments that have already been
    confirmed as successful.

    Gateway initialization and webhook verification will be added
    separately when the payment gateway layer is implemented.
    """

    invoice = _get_invoice(invoice_id)

    if invoice.status == InvoiceStatus.CANCELLED:
        raise ConflictError(
            f"Cannot record payment for cancelled invoice {invoice.invoice_number}"
        )

    if invoice.status == InvoiceStatus.PAID:
        raise ConflictError(
            f"Invoice {invoice.invoice_number} is already fully paid"
        )

    amount = _to_decimal(amount)

    if amount <= Decimal("0"):
        raise ValidationError("Payment amount must be greater than zero")

    method = _normalize_payment_method(method)
    gateway = _normalize_payment_gateway(gateway)

    _validate_gateway_method(method, gateway)

    remaining_balance = (
        Decimal(invoice.total_amount)
        - Decimal(invoice.amount_paid)
    )

    if amount > remaining_balance:
        raise ValidationError(
            f"Payment amount exceeds the remaining invoice balance "
            f"of {remaining_balance}"
        )

    if gateway is not None and not gateway_transaction_id:
        raise ValidationError(
            "Gateway transaction ID is required for gateway payments"
        )

    old_status = invoice.status.value

    payment = Payment(
    invoice_id=invoice.id,
    amount=amount,
    method=method,
    status=PaymentStatus.SUCCESSFUL,
    gateway=gateway,
    reference=reference,
    gateway_transaction_id=gateway_transaction_id,
)

    payment.paid_at = _utcnow()

    db.session.add(payment)

    invoice.amount_paid = (
        Decimal(invoice.amount_paid) + amount
    )

    invoice.status = _calculate_invoice_status(invoice)

    create_audit_log(
        action=AuditAction.PAYMENT,
        entity_type="Invoice",
        entity_id=invoice.id,
        description=(
            f"Payment of {amount} recorded via {method.value}"
        ),
        old_value={
            "status": old_status,
            "amount_paid": str(
                Decimal(invoice.amount_paid) - amount
            ),
        },
        new_value={
            "amount_paid": str(invoice.amount_paid),
            "status": invoice.status.value,
            "payment_method": method.value,
            "payment_gateway": (
                gateway.value if gateway else None
            ),
        },
    )

    db.session.commit()

    return payment


def get_outstanding_invoices(clinic_id=None):
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
        query = query.filter(
            Invoice.clinic_id == clinic_id
        )

    return query.order_by(
        Invoice.due_date.asc(),
        Invoice.created_at.asc(),
    ).all()


@celery.task(name="mark_overdue_invoices")
def mark_overdue_invoices():
    """
    Mark issued and partially-paid invoices as overdue
    when their due date has passed.
    """

    today = date.today()

    overdue = Invoice.query.filter(
        Invoice.due_date.isnot(None),
        Invoice.due_date < today,
        Invoice.status.in_(
            [
                InvoiceStatus.ISSUED,
                InvoiceStatus.PARTIALLY_PAID,
            ]
        ),
    ).all()

    for invoice in overdue:
        old_status = invoice.status.value

        invoice.status = InvoiceStatus.OVERDUE

        create_audit_log(
            action=AuditAction.STATUS_CHANGE,
            entity_type="Invoice",
            entity_id=invoice.id,
            description="Invoice marked overdue (automated)",
            old_value={
                "status": old_status,
            },
            new_value={
                "status": InvoiceStatus.OVERDUE.value,
            },
        )

    db.session.commit()
    return len(overdue)