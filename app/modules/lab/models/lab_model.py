from datetime import datetime, timezone
from app.extensions import db
from app.core.enums.lab_enums import LabOrderStatus, LabResultFlag, SampleType

def _utcnow():
    return datetime.now(timezone.utc)

class LabTest(db.Model):
    __tablename__ = "lab_tests"

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=True)

    name = db.Column(db.String(150), nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=True)
    sample_type = db.Column(db.Enum(SampleType), default=SampleType.BLOOD, nullable=False)
    reference_range = db.Column(db.String(150), nullable=True)
    unit = db.Column(db.String(30), nullable=True)
    price = db.Column(db.Numeric(10, 2), nullable=True)

    # NEW: numeric critical thresholds, separate from reference_range.
    # Nullable — a test with no thresholds set simply can't be
    # auto-flagged CRITICAL, and enter_result() will leave that to a
    # human, same as it already does for non-numeric results.
    critical_low = db.Column(db.Numeric(10, 3), nullable=True)
    critical_high = db.Column(db.Numeric(10, 3), nullable=True)

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    orders = db.relationship("LabOrderItem", back_populates="test")

    def __repr__(self):
        return f"<LabTest {self.name}>"


class LabOrder(db.Model):
    __tablename__ = "lab_orders"

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id"), nullable=True)
    ordered_by_id = db.Column(db.Integer, db.ForeignKey("staff.id"), nullable=False)

    status = db.Column(db.Enum(LabOrderStatus), default=LabOrderStatus.ORDERED, nullable=False)

    qr_code = db.Column(db.String(150), unique=True, nullable=True)
    sample_collected_at = db.Column(db.DateTime, nullable=True)
    equipment_reference_id = db.Column(db.String(150), nullable=True)

    # NEW: queryable/reportable cancel reason, instead of only living
    # inside an audit log description string.
    cancellation_reason = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    clinic = db.relationship("Clinic", back_populates="lab_orders")
    patient = db.relationship("Patient", back_populates="lab_orders")
    consultation = db.relationship("Consultation", back_populates="lab_orders")
    ordered_by = db.relationship("Staff", back_populates="lab_orders")
    items = db.relationship("LabOrderItem", back_populates="order", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<LabOrder {self.id} - Patient {self.patient_id} ({self.status.value})>"


class LabOrderItem(db.Model):
    """A single test within a lab order, plus its result once ready."""
    __tablename__ = "lab_order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("lab_orders.id"), nullable=False)
    test_id = db.Column(db.Integer, db.ForeignKey("lab_tests.id"), nullable=False)

    result_value = db.Column(db.String(150), nullable=True)
    flag = db.Column(db.Enum(LabResultFlag), nullable=True)
    result_notes = db.Column(db.Text, nullable=True)
    result_file_url = db.Column(db.String(255), nullable=True)   

    resulted_at = db.Column(db.DateTime, nullable=True)

    order = db.relationship("LabOrder", back_populates="items")
    test = db.relationship("LabTest", back_populates="orders")

    def __repr__(self):
        return f"<LabOrderItem Test {self.test_id} - Order {self.order_id}>"