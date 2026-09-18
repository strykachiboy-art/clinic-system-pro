from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AssetAssignment(db.Model):
    __tablename__ = "asset_assignments"

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

    staff_id: Mapped[int] = mapped_column(
        ForeignKey("staff.id"),
        nullable=False,
        index=True,
    )

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        index=True,
    )

    returned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    assigned_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    returned_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
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
        back_populates="assignments",
    )

    staff = relationship(
        "Staff",
    )

    assigned_by_user = relationship(
        "User",
        foreign_keys=[assigned_by_user_id],
    )

    returned_by_user = relationship(
        "User",
        foreign_keys=[returned_by_user_id],
    )

    __table_args__ = (
        CheckConstraint(
            "returned_at IS NULL OR returned_at >= assigned_at",
            name="ck_asset_assignments_returned_after_assigned",
        ),
        Index(
            "ix_asset_assignments_clinic_asset_assigned",
            "clinic_id",
            "asset_id",
            "assigned_at",
        ),
        Index(
            "ix_asset_assignments_clinic_staff_assigned",
            "clinic_id",
            "staff_id",
            "assigned_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AssetAssignment id={self.id} "
            f"asset_id={self.asset_id} "
            f"staff_id={self.staff_id}>"
        )