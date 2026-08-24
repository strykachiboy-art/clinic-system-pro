from datetime import datetime, timezone
from app.extensions import db
from app.core.enums.billing_enums import InvoiceStatus, PaymentMethod, PaymentStatus

def _utcnow():
    return datetime.now(timezone.utc)

class Invoice(db.Model):
    __tablename__ = "invoices"

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    appointment_id = db.Column(db.Integer, db.ForeignKey("appointments.id"), nullable=True)

    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    amount_paid = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    status = db.Column(db.Enum(InvoiceStatus), default=InvoiceStatus.DRAFT, nullable=False)

    due_date = db.Column(db.Date, nullable=True)
    is_insurance_claim = db.Column(db.Boolean, default=False)
    insurance_provider = db.Column(db.String(120), nullable=True)

    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    clinic = db.relationship("Clinic", back_populates="invoices")
    patient = db.relationship("Patient", back_populates="invoices")
    items = db.relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")
    payments = db.relationship("Payment", back_populates="invoice", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Invoice {self.invoice_number} - {self.status.value}>"


class InvoiceItem(db.Model):
    __tablename__ = "invoice_items"

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False)

    description = db.Column(db.String(255), nullable=False) 
    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)

    invoice = db.relationship("Invoice", back_populates="items")


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False)

    amount = db.Column(db.Numeric(10, 2), nullable=False)
    method = db.Column(db.Enum(PaymentMethod), nullable=False)
    status = db.Column(db.Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    reference = db.Column(db.String(120), nullable=True)

    paid_at = db.Column(db.DateTime, default=_utcnow)

    invoice = db.relationship("Invoice", back_populates="payments")

    def __repr__(self):
        return f"<Payment {self.amount} - {self.status.value}>"