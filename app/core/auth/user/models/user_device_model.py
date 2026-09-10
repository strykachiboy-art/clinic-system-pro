from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserDevice(db.Model):
    __tablename__ = "user_devices"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    device_token = db.Column(
        db.String(500),
        nullable=False,
        unique=True,
        index=True,
    )

    device_name = db.Column(
        db.String(100),
        nullable=True,
    )

    platform = db.Column(
        db.String(20),
        nullable=False,
        index=True,
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    last_seen_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=_utcnow,
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    user = db.relationship(
        "User",
        back_populates="devices",
    )

    def __repr__(self) -> str:
        return (
            f"<UserDevice "
            f"id={self.id} "
            f"user_id={self.user_id} "
            f"platform={self.platform!r} "
            f"device_name={self.device_name!r} "
            f"is_active={self.is_active}>"
        )