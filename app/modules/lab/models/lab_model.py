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
        db.CheckConstraint(
            "price IS NULL OR price >= 0",
            name="ck_lab_tests_price_non_negative",
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    # NULL = global/shared laboratory test.
    # Non-NULL = clinic-specific laboratory test.
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
    # These are separate from reference_range because
    # reference_range is descriptive/display information,
    # while these values can be used for automatic
    # CRITICAL flagging.
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

    __table_args__ = (
        # ---------------------------------------------------------
        # Collection timestamp integrity
        # ---------------------------------------------------------
        db.CheckConstraint(
            "sample_collected_at IS NULL "
            "OR sample_collected_at >= created_at",
            name="ck_lab_orders_sample_collected_after_created",
        ),

        # ---------------------------------------------------------
        # Processing timestamp integrity
        # ---------------------------------------------------------
        db.CheckConstraint(
            "processed_at IS NULL "
            "OR processed_at >= created_at",
            name="ck_lab_orders_processed_after_created",
        ),

        db.CheckConstraint(
            "processed_at IS NULL "
            "OR sample_collected_at IS NULL "
            "OR processed_at >= sample_collected_at",
            name="ck_lab_orders_processed_after_sample",
        ),

        # ---------------------------------------------------------
        # Verification timestamp integrity
        # ---------------------------------------------------------
        db.CheckConstraint(
            "verified_at IS NULL "
            "OR verified_at >= created_at",
            name="ck_lab_orders_verified_after_created",
        ),

        db.CheckConstraint(
            "verified_at IS NULL "
            "OR processed_at IS NULL "
            "OR verified_at >= processed_at",
            name="ck_lab_orders_verified_after_processed",
        ),

        # ---------------------------------------------------------
        # Completion timestamp integrity
        # ---------------------------------------------------------
        db.CheckConstraint(
            "completed_at IS NULL "
            "OR completed_at >= created_at",
            name="ck_lab_orders_completed_after_created",
        ),

        db.CheckConstraint(
            "completed_at IS NULL "
            "OR sample_collected_at IS NULL "
            "OR completed_at >= sample_collected_at",
            name="ck_lab_orders_completed_after_sample",
        ),

        db.CheckConstraint(
            "completed_at IS NULL "
            "OR processed_at IS NULL "
            "OR completed_at >= processed_at",
            name="ck_lab_orders_completed_after_processed",
        ),

        db.CheckConstraint(
            "completed_at IS NULL "
            "OR verified_at IS NULL "
            "OR completed_at >= verified_at",
            name="ck_lab_orders_completed_after_verified",
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    # -------------------------------------------------------------
    # Tenant ownership
    # -------------------------------------------------------------

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

    # -------------------------------------------------------------
    # Clinical actors
    #
    # These are populated by the service from the authenticated
    # user's Staff record. They must NOT come from the request body.
    # -------------------------------------------------------------

    ordered_by_id = db.Column(
        db.Integer,
        db.ForeignKey("staff.id"),
        nullable=False,
        index=True,
    )

    collected_by_id = db.Column(
        db.Integer,
        db.ForeignKey("staff.id"),
        nullable=True,
        index=True,
    )

    processed_by_id = db.Column(
        db.Integer,
        db.ForeignKey("staff.id"),
        nullable=True,
        index=True,
    )

    verified_by_id = db.Column(
        db.Integer,
        db.ForeignKey("staff.id"),
        nullable=True,
        index=True,
    )

    # -------------------------------------------------------------
    # Order lifecycle
    # -------------------------------------------------------------

    status = db.Column(
        db.Enum(LabOrderStatus),
        default=LabOrderStatus.ORDERED,
        nullable=False,
        index=True,
    )

    # Unique QR identifier used to identify the order during
    # specimen collection/workflow.
    qr_code = db.Column(
        db.String(150),
        unique=True,
        nullable=True,
        index=True,
    )

    # -------------------------------------------------------------
    # Collection
    # -------------------------------------------------------------

    sample_collected_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    # -------------------------------------------------------------
    # Processing
    # -------------------------------------------------------------

    processed_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    # -------------------------------------------------------------
    # Verification
    # -------------------------------------------------------------

    verified_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    # -------------------------------------------------------------
    # Equipment
    # -------------------------------------------------------------

    equipment_reference_id = db.Column(
        db.String(150),
        nullable=True,
        index=True,
    )

    # -------------------------------------------------------------
    # Cancellation
    # -------------------------------------------------------------

    # Persisted separately so cancellation reason is
    # queryable/reportable and not stored only in audit logs.
    cancellation_reason = db.Column(
        db.String(255),
        nullable=True,
    )

    # -------------------------------------------------------------
    # Timestamps
    # -------------------------------------------------------------

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

    # -------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------

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

    # Multiple foreign keys point to Staff, so foreign_keys must
    # be explicit to avoid SQLAlchemy relationship ambiguity.
    ordered_by = db.relationship(
        "Staff",
        foreign_keys=[ordered_by_id],
        back_populates="lab_orders",
    )

    collected_by = db.relationship(
        "Staff",
        foreign_keys=[collected_by_id],
    )

    processed_by = db.relationship(
        "Staff",
        foreign_keys=[processed_by_id],
    )

    verified_by = db.relationship(
        "Staff",
        foreign_keys=[verified_by_id],
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

    Stores the result associated with that test once
    laboratory processing is completed.
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