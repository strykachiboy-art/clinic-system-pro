from datetime import date
from decimal import Decimal
from app.extensions import db, celery
from app.modules.billing.models.billing_model import Invoice, InvoiceItem, Payment
from app.core.enums.billing_enums import InvoiceStatus, PaymentStatus
from app.core.audit.services.audit_services import create_audit_log
from app.core.enums.audit_enums import AuditAction


def create_invoice(clinic_id, patient_id, items: list[dict], appointment_id=None, due_date=None, is_insurance_claim=False, insurance_provider=None):
    """items = [{'description': str, 'quantity': int, 'unit_price': Decimal}]"""
    invoice_number = f"INV-{clinic_id}-{int(date.today().strftime('%Y%m%d'))}-{Invoice.query.count() + 1}"

    invoice = Invoice(
        clinic_id=clinic_id,
        patient_id=patient_id,
        appointment_id=appointment_id,
        invoice_number=invoice_number,
        status=InvoiceStatus.ISSUED,
        due_date=due_date,
        is_insurance_claim=is_insurance_claim,
        insurance_provider=insurance_provider,
    )
    db.session.add(invoice)
    db.session.flush()

    total = Decimal("0")
    for item in items:
        subtotal = Decimal(item["unit_price"]) * item["quantity"]
        total += subtotal
        db.session.add(InvoiceItem(
            invoice_id=invoice.id,
            description=item["description"],
            quantity=item["quantity"],
            unit_price=item["unit_price"],
            subtotal=subtotal,
        ))

    invoice.total_amount = total
    db.session.flush()  

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Invoice",
        entity_id=invoice.id,
        description=f"Invoice {invoice.invoice_number} created for patient {patient_id}",
        new_value={"total_amount": str(total), "status": invoice.status.value},
    )

    db.session.commit()
    return invoice


def record_payment(invoice_id, amount, method, reference=None):
    invoice = Invoice.query.get_or_404(invoice_id)
    old_status = invoice.status.value

    payment = Payment(
        invoice_id=invoice.id,
        amount=amount,
        method=method,
        status=PaymentStatus.SUCCESSFUL,
        reference=reference,
    )
    db.session.add(payment)

    invoice.amount_paid += Decimal(amount)
    if invoice.amount_paid >= invoice.total_amount:
        invoice.status = InvoiceStatus.PAID
    elif invoice.amount_paid > 0:
        invoice.status = InvoiceStatus.PARTIALLY_PAID

    create_audit_log(
        action=AuditAction.PAYMENT,
        entity_type="Invoice",
        entity_id=invoice.id,
        description=f"Payment of {amount} recorded via {method.value}",
        old_value={"status": old_status},
        new_value={"amount_paid": str(invoice.amount_paid), "status": invoice.status.value},
    )

    db.session.commit()
    return payment


def get_outstanding_invoices(clinic_id=None):
    query = Invoice.query.filter(Invoice.status.in_([InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE]))
    if clinic_id:
        query = query.filter_by(clinic_id=clinic_id)
    return query.all()


@celery.task(name="mark_overdue_invoices")
def mark_overdue_invoices():
    """Run daily via celery beat."""
    today = date.today()
    overdue = Invoice.query.filter(
        Invoice.due_date < today,
        Invoice.status.in_([InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID]),
    ).all()

    for invoice in overdue:
        old_status = invoice.status.value
        invoice.status = InvoiceStatus.OVERDUE

        create_audit_log(
            action=AuditAction.STATUS_CHANGE,
            entity_type="Invoice",
            entity_id=invoice.id,
            description="Invoice marked overdue (automated)",
            old_value={"status": old_status},
            new_value={"status": "overdue"},
        )

    db.session.commit()
    return len(overdue)