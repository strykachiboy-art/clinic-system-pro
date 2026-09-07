from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db

from app.core.enums.audit_enums import AuditAction


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    action = db.Column(
        db.Enum(AuditAction),
        nullable=False,
        index=True,
    )

    entity_type = db.Column(
        db.String(80),
        nullable=False,
        index=True,
    )

    entity_id = db.Column(
        db.Integer,
        nullable=False,
        index=True,
    )

    description = db.Column(
        db.String(255),
        nullable=True,
    )

    old_value = db.Column(
        db.JSON,
        nullable=True,
    )

    new_value = db.Column(
        db.JSON,
        nullable=True,
    )

    ip_address = db.Column(
        db.String(45),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
        index=True,
    )

    user = db.relationship(
        "User",
        back_populates="audit_logs",
    )

    def __repr__(self):
        return (
            f"<AuditLog "
            f"{self.action.value} "
            f"{self.entity_type}#{self.entity_id}>"
        )