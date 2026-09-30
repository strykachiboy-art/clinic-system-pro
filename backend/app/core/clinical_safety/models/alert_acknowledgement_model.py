from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Index, UniqueConstraint

from app.core.enums.clinical_safety_enums import (
    AlertAcknowledgementType,
)
from app.extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AlertAcknowledgement(db.Model):
    __tablename__ = "alert_acknowledgements"

    __table_args__ = (
        UniqueConstraint(
            "alert_id",
            "acknowledged_by_user_id",
            "acknowledgement_type",
            name="uq_alert_acknowledgement_actor_type",
        ),
        Index(
            "ix_alert_acknowledgements_alert_created",
            "alert_id",
            "acknowledged_at",
            "id",
        ),
        Index(
            "ix_alert_acknowledgements_user_created",
            "acknowledged_by_user_id",
            "acknowledged_at",
            "id",
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    alert_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "clinical_alerts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    acknowledged_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    acknowledgement_type = db.Column(
        db.Enum(AlertAcknowledgementType),
        nullable=False,
        index=True,
    )

    justification = db.Column(
        db.Text,
        nullable=True,
    )

    acknowledged_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        index=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    def __repr__(self) -> str:
        return (
            f"<AlertAcknowledgement "
            f"Alert {self.alert_id} "
            f"User {self.acknowledged_by_user_id} "
            f"({self.acknowledgement_type.value})>"
        )