from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    CheckConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.core.enums.asset_enums import (
    AssetCategory,
    AssetCondition,
    AssetOwnership,
    AssetStatus,
    MaintenanceStatus,
)


class Asset(db.Model):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    clinic_id: Mapped[int] = mapped_column(
        ForeignKey("clinics.id"),
        nullable=False,
        index=True,
    )

    asset_tag: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    category: Mapped[AssetCategory] = mapped_column(
        db.Enum(
            AssetCategory,
            name="asset_category",
        ),
        nullable=False,
        index=True,
    )

    status: Mapped[AssetStatus] = mapped_column(
        db.Enum(
            AssetStatus,
            name="asset_status",
        ),
        nullable=False,
        default=AssetStatus.ACTIVE,
        index=True,
    )

    condition: Mapped[AssetCondition] = mapped_column(
        db.Enum(
            AssetCondition,
            name="asset_condition",
        ),
        nullable=False,
        default=AssetCondition.GOOD,
        index=True,
    )

    ownership: Mapped[AssetOwnership] = mapped_column(
        db.Enum(
            AssetOwnership,
            name="asset_ownership",
        ),
        nullable=False,
        default=AssetOwnership.CLINIC,
        index=True,
    )

    location: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    assigned_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff.id"),
        nullable=True,
        index=True,
    )

    serial_number: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
        index=True,
    )

    manufacturer: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    model_number: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    purchase_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    purchase_cost: Mapped[float | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
    )

    supplier: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    warranty_expiry: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    maintenance_status: Mapped[MaintenanceStatus] = mapped_column(
        db.Enum(
            MaintenanceStatus,
            name="maintenance_status",
        ),
        nullable=False,
        default=MaintenanceStatus.NOT_REQUIRED,
        index=True,
    )

    last_maintenance_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    next_maintenance_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )

    retirement_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    disposal_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    disposal_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    clinic = relationship(
        "Clinic",
        back_populates="assets",
    )

    assigned_to = relationship(
        "Staff",
        foreign_keys=[assigned_to_id],
    )

    __table_args__ = (
        CheckConstraint(
            "purchase_cost IS NULL OR purchase_cost >= 0",
            name="ck_assets_purchase_cost_non_negative",
        ),
        CheckConstraint(
            "retirement_date IS NULL OR "
            "purchase_date IS NULL OR "
            "retirement_date >= purchase_date",
            name="ck_assets_retirement_after_purchase",
        ),
        CheckConstraint(
            "disposal_date IS NULL OR "
            "retirement_date IS NULL OR "
            "disposal_date >= retirement_date",
            name="ck_assets_disposal_after_retirement",
        ),
        Index(
            "ix_assets_clinic_asset_tag",
            "clinic_id",
            "asset_tag",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Asset id={self.id} "
            f"asset_tag={self.asset_tag!r} "
            f"name={self.name!r}>"
        )