from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.core.enums.asset_enums import MaintenanceStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AssetMaintenance(db.Model):
    __tablename__ = "asset_maintenance"

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

    status: Mapped[MaintenanceStatus] = mapped_column(
        db.Enum(
            MaintenanceStatus,
            name="maintenance_status",
        ),
        nullable=False,
        default=MaintenanceStatus.SCHEDULED,
        index=True,
    )

    scheduled_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    performed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    cost: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    clinic = relationship(
        "Clinic",
    )

    asset = relationship(
        "Asset",
        back_populates="maintenance_records",
    )

    performed_by_user = relationship(
        "User",
        foreign_keys=[performed_by_user_id],
    )

    __table_args__ = (
        CheckConstraint(
            "cost IS NULL OR cost >= 0",
            name="ck_asset_maintenance_cost_non_negative",
        ),
        CheckConstraint(
            "completed_at IS NULL OR "
            "started_at IS NULL OR "
            "completed_at >= started_at",
            name="ck_asset_maintenance_completed_after_started",
        ),
        Index(
            "ix_asset_maintenance_clinic_asset_scheduled",
            "clinic_id",
            "asset_id",
            "scheduled_date",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AssetMaintenance id={self.id} "
            f"asset_id={self.asset_id} "
            f"status={self.status.value!r}>"
        )