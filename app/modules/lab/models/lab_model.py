from datetime import datetime, timezone

from app.extensions import db
from app.core.enums.lab_enums import (
    LabOrderStatus,
    LabResultFlag,
    SampleType,
)


def _utcnow():
    return datetime.now(timezone.utc)


class LabTest(db.Model):
    __tablename__ = "lab_tests"

    __table_args__ = (
        db.CheckConstraint(
            "critical_low IS NULL "
            "OR critical_high IS NULL "
            "OR critical_low <= critical_high",
            name="ck_lab_tests_valid_critical_range",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)

    clinic_id = db.Column(
        db.Integer,
        db.ForeignKey("clinics.id"),
        nullable=True,
        index=True,
    )

    # Standard LOINC terminology code.
    loinc_code = db.Column(
        db.String(20),
        nullable=True,
        index=True,
    )

    name = db.Column(
        db.String(150),
        nullable=False,
    )

    # Internal test code.
    code = db.Column(
        db.String(50),
        unique=True,
        nullable=True,
        index=True,
    )

    sample_type = db.Column(
        db.Enum(SampleType),
        default=SampleType.BLOOD,
        nullable=False,
        index=True,
    )

    reference_range = db.Column(
        db.String(150),
        nullable=True,
    )

    unit = db.Column(
        db.String(30),
        nullable=True,
    )

    price = db.Column(
        db.Numeric(10, 2),
        nullable=True,
    )

    # Numeric critical thresholds.
    #
    # These are intentionally separate from reference_range because
    # reference_range is primarily descriptive/display information,
    # while these values can be used for automatic CRITICAL flagging.
    critical_low = db.Column(
        db.Numeric(10, 3),
        nullable=True,
    )

    critical_high = db.Column(
        db.Numeric(10, 3),
        nullable=True,
    )

    is_active = db.Column(
        db.Boolean,
        default=True,
        nullable=False,
        index=True,
    )

    created_at = db.Column(
        db.DateTime,
        default=_utcnow,
        nullable=False,
    )

    updated_at = db.Column(
        db.DateTime,
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    orders = db.relationship(
        "LabOrderItem",
        back_populates="test",
    )

    def __repr__(self):
        return f"<LabTest {self.name}>"


class LabOrder(db.Model):
    __tablename__ = "lab_orders"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    clinic_id = db.Column(
        db.Integer,
        db.ForeignKey("clinics.id"),
        nullable=False,
        index=True,
    )

    patient_id = db.Column(
        db.Integer,
        db.ForeignKey("patients.id"),
        nullable=False,
        index=True,
    )

    consultation_id = db.Column(
        db.Integer,
        db.ForeignKey("consultations.id"),
        nullable=True,
        index=True,
    )

    ordered_by_id = db.Column(
        db.Integer,
        db.ForeignKey("staff.id"),
        nullable=False,
        index=True,
    )

    status = db.Column(
        db.Enum(LabOrderStatus),
        default=LabOrderStatus.ORDERED,
        nullable=False,
        index=True,
    )

    qr_code = db.Column(
        db.String(150),
        unique=True,
        nullable=True,
        index=True,
    )

    sample_collected_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    equipment_reference_id = db.Column(
        db.String(150),
        nullable=True,
        index=True,
    )

    # Persisted separately so cancellation reason is queryable/reportable
    # and does not exist only inside the audit log.
    cancellation_reason = db.Column(
        db.String(255),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        default=_utcnow,
        nullable=False,
    )

    updated_at = db.Column(
        db.DateTime,
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    completed_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    clinic = db.relationship(
        "Clinic",
        back_populates="lab_orders",
    )

    patient = db.relationship(
        "Patient",
        back_populates="lab_orders",
    )

    consultation = db.relationship(
        "Consultation",
        back_populates="lab_orders",
    )

    ordered_by = db.relationship(
        "Staff",
        back_populates="lab_orders",
    )

    items = db.relationship(
        "LabOrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return (
            f"<LabOrder {self.id} - "
            f"Patient {self.patient_id} "
            f"({self.status.value})>"
        )


class LabOrderItem(db.Model):
    """
    A single laboratory test within a lab order.

    Stores the result associated with that test once the laboratory
    processing is completed.
    """

    __tablename__ = "lab_order_items"

    __table_args__ = (
        db.UniqueConstraint(
            "order_id",
            "test_id",
            name="uq_lab_order_item_order_test",
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    order_id = db.Column(
        db.Integer,
        db.ForeignKey("lab_orders.id"),
        nullable=False,
        index=True,
    )

    test_id = db.Column(
        db.Integer,
        db.ForeignKey("lab_tests.id"),
        nullable=False,
        index=True,
    )

    result_value = db.Column(
        db.String(150),
        nullable=True,
    )

    flag = db.Column(
        db.Enum(LabResultFlag),
        nullable=True,
        index=True,
    )

    result_notes = db.Column(
        db.Text,
        nullable=True,
    )

    result_file_url = db.Column(
        db.String(255),
        nullable=True,
    )

    resulted_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    order = db.relationship(
        "LabOrder",
        back_populates="items",
    )

    test = db.relationship(
        "LabTest",
        back_populates="orders",
    )

    def __repr__(self):
        return (
            f"<LabOrderItem "
            f"Test {self.test_id} - "
            f"Order {self.order_id}>"
        )