from datetime import datetime, timezone

from app.core.enums.inventory_enums import (
    InventoryCategory,
    InventoryTransferStatus,
    StockMovementDirection,
    StockMovementType,
)
from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class InventoryItem(db.Model):
    __tablename__ = "inventory_items"

    id = db.Column(db.Integer, primary_key=True)

    clinic_id = db.Column(
        db.Integer,
        db.ForeignKey("clinics.id"),
        nullable=False,
        index=True,
    )

    name = db.Column(
        db.String(150),
        nullable=False,
        index=True,
    )

    category = db.Column(
        db.Enum(InventoryCategory),
        default=InventoryCategory.MEDICAL_SUPPLY,
        nullable=False,
        index=True,
    )

    sku = db.Column(
        db.String(80),
        unique=True,
        nullable=True,
        index=True,
    )

    barcode = db.Column(
        db.String(80),
        unique=True,
        nullable=True,
        index=True,
    )

    unit = db.Column(
        db.String(30),
        nullable=True,
    )

    quantity_on_hand = db.Column(
        db.Integer,
        default=0,
        nullable=False,
    )

    reorder_level = db.Column(
        db.Integer,
        default=10,
        nullable=False,
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

    clinic = db.relationship(
        "Clinic",
        back_populates="inventory_items",
    )

    batches = db.relationship(
        "InventoryBatch",
        back_populates="item",
        cascade="all, delete-orphan",
        lazy="select",
    )

    movements = db.relationship(
        "StockMovement",
        back_populates="item",
        cascade="all, delete-orphan",
        lazy="select",
    )

    outgoing_transfers = db.relationship(
        "InventoryTransfer",
        foreign_keys="InventoryTransfer.item_id",
        back_populates="item",
        lazy="select",
    )

    def __repr__(self):
        return (
            f"<InventoryItem "
            f"{self.name} "
            f"({self.quantity_on_hand} {self.unit})>"
        )


class InventorySupplier(db.Model):
    __tablename__ = "inventory_suppliers"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    # NULL means globally/shared supplier.
    # Non-null means clinic-specific supplier.
    clinic_id = db.Column(
        db.Integer,
        db.ForeignKey("clinics.id"),
        nullable=True,
        index=True,
    )

    name = db.Column(
        db.String(150),
        nullable=False,
        index=True,
    )

    contact_person = db.Column(
        db.String(120),
        nullable=True,
    )

    phone = db.Column(
        db.String(30),
        nullable=True,
    )

    email = db.Column(
        db.String(120),
        nullable=True,
    )

    address = db.Column(
        db.String(255),
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

    clinic = db.relationship(
        "Clinic",
        back_populates="inventory_suppliers",
    )

    items = db.relationship(
        "InventoryBatch",
        foreign_keys="InventoryBatch.supplier_id",
        back_populates="supplier",
        lazy="select",
    )

    drug_batches = db.relationship(
        "DrugBatch",
        back_populates="supplier",
        lazy="select",
    )

    def __repr__(self):
        return f"<InventorySupplier {self.name}>"


class InventoryBatch(db.Model):
    __tablename__ = "inventory_batches"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    item_id = db.Column(
        db.Integer,
        db.ForeignKey("inventory_items.id"),
        nullable=False,
        index=True,
    )

    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey("inventory_suppliers.id"),
        nullable=True,
        index=True,
    )

    batch_number = db.Column(
        db.String(100),
        nullable=False,
        index=True,
    )

    quantity_on_hand = db.Column(
        db.Integer,
        default=0,
        nullable=False,
    )

    unit_cost = db.Column(
        db.Numeric(12, 2),
        nullable=True,
    )

    expiry_date = db.Column(
        db.Date,
        nullable=True,
        index=True,
    )

    received_at = db.Column(
        db.DateTime,
        default=_utcnow,
        nullable=False,
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

    item = db.relationship(
        "InventoryItem",
        back_populates="batches",
    )

    supplier = db.relationship(
        "InventorySupplier",
        foreign_keys=[supplier_id],
        back_populates="items",
    )

    movements = db.relationship(
        "StockMovement",
        back_populates="batch",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self):
        return (
            f"<InventoryBatch "
            f"{self.batch_number} "
            f"Item={self.item_id} "
            f"Qty={self.quantity_on_hand}>"
        )


class StockMovement(db.Model):
    __tablename__ = "stock_movements"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    item_id = db.Column(
        db.Integer,
        db.ForeignKey("inventory_items.id"),
        nullable=False,
        index=True,
    )

    batch_id = db.Column(
        db.Integer,
        db.ForeignKey("inventory_batches.id"),
        nullable=True,
        index=True,
    )

    movement_type = db.Column(
        db.Enum(StockMovementType),
        nullable=False,
        index=True,
    )

    direction = db.Column(
        db.Enum(StockMovementDirection),
        nullable=False,
        index=True,
    )

    quantity = db.Column(
        db.Integer,
        nullable=False,
    )

    reason = db.Column(
        db.String(255),
        nullable=True,
    )

    performed_by_id = db.Column(
        db.Integer,
        db.ForeignKey("staff.id"),
        nullable=False,
        index=True,
    )

    reference_type = db.Column(
        db.String(50),
        nullable=True,
        index=True,
    )

    reference_id = db.Column(
        db.Integer,
        nullable=True,
        index=True,
    )

    created_at = db.Column(
        db.DateTime,
        default=_utcnow,
        nullable=False,
        index=True,
    )

    item = db.relationship(
        "InventoryItem",
        back_populates="movements",
    )

    batch = db.relationship(
        "InventoryBatch",
        back_populates="movements",
    )

    performed_by = db.relationship(
        "Staff",
        back_populates="stock_movements",
    )

    def __repr__(self):
        return (
            f"<StockMovement "
            f"{self.movement_type.value} "
            f"{self.direction.value} "
            f"{self.quantity} "
            f"Item={self.item_id}>"
        )


class InventoryTransfer(db.Model):
    __tablename__ = "inventory_transfers"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    item_id = db.Column(
        db.Integer,
        db.ForeignKey("inventory_items.id"),
        nullable=False,
        index=True,
    )

    batch_id = db.Column(
        db.Integer,
        db.ForeignKey("inventory_batches.id"),
        nullable=True,
        index=True,
    )

    source_clinic_id = db.Column(
        db.Integer,
        db.ForeignKey("clinics.id"),
        nullable=False,
        index=True,
    )

    destination_clinic_id = db.Column(
        db.Integer,
        db.ForeignKey("clinics.id"),
        nullable=False,
        index=True,
    )

    quantity = db.Column(
        db.Integer,
        nullable=False,
    )

    status = db.Column(
        db.Enum(InventoryTransferStatus),
        default=InventoryTransferStatus.PENDING,
        nullable=False,
        index=True,
    )

    reason = db.Column(
        db.String(255),
        nullable=True,
    )

    requested_by_id = db.Column(
        db.Integer,
        db.ForeignKey("staff.id"),
        nullable=False,
        index=True,
    )

    approved_by_id = db.Column(
        db.Integer,
        db.ForeignKey("staff.id"),
        nullable=True,
        index=True,
    )

    requested_at = db.Column(
        db.DateTime,
        default=_utcnow,
        nullable=False,
    )

    approved_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    completed_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    cancelled_at = db.Column(
        db.DateTime,
        nullable=True,
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

    item = db.relationship(
        "InventoryItem",
        foreign_keys=[item_id],
        back_populates="outgoing_transfers",
    )

    batch = db.relationship(
        "InventoryBatch",
        foreign_keys=[batch_id],
    )

    source_clinic = db.relationship(
        "Clinic",
        foreign_keys=[source_clinic_id],
    )

    destination_clinic = db.relationship(
        "Clinic",
        foreign_keys=[destination_clinic_id],
    )

    requested_by = db.relationship(
        "Staff",
        foreign_keys=[requested_by_id],
    )

    approved_by = db.relationship(
        "Staff",
        foreign_keys=[approved_by_id],
    )

    def __repr__(self):
        return (
            f"<InventoryTransfer "
            f"{self.source_clinic_id} -> "
            f"{self.destination_clinic_id} "
            f"Item={self.item_id} "
            f"Qty={self.quantity} "
            f"Status={self.status.value}>"
        )