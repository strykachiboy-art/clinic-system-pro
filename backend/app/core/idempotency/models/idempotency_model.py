from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IdempotencyRecord(db.Model):
    __tablename__ = "idempotency_records"

    __table_args__ = (
        db.UniqueConstraint(
            "clinic_id",
            "user_id",
            "operation",
            "idempotency_key",
            name="uq_idempotency_records_scope",
        ),
        db.Index(
            "ix_idempotency_records_clinic_operation_created",
            "clinic_id",
            "operation",
            "created_at",
            "id",
        ),
    )

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

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    operation = db.Column(
        db.String(120),
        nullable=False,
    )

    idempotency_key = db.Column(
        db.String(255),
        nullable=False,
    )

    request_hash = db.Column(
        db.String(64),
        nullable=False,
    )

    entity_type = db.Column(
        db.String(80),
        nullable=True,
    )

    entity_id = db.Column(
        db.Integer,
        nullable=True,
    )

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

    clinic = db.relationship(
        "Clinic",
    )

    user = db.relationship(
        "User",
    )

    def __repr__(self) -> str:
        return (
            f"<IdempotencyRecord "
            f"{self.operation}:{self.idempotency_key}>"
        )
