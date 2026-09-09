from datetime import datetime, timezone
from decimal import Decimal

from app.extensions import db

from app.core.enums.ai_enums import (
    AIFeature,
    AIRiskLevel,
    AIApprovalStatus,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AILog(db.Model):
    __tablename__ = "ai_logs"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    # ================================================================
    # OWNERSHIP / TENANT ISOLATION
    # ================================================================

    clinic_id = db.Column(
        db.Integer,
        db.ForeignKey("clinics.id"),
        nullable=False,
        index=True,
    )

    patient_id = db.Column(
        db.Integer,
        db.ForeignKey("patients.id"),
        nullable=True,
        index=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    # ================================================================
    # AI FEATURE
    # ================================================================

    feature_used = db.Column(
        db.Enum(AIFeature),
        nullable=False,
        index=True,
    )

    risk_level = db.Column(
        db.Enum(AIRiskLevel),
        nullable=False,
        default=AIRiskLevel.LOW,
        index=True,
    )

    # ================================================================
    # AI PROVENANCE
    # ================================================================

    model = db.Column(
        db.String(100),
        nullable=False,
    )

    model_version = db.Column(
        db.String(100),
        nullable=True,
    )

    input_context_version = db.Column(
        db.String(100),
        nullable=False,
        default="v1",
    )

    generated_by_system = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    # ================================================================
    # AI INPUT / OUTPUT
    # ================================================================

    input_data = db.Column(
        db.JSON,
        nullable=True,
    )

    output_data = db.Column(
        db.JSON,
        nullable=True,
    )

    # ================================================================
    # REVIEW STATE
    # ================================================================

    approval_status = db.Column(
        db.Enum(AIApprovalStatus),
        nullable=False,
        default=AIApprovalStatus.PENDING,
        index=True,
    )

    # ================================================================
    # USAGE / COST MONITORING
    # ================================================================

    credits_used = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    input_tokens = db.Column(
        db.Integer,
        nullable=True,
    )

    output_tokens = db.Column(
        db.Integer,
        nullable=True,
    )

    total_tokens = db.Column(
        db.Integer,
        nullable=True,
    )

    estimated_cost = db.Column(
        db.Numeric(12, 6),
        nullable=True,
    )

    cost_currency = db.Column(
        db.String(10),
        nullable=True,
    )

    # ================================================================
    # TIMESTAMPS
    # ================================================================

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
        index=True,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    # ================================================================
    # RELATIONSHIPS
    # ================================================================

    clinic = db.relationship(
        "Clinic",
        back_populates="ai_logs",
    )

    patient = db.relationship(
        "Patient",
        back_populates="ai_logs",
    )

    user = db.relationship(
        "User",
        back_populates="ai_logs",
    )

    reviews = db.relationship(
        "AIReview",
        back_populates="ai_log",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def __repr__(self):
        return (
            f"<AILog id={self.id} "
            f"feature={self.feature_used.value} "
            f"risk={self.risk_level.value} "
            f"status={self.approval_status.value} "
            f"clinic_id={self.clinic_id} "
            f"patient_id={self.patient_id} "
            f"user_id={self.user_id}>"
        )


class AIReview(db.Model):
    __tablename__ = "ai_reviews"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    # ================================================================
    # AI RESULT
    # ================================================================

    ai_log_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "ai_logs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # ================================================================
    # REVIEWER
    # ================================================================

    reviewer_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    # ================================================================
    # REVIEW DECISION
    # ================================================================

    status = db.Column(
        db.Enum(AIApprovalStatus),
        nullable=False,
        index=True,
    )

    review_notes = db.Column(
        db.Text,
        nullable=True,
    )

    reviewed_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        index=True,
    )

    # ================================================================
    # TIMESTAMPS
    # ================================================================

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    # ================================================================
    # RELATIONSHIPS
    # ================================================================

    ai_log = db.relationship(
        "AILog",
        back_populates="reviews",
    )

    reviewer = db.relationship(
        "User",
        back_populates="ai_reviews",
        foreign_keys=[reviewer_id],
    )

    def __repr__(self):
        return (
            f"<AIReview id={self.id} "
            f"ai_log_id={self.ai_log_id} "
            f"reviewer_id={self.reviewer_id} "
            f"status={self.status.value}>"
        )