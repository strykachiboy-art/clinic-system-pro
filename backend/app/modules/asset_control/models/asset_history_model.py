from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.core.enums.asset_enums import (
    AssetCondition,
    AssetHistoryEventType,
    AssetStatus,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AssetHistory(db.Model):
    __tablename__ = "asset_history"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    clinic_id: Mapped[int] = mapped_column(
        ForeignKey("clinics.id"),
        nullable=False,
        index=True,
    )

    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id"),
        nullable=False,
        index=True,
    )

    event_type: Mapped[AssetHistoryEventType] = mapped_column(
        db.Enum(
            AssetHistoryEventType,
            name="asset_history_event_type",
        ),
        nullable=False,
        index=True,
    )

    previous_status: Mapped[AssetStatus | None] = mapped_column(
        db.Enum(
            AssetStatus,
            name="asset_status",
        ),
        nullable=True,
    )

    new_status: Mapped[AssetStatus | None] = mapped_column(
        db.Enum(
            AssetStatus,
            name="asset_status",
        ),
        nullable=True,
    )

    previous_condition: Mapped[AssetCondition | None] = mapped_column(
        db.Enum(
            AssetCondition,
            name="asset_condition",
        ),
        nullable=True,
    )

    new_condition: Mapped[AssetCondition | None] = mapped_column(
        db.Enum(
            AssetCondition,
            name="asset_condition",
        ),
        nullable=True,
    )

    previous_assigned_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff.id"),
        nullable=True,
        index=True,
    )

    new_assigned_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff.id"),
        nullable=True,
        index=True,
    )

    previous_location: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    new_location: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    event_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        index=True,
    )

    reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    event_metadata: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )

    asset = relationship(
        "Asset",
        back_populates="history",
    )

    clinic = relationship(
        "Clinic",
    )

    actor_user = relationship(
        "User",
        foreign_keys=[actor_user_id],
    )

    previous_assigned_to = relationship(
        "Staff",
        foreign_keys=[previous_assigned_to_id],
    )

    new_assigned_to = relationship(
        "Staff",
        foreign_keys=[new_assigned_to_id],
    )

    __table_args__ = (
        Index(
            "ix_asset_history_clinic_asset_event",
            "clinic_id",
            "asset_id",
            "event_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AssetHistory id={self.id} "
            f"asset_id={self.asset_id} "
            f"event_type={self.event_type.value!r}>"
        )