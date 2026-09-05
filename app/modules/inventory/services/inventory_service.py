from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.extensions import db

from app.core.audit.services.audit_service import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.clinic_enums import ClinicStatus
from app.core.enums.inventory_enums import (
    DECREASING_MOVEMENTS,
    INCREASING_MOVEMENTS,
    InventoryCategory,
    InventoryTransferStatus,
    StockMovementDirection,
    StockMovementType,
)
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import transactional

from app.modules.clinic.models.clinic_model import Clinic
from app.modules.inventory.models.inventory_model import (
    InventoryBatch,
    InventoryItem,
    InventorySupplier,
    InventoryTransfer,
    StockMovement,
)
from app.modules.staff.models.staff_model import Staff


# ============================================================================
# CONSTANTS
# ============================================================================

_ITEM_EDITABLE_FIELDS = {
    "name",
    "category",
    "sku",
    "barcode",
    "unit",
    "reorder_level",
}

_SUPPLIER_EDITABLE_FIELDS = {
    "name",
    "contact_person",
    "phone",
    "email",
    "address",
}

_BATCH_EDITABLE_FIELDS = {
    "batch_number",
    "unit_cost",
    "expiry_date",
    "supplier_id",
}


# ============================================================================
# HELPERS
# ============================================================================

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_enum(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValidationError("Expected a string value")

    value = value.strip()

    return value or None


def _validate_positive_quantity(quantity: int) -> None:
    if not isinstance(quantity, int):
        raise ValidationError("Quantity must be an integer")

    if quantity <= 0:
        raise ValidationError("Quantity must be greater than zero")


def _validate_non_negative(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise ValidationError(f"{field_name} must be an integer")

    if value < 0:
        raise ValidationError(f"{field_name} cannot be negative")


def _get_active_clinic(clinic_id: int) -> Clinic:
    clinic = db.session.get(Clinic, clinic_id)

    if clinic is None:
        raise NotFoundError(f"Clinic {clinic_id} not found")

    if clinic.status != ClinicStatus.ACTIVE:
        raise ConflictError(f"Clinic {clinic_id} is inactive")

    return clinic


def _ensure_same_clinic(
    *,
    expected_clinic_id: int,
    actual_clinic_id: int | None,
    resource_name: str,
) -> None:
    if actual_clinic_id != expected_clinic_id:
        raise ValidationError(
            f"{resource_name} does not belong to clinic {expected_clinic_id}"
        )


def _get_staff(staff_id: int) -> Staff:
    staff = db.session.get(Staff, staff_id)

    if staff is None:
        raise NotFoundError(f"Staff {staff_id} not found")

    return staff


def _validate_staff_for_clinic(
    *,
    staff_id: int,
    clinic_id: int,
) -> Staff:
    staff = _get_staff(staff_id)

    if staff.clinic_id != clinic_id:
        raise ValidationError(
            f"Staff {staff_id} does not belong to clinic {clinic_id}"
        )

    if staff.status != StaffStatus.ACTIVE:
        raise ConflictError(f"Staff {staff_id} is inactive")

    return staff


def _get_item(item_id: int) -> InventoryItem:
    item = db.session.get(InventoryItem, item_id)

    if item is None:
        raise NotFoundError(f"Inventory item {item_id} not found")

    return item


def _get_active_item(item_id: int) -> InventoryItem:
    item = _get_item(item_id)

    if not item.is_active:
        raise ConflictError(f"Inventory item {item_id} is inactive")

    return item


def _validate_item_clinic(
    item: InventoryItem,
    clinic_id: int | None,
) -> InventoryItem:
    if clinic_id is not None:
        _ensure_same_clinic(
            expected_clinic_id=clinic_id,
            actual_clinic_id=item.clinic_id,
            resource_name=f"Inventory item {item.id}",
        )

    return item


def _get_supplier(supplier_id: int) -> InventorySupplier:
    supplier = db.session.get(InventorySupplier, supplier_id)

    if supplier is None:
        raise NotFoundError(f"Inventory supplier {supplier_id} not found")

    return supplier


def _validate_supplier_for_clinic(
    supplier: InventorySupplier,
    clinic_id: int,
) -> None:
    # Global suppliers are allowed.
    if supplier.clinic_id is not None and supplier.clinic_id != clinic_id:
        raise ValidationError(
            f"Supplier {supplier.id} does not belong to clinic {clinic_id}"
        )


def _get_batch(batch_id: int) -> InventoryBatch:
    batch = db.session.get(InventoryBatch, batch_id)

    if batch is None:
        raise NotFoundError(f"Inventory batch {batch_id} not found")

    return batch


def _validate_batch_for_item(
    *,
    batch: InventoryBatch,
    item: InventoryItem,
) -> None:
    if batch.item_id != item.id:
        raise ValidationError(
            f"Batch {batch.id} does not belong to inventory item {item.id}"
        )


def _validate_batch_active(batch: InventoryBatch) -> None:
    if not batch.is_active:
        raise ConflictError(f"Inventory batch {batch.id} is inactive")


def _validate_batch_expiry(expiry_date: date | None) -> None:
    if expiry_date is not None and expiry_date < date.today():
        raise ValidationError("Expiry date cannot be in the past")


def _audit_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    return value


def _build_change_dict(
    old_values: dict[str, Any],
    new_values: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    old_value = {
        key: _audit_value(value)
        for key, value in old_values.items()
    }

    new_value = {
        key: _audit_value(value)
        for key, value in new_values.items()
    }

    return old_value, new_value


# ============================================================================
# INVENTORY ITEMS
# ============================================================================

def get_inventory_item(
    item_id: int,
    clinic_id: int | None = None,
) -> InventoryItem:
    item = _get_item(item_id)

    _validate_item_clinic(item, clinic_id)

    return item


def list_inventory_items(
    clinic_id: int,
    category: InventoryCategory | None = None,
    low_stock_only: bool = False,
    include_inactive: bool = False,
) -> list[InventoryItem]:
    _get_active_clinic(clinic_id)

    query = InventoryItem.query.filter_by(clinic_id=clinic_id)

    if not include_inactive:
        query = query.filter_by(is_active=True)

    if category is not None:
        query = query.filter_by(category=category)

    if low_stock_only:
        query = query.filter(
            InventoryItem.quantity_on_hand <= InventoryItem.reorder_level
        )

    return query.order_by(InventoryItem.name.asc()).all()


def get_low_stock_items(clinic_id: int) -> list[InventoryItem]:
    return list_inventory_items(
        clinic_id=clinic_id,
        low_stock_only=True,
        include_inactive=False,
    )


@transactional
def create_inventory_item(
    clinic_id: int,
    name: str,
    category: InventoryCategory = InventoryCategory.MEDICAL_SUPPLY,
    initial_quantity: int = 0,
    performed_by_id: int | None = None,
    **fields,
) -> InventoryItem:
    _get_active_clinic(clinic_id)

    if not name or not name.strip():
        raise ValidationError("Inventory item name is required")

    _validate_non_negative(initial_quantity, "Initial quantity")

    unknown = set(fields) - _ITEM_EDITABLE_FIELDS

    if unknown:
        raise ValidationError(
            f"Unknown inventory item field(s): {', '.join(sorted(unknown))}"
        )

    if "name" in fields:
        fields["name"] = _normalize_optional_text(fields["name"])

    if fields.get("name") is not None:
        name = fields.pop("name")

    if not name:
        raise ValidationError("Inventory item name is required")

    sku = fields.get("sku")
    barcode = fields.get("barcode")

    if sku:
        sku = sku.strip()

        existing = InventoryItem.query.filter_by(sku=sku).first()

        if existing:
            raise ConflictError(
                f"SKU '{sku}' is already assigned to inventory item {existing.id}"
            )

        fields["sku"] = sku

    if barcode:
        barcode = barcode.strip()

        existing = InventoryItem.query.filter_by(barcode=barcode).first()

        if existing:
            raise ConflictError(
                f"Barcode '{barcode}' is already assigned to inventory item {existing.id}"
            )

        fields["barcode"] = barcode

    if "reorder_level" in fields:
        _validate_non_negative(
            fields["reorder_level"],
            "Reorder level",
        )

    item = InventoryItem(
        clinic_id=clinic_id,
        name=name.strip(),
        category=category,
        quantity_on_hand=initial_quantity,
        **fields,
    )

    db.session.add(item)
    db.session.flush()

    if initial_quantity > 0:
        if performed_by_id is None:
            raise ValidationError(
                "performed_by_id is required when initial_quantity is greater than zero"
            )

        _validate_staff_for_clinic(
            staff_id=performed_by_id,
            clinic_id=clinic_id,
        )

        movement = StockMovement(
            item_id=item.id,
            movement_type=StockMovementType.RESTOCK,
            direction=StockMovementDirection.IN,
            quantity=initial_quantity,
            reason="Initial inventory quantity",
            performed_by_id=performed_by_id,
            reference_type="inventory_item",
            reference_id=item.id,
        )

        db.session.add(movement)
        db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="InventoryItem",
        entity_id=item.id,
        description=f"Inventory item '{item.name}' created",
        new_value={
            "clinic_id": clinic_id,
            "quantity_on_hand": initial_quantity,
        },
    )

    return item


@transactional
def update_inventory_item(
    item_id: int,
    clinic_id: int | None = None,
    **fields,
) -> InventoryItem:
    item = get_inventory_item(item_id, clinic_id)

    unknown = set(fields) - _ITEM_EDITABLE_FIELDS

    if unknown:
        raise ValidationError(
            f"Unknown inventory item field(s): {', '.join(sorted(unknown))}"
        )

    old_values = {}
    new_values = {}

    for key, new_value in fields.items():
        if key == "name":
            new_value = _normalize_optional_text(new_value)

            if not new_value:
                raise ValidationError("Inventory item name cannot be empty")

        if key in {"sku", "barcode", "unit"}:
            new_value = _normalize_optional_text(new_value)

        if key == "reorder_level":
            _validate_non_negative(new_value, "Reorder level")

        current_value = getattr(item, key)

        if current_value == new_value:
            continue

        if key == "sku" and new_value:
            existing = InventoryItem.query.filter(
                InventoryItem.sku == new_value,
                InventoryItem.id != item.id,
            ).first()

            if existing:
                raise ConflictError(
                    f"SKU '{new_value}' is already assigned to inventory item {existing.id}"
                )

        if key == "barcode" and new_value:
            existing = InventoryItem.query.filter(
                InventoryItem.barcode == new_value,
                InventoryItem.id != item.id,
            ).first()

            if existing:
                raise ConflictError(
                    f"Barcode '{new_value}' is already assigned to inventory item {existing.id}"
                )

        old_values[key] = current_value
        new_values[key] = new_value

        setattr(item, key, new_value)

    if new_values:
        old_value, new_value = _build_change_dict(
            old_values,
            new_values,
        )

        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="InventoryItem",
            entity_id=item.id,
            description=f"Inventory item '{item.name}' updated",
            old_value=old_value,
            new_value=new_value,
        )

    return item


@transactional
def deactivate_inventory_item(
    item_id: int,
    clinic_id: int | None = None,
) -> InventoryItem:
    item = get_inventory_item(item_id, clinic_id)

    if not item.is_active:
        return item

    item.is_active = False

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="InventoryItem",
        entity_id=item.id,
        description=f"Inventory item '{item.name}' deactivated",
        old_value={"is_active": True},
        new_value={"is_active": False},
    )

    return item


@transactional
def reactivate_inventory_item(
    item_id: int,
    clinic_id: int | None = None,
) -> InventoryItem:
    item = get_inventory_item(item_id, clinic_id)

    if item.is_active:
        return item

    _get_active_clinic(item.clinic_id)

    item.is_active = True

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="InventoryItem",
        entity_id=item.id,
        description=f"Inventory item '{item.name}' reactivated",
        old_value={"is_active": False},
        new_value={"is_active": True},
    )

    return item


# ============================================================================
# SUPPLIERS
# ============================================================================

def get_supplier(
    supplier_id: int,
    clinic_id: int | None = None,
) -> InventorySupplier:
    supplier = _get_supplier(supplier_id)

    if clinic_id is not None:
        _validate_supplier_for_clinic(
            supplier,
            clinic_id,
        )

    return supplier


def list_suppliers(
    clinic_id: int | None = None,
    include_inactive: bool = False,
) -> list[InventorySupplier]:
    query = InventorySupplier.query

    if clinic_id is not None:
        query = query.filter(
            db.or_(
                InventorySupplier.clinic_id == clinic_id,
                InventorySupplier.clinic_id.is_(None),
            )
        )

    if not include_inactive:
        query = query.filter_by(is_active=True)

    return query.order_by(InventorySupplier.name.asc()).all()


@transactional
def create_supplier(
    name: str,
    clinic_id: int | None = None,
    **fields,
) -> InventorySupplier:
    if clinic_id is not None:
        _get_active_clinic(clinic_id)

    if not name or not name.strip():
        raise ValidationError("Supplier name is required")

    unknown = set(fields) - _SUPPLIER_EDITABLE_FIELDS

    if unknown:
        raise ValidationError(
            f"Unknown supplier field(s): {', '.join(sorted(unknown))}"
        )

    name = name.strip()

    duplicate_query = InventorySupplier.query.filter(
        db.func.lower(InventorySupplier.name) == name.lower(),
    )

    if clinic_id is not None:
        duplicate_query = duplicate_query.filter(
            db.or_(
                InventorySupplier.clinic_id == clinic_id,
                InventorySupplier.clinic_id.is_(None),
            )
        )

    if duplicate_query.first():
        raise ConflictError(
            f"Supplier '{name}' already exists"
        )

    for key in fields:
        fields[key] = _normalize_optional_text(fields[key])

    supplier = InventorySupplier(
        name=name,
        clinic_id=clinic_id,
        **fields,
    )

    db.session.add(supplier)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="InventorySupplier",
        entity_id=supplier.id,
        description=f"Inventory supplier '{supplier.name}' created",
        new_value={
            "clinic_id": supplier.clinic_id,
        },
    )

    return supplier


@transactional
def update_supplier(
    supplier_id: int,
    clinic_id: int | None = None,
    **fields,
) -> InventorySupplier:
    supplier = get_supplier(
        supplier_id,
        clinic_id,
    )

    unknown = set(fields) - (
        _SUPPLIER_EDITABLE_FIELDS | {"is_active"}
    )

    if unknown:
        raise ValidationError(
            f"Unknown supplier field(s): {', '.join(sorted(unknown))}"
        )

    old_values = {}
    new_values = {}

    for key, new_value in fields.items():
        if key in {
            "name",
            "contact_person",
            "phone",
            "email",
            "address",
        }:
            new_value = _normalize_optional_text(new_value)

        if key == "name" and not new_value:
            raise ValidationError("Supplier name cannot be empty")

        current_value = getattr(supplier, key)

        if current_value == new_value:
            continue

        if key == "name" and new_value:
            duplicate_query = InventorySupplier.query.filter(
                db.func.lower(InventorySupplier.name) == new_value.lower(),
                InventorySupplier.id != supplier.id,
            )

            if supplier.clinic_id is not None:
                duplicate_query = duplicate_query.filter(
                    db.or_(
                        InventorySupplier.clinic_id == supplier.clinic_id,
                        InventorySupplier.clinic_id.is_(None),
                    )
                )

            if duplicate_query.first():
                raise ConflictError(
                    f"Supplier '{new_value}' already exists"
                )

        old_values[key] = current_value
        new_values[key] = new_value

        setattr(supplier, key, new_value)

    if new_values:
        old_value, new_value = _build_change_dict(
            old_values,
            new_values,
        )

        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="InventorySupplier",
            entity_id=supplier.id,
            description=f"Inventory supplier '{supplier.name}' updated",
            old_value=old_value,
            new_value=new_value,
        )

    return supplier


@transactional
def deactivate_supplier(
    supplier_id: int,
    clinic_id: int | None = None,
) -> InventorySupplier:
    supplier = get_supplier(
        supplier_id,
        clinic_id,
    )

    if not supplier.is_active:
        return supplier

    supplier.is_active = False

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="InventorySupplier",
        entity_id=supplier.id,
        description=f"Inventory supplier '{supplier.name}' deactivated",
        old_value={"is_active": True},
        new_value={"is_active": False},
    )

    return supplier


@transactional
def reactivate_supplier(
    supplier_id: int,
    clinic_id: int | None = None,
) -> InventorySupplier:
    supplier = get_supplier(
        supplier_id,
        clinic_id,
    )

    if supplier.is_active:
        return supplier

    if supplier.clinic_id is not None:
        _get_active_clinic(supplier.clinic_id)

    supplier.is_active = True

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="InventorySupplier",
        entity_id=supplier.id,
        description=f"Inventory supplier '{supplier.name}' reactivated",
        old_value={"is_active": False},
        new_value={"is_active": True},
    )

    return supplier


# ============================================================================
# INVENTORY BATCHES
# ============================================================================

def get_inventory_batch(
    batch_id: int,
    item_id: int | None = None,
    clinic_id: int | None = None,
) -> InventoryBatch:
    batch = _get_batch(batch_id)

    item = _get_item(batch.item_id)

    if item_id is not None:
        _validate_batch_for_item(
            batch=batch,
            item=_get_item(item_id),
        )

    if clinic_id is not None:
        _validate_item_clinic(
            item,
            clinic_id,
        )

    return batch


def list_inventory_batches(
    item_id: int,
    clinic_id: int | None = None,
    include_inactive: bool = False,
) -> list[InventoryBatch]:
    item = get_inventory_item(
        item_id,
        clinic_id,
    )

    query = InventoryBatch.query.filter_by(
        item_id=item.id,
    )

    if not include_inactive:
        query = query.filter_by(is_active=True)

    return query.order_by(
        InventoryBatch.expiry_date.asc(),
        InventoryBatch.received_at.asc(),
    ).all()


@transactional
def create_inventory_batch(
    item_id: int,
    batch_number: str,
    unit_cost: Decimal | None = None,
    expiry_date: date | None = None,
    supplier_id: int | None = None,
    clinic_id: int | None = None,
) -> InventoryBatch:
    item = _get_active_item(item_id)

    _validate_item_clinic(
        item,
        clinic_id,
    )

    if not batch_number or not batch_number.strip():
        raise ValidationError("Batch number is required")

    batch_number = batch_number.strip()

    existing = InventoryBatch.query.filter_by(
        item_id=item.id,
        batch_number=batch_number,
    ).first()

    if existing:
        raise ConflictError(
            f"Batch '{batch_number}' already exists for inventory item {item.id}"
        )

    if unit_cost is not None and unit_cost < 0:
        raise ValidationError("Unit cost cannot be negative")

    _validate_batch_expiry(expiry_date)

    if supplier_id is not None:
        supplier = _get_supplier(supplier_id)

        if not supplier.is_active:
            raise ConflictError(
                f"Supplier {supplier_id} is inactive"
            )

        _validate_supplier_for_clinic(
            supplier,
            item.clinic_id,
        )

    batch = InventoryBatch(
        item_id=item.id,
        supplier_id=supplier_id,
        batch_number=batch_number,
        quantity_on_hand=0,
        unit_cost=unit_cost,
        expiry_date=expiry_date,
    )

    db.session.add(batch)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="InventoryBatch",
        entity_id=batch.id,
        description=f"Inventory batch '{batch.batch_number}' created",
        new_value={
            "item_id": item.id,
            "supplier_id": supplier_id,
            "expiry_date": (
                expiry_date.isoformat()
                if expiry_date
                else None
            ),
        },
    )

    return batch


@transactional
def update_inventory_batch(
    batch_id: int,
    clinic_id: int | None = None,
    **fields,
) -> InventoryBatch:
    batch = get_inventory_batch(
        batch_id,
        clinic_id=clinic_id,
    )

    unknown = set(fields) - _BATCH_EDITABLE_FIELDS

    if unknown:
        raise ValidationError(
            f"Unknown inventory batch field(s): {', '.join(sorted(unknown))}"
        )

    item = _get_item(batch.item_id)

    old_values = {}
    new_values = {}

    for key, new_value in fields.items():
        if key == "batch_number":
            new_value = _normalize_optional_text(new_value)

            if not new_value:
                raise ValidationError("Batch number cannot be empty")

            duplicate = InventoryBatch.query.filter(
                InventoryBatch.item_id == batch.item_id,
                InventoryBatch.batch_number == new_value,
                InventoryBatch.id != batch.id,
            ).first()

            if duplicate:
                raise ConflictError(
                    f"Batch '{new_value}' already exists for inventory item {item.id}"
                )

        if key == "unit_cost":
            if new_value is not None and new_value < 0:
                raise ValidationError("Unit cost cannot be negative")

        if key == "expiry_date":
            _validate_batch_expiry(new_value)

        if key == "supplier_id":
            if new_value is not None:
                supplier = _get_supplier(new_value)

                if not supplier.is_active:
                    raise ConflictError(
                        f"Supplier {new_value} is inactive"
                    )

                _validate_supplier_for_clinic(
                    supplier,
                    item.clinic_id,
                )

        current_value = getattr(batch, key)

        if current_value == new_value:
            continue

        old_values[key] = current_value
        new_values[key] = new_value

        setattr(batch, key, new_value)

    if new_values:
        old_value, new_value = _build_change_dict(
            old_values,
            new_values,
        )

        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="InventoryBatch",
            entity_id=batch.id,
            description=f"Inventory batch '{batch.batch_number}' updated",
            old_value=old_value,
            new_value=new_value,
        )

    return batch


def list_expiring_inventory_batches(
    clinic_id: int,
    days: int = 30,
) -> list[InventoryBatch]:
    _get_active_clinic(clinic_id)

    if days < 0:
        raise ValidationError("Days cannot be negative")

    today = date.today()
    expiry_limit = today + timedelta(days=days)

    return (
        InventoryBatch.query
        .join(InventoryItem)
        .filter(
            InventoryItem.clinic_id == clinic_id,
            InventoryItem.is_active.is_(True),
            InventoryBatch.is_active.is_(True),
            InventoryBatch.quantity_on_hand > 0,
            InventoryBatch.expiry_date.isnot(None),
            InventoryBatch.expiry_date >= today,
            InventoryBatch.expiry_date <= expiry_limit,
        )
        .order_by(InventoryBatch.expiry_date.asc())
        .all()
    )


# ============================================================================
# STOCK MOVEMENTS
# ============================================================================

def get_stock_movements(
    item_id: int,
    clinic_id: int | None = None,
) -> list[StockMovement]:
    item = get_inventory_item(
        item_id,
        clinic_id,
    )

    return (
        StockMovement.query
        .filter_by(item_id=item.id)
        .order_by(StockMovement.created_at.desc())
        .all()
    )


def _resolve_movement_direction(
    movement_type: StockMovementType,
    quantity: int,
) -> tuple[StockMovementDirection, int]:
    if movement_type == StockMovementType.ADJUSTMENT:
        if quantity == 0:
            raise ValidationError(
                "Adjustment quantity cannot be zero"
            )

        if quantity > 0:
            return StockMovementDirection.IN, quantity

        return StockMovementDirection.OUT, abs(quantity)

    _validate_positive_quantity(quantity)

    if movement_type in INCREASING_MOVEMENTS:
        return StockMovementDirection.IN, quantity

    if movement_type in DECREASING_MOVEMENTS:
        return StockMovementDirection.OUT, quantity

    raise ValidationError(
        f"Cannot determine stock direction for movement type "
        f"'{_serialize_enum(movement_type)}'"
    )


@transactional
def record_stock_movement(
    *,
    item_id: int,
    movement_type: StockMovementType,
    quantity: int,
    performed_by_id: int,
    batch_id: int | None = None,
    reason: str | None = None,
    reference_type: str | None = None,
    reference_id: int | None = None,
    clinic_id: int | None = None,
) -> StockMovement:
    item = _get_active_item(item_id)

    _validate_item_clinic(
        item,
        clinic_id,
    )

    _validate_staff_for_clinic(
        staff_id=performed_by_id,
        clinic_id=item.clinic_id,
    )

    direction, effective_quantity = _resolve_movement_direction(
        movement_type,
        quantity,
    )

    batch = None

    if batch_id is not None:
        batch = _get_batch(batch_id)

        _validate_batch_for_item(
            batch=batch,
            item=item,
        )

        _validate_batch_active(batch)

    if direction == StockMovementDirection.OUT:
        if item.quantity_on_hand < effective_quantity:
            raise ConflictError(
                f"Insufficient stock for inventory item {item.id}. "
                f"Available: {item.quantity_on_hand}, "
                f"requested: {effective_quantity}"
            )

        if batch is not None and batch.quantity_on_hand < effective_quantity:
            raise ConflictError(
                f"Insufficient stock in batch {batch.id}. "
                f"Available: {batch.quantity_on_hand}, "
                f"requested: {effective_quantity}"
            )

        item.quantity_on_hand -= effective_quantity

        if batch is not None:
            batch.quantity_on_hand -= effective_quantity

    else:
        item.quantity_on_hand += effective_quantity

        if batch is not None:
            batch.quantity_on_hand += effective_quantity

    movement = StockMovement(
        item_id=item.id,
        batch_id=batch.id if batch else None,
        movement_type=movement_type,
        direction=direction,
        quantity=effective_quantity,
        reason=_normalize_optional_text(reason),
        performed_by_id=performed_by_id,
        reference_type=_normalize_optional_text(reference_type),
        reference_id=reference_id,
    )

    db.session.add(movement)
    db.session.flush()

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="StockMovement",
        entity_id=movement.id,
        description=(
            f"Stock movement recorded for item {item.id}: "
            f"{direction.value} {effective_quantity}"
        ),
        new_value={
            "item_id": item.id,
            "batch_id": batch.id if batch else None,
            "movement_type": movement_type.value,
            "direction": direction.value,
            "quantity": effective_quantity,
            "reference_type": reference_type,
            "reference_id": reference_id,
            "quantity_on_hand": item.quantity_on_hand,
        },
    )

    return movement


# ============================================================================
# INVENTORY TRANSFERS
# ============================================================================

def get_inventory_transfer(
    transfer_id: int,
    clinic_id: int | None = None,
) -> InventoryTransfer:
    transfer = db.session.get(
        InventoryTransfer,
        transfer_id,
    )

    if transfer is None:
        raise NotFoundError(
            f"Inventory transfer {transfer_id} not found"
        )

    if clinic_id is not None:
        if (
            transfer.source_clinic_id != clinic_id
            and transfer.destination_clinic_id != clinic_id
        ):
            raise ValidationError(
                f"Inventory transfer {transfer_id} is not associated "
                f"with clinic {clinic_id}"
            )

    return transfer


def list_inventory_transfers(
    clinic_id: int,
    status: InventoryTransferStatus | None = None,
) -> list[InventoryTransfer]:
    _get_active_clinic(clinic_id)

    query = InventoryTransfer.query.filter(
        db.or_(
            InventoryTransfer.source_clinic_id == clinic_id,
            InventoryTransfer.destination_clinic_id == clinic_id,
        )
    )

    if status is not None:
        query = query.filter_by(status=status)

    return query.order_by(
        InventoryTransfer.created_at.desc()
    ).all()


@transactional
def create_inventory_transfer(
    *,
    item_id: int,
    source_clinic_id: int,
    destination_clinic_id: int,
    quantity: int,
    requested_by_id: int,
    batch_id: int | None = None,
    reason: str | None = None,
) -> InventoryTransfer:
    _validate_positive_quantity(quantity)

    if source_clinic_id == destination_clinic_id:
        raise ValidationError(
            "Source and destination clinics must be different"
        )

    source_clinic = _get_active_clinic(source_clinic_id)
    _get_active_clinic(destination_clinic_id)

    item = _get_active_item(item_id)

    _ensure_same_clinic(
        expected_clinic_id=source_clinic.id,
        actual_clinic_id=item.clinic_id,
        resource_name=f"Inventory item {item.id}",
    )

    _validate_staff_for_clinic(
        staff_id=requested_by_id,
        clinic_id=source_clinic_id,
    )

    if item.quantity_on_hand < quantity:
        raise ConflictError(
            f"Insufficient stock for transfer. "
            f"Available: {item.quantity_on_hand}, requested: {quantity}"
        )

    batch = None

    if batch_id is not None:
        batch = _get_batch(batch_id)

        _validate_batch_for_item(
            batch=batch,
            item=item,
        )

        _validate_batch_active(batch)

        if batch.quantity_on_hand < quantity:
            raise ConflictError(
                f"Insufficient stock in batch {batch.id}. "
                f"Available: {batch.quantity_on_hand}, requested: {quantity}"
            )

    transfer = InventoryTransfer(
        item_id=item.id,
        batch_id=batch.id if batch else None,
        source_clinic_id=source_clinic_id,
        destination_clinic_id=destination_clinic_id,
        quantity=quantity,
        status=InventoryTransferStatus.PENDING,
        reason=_normalize_optional_text(reason),
        requested_by_id=requested_by_id,
        requested_at=_utcnow(),
    )

    db.session.add(transfer)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="InventoryTransfer",
        entity_id=transfer.id,
        description=(
            f"Inventory transfer requested: "
            f"{source_clinic_id} -> {destination_clinic_id}"
        ),
        new_value={
            "item_id": item.id,
            "batch_id": batch.id if batch else None,
            "quantity": quantity,
            "source_clinic_id": source_clinic_id,
            "destination_clinic_id": destination_clinic_id,
        },
    )

    return transfer


@transactional
def approve_inventory_transfer(
    transfer_id: int,
    approved_by_id: int,
) -> InventoryTransfer:
    transfer = get_inventory_transfer(transfer_id)

    if transfer.status != InventoryTransferStatus.PENDING:
        raise ConflictError(
            f"Transfer {transfer.id} cannot be approved from "
            f"status '{transfer.status.value}'"
        )

    _validate_staff_for_clinic(
        staff_id=approved_by_id,
        clinic_id=transfer.source_clinic_id,
    )

    if approved_by_id == transfer.requested_by_id:
        raise ValidationError(
            "The staff member who requested a transfer cannot approve "
            "the same transfer"
        )

    transfer.status = InventoryTransferStatus.APPROVED
    transfer.approved_by_id = approved_by_id
    transfer.approved_at = _utcnow()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="InventoryTransfer",
        entity_id=transfer.id,
        description=f"Inventory transfer {transfer.id} approved",
        old_value={
            "status": InventoryTransferStatus.PENDING.value,
        },
        new_value={
            "status": InventoryTransferStatus.APPROVED.value,
            "approved_by_id": approved_by_id,
        },
    )

    return transfer


def _get_or_create_destination_item(
    *,
    source_item: InventoryItem,
    destination_clinic_id: int,
) -> InventoryItem:
    destination_item = InventoryItem.query.filter_by(
        clinic_id=destination_clinic_id,
        name=source_item.name,
        category=source_item.category,
    ).first()

    if destination_item is not None:
        if not destination_item.is_active:
            destination_item.is_active = True

        return destination_item

    destination_item = InventoryItem(
        clinic_id=destination_clinic_id,
        name=source_item.name,
        category=source_item.category,
        sku=None,
        barcode=None,
        unit=source_item.unit,
        quantity_on_hand=0,
        reorder_level=source_item.reorder_level,
        is_active=True,
    )

    db.session.add(destination_item)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="InventoryItem",
        entity_id=destination_item.id,
        description=(
            f"Destination inventory item created for transfer "
            f"from source item {source_item.id}"
        ),
        new_value={
            "source_item_id": source_item.id,
            "destination_clinic_id": destination_clinic_id,
        },
    )

    return destination_item


def _get_or_create_destination_batch(
    *,
    source_batch: InventoryBatch,
    destination_item: InventoryItem,
) -> InventoryBatch:
    destination_batch = InventoryBatch.query.filter_by(
        item_id=destination_item.id,
        batch_number=source_batch.batch_number,
    ).first()

    if destination_batch is not None:
        if not destination_batch.is_active:
            destination_batch.is_active = True

        return destination_batch

    destination_batch = InventoryBatch(
        item_id=destination_item.id,
        supplier_id=source_batch.supplier_id,
        batch_number=source_batch.batch_number,
        quantity_on_hand=0,
        unit_cost=source_batch.unit_cost,
        expiry_date=source_batch.expiry_date,
        received_at=_utcnow(),
        is_active=True,
    )

    db.session.add(destination_batch)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="InventoryBatch",
        entity_id=destination_batch.id,
        description=(
            f"Destination batch '{destination_batch.batch_number}' "
            f"created from source batch {source_batch.id}"
        ),
        new_value={
            "source_batch_id": source_batch.id,
            "destination_item_id": destination_item.id,
        },
    )

    return destination_batch


@transactional
def complete_inventory_transfer(
    transfer_id: int,
    performed_by_id: int,
) -> InventoryTransfer:
    transfer = get_inventory_transfer(transfer_id)

    if transfer.status not in (
        InventoryTransferStatus.APPROVED,
        InventoryTransferStatus.IN_TRANSIT,
    ):
        raise ConflictError(
            f"Transfer {transfer.id} cannot be completed from "
            f"status '{transfer.status.value}'"
        )

    _validate_staff_for_clinic(
        staff_id=performed_by_id,
        clinic_id=transfer.source_clinic_id,
    )

    source_item = _get_active_item(transfer.item_id)

    _ensure_same_clinic(
        expected_clinic_id=transfer.source_clinic_id,
        actual_clinic_id=source_item.clinic_id,
        resource_name=f"Inventory item {source_item.id}",
    )

    if source_item.quantity_on_hand < transfer.quantity:
        raise ConflictError(
            f"Insufficient source stock for transfer {transfer.id}. "
            f"Available: {source_item.quantity_on_hand}, "
            f"required: {transfer.quantity}"
        )

    source_batch = None

    if transfer.batch_id is not None:
        source_batch = _get_batch(transfer.batch_id)

        _validate_batch_for_item(
            batch=source_batch,
            item=source_item,
        )

        _validate_batch_active(source_batch)

        if source_batch.quantity_on_hand < transfer.quantity:
            raise ConflictError(
                f"Insufficient source batch stock for transfer "
                f"{transfer.id}. Available: "
                f"{source_batch.quantity_on_hand}, required: "
                f"{transfer.quantity}"
            )

    destination_item = _get_or_create_destination_item(
        source_item=source_item,
        destination_clinic_id=transfer.destination_clinic_id,
    )

    destination_batch = None

    if source_batch is not None:
        destination_batch = _get_or_create_destination_batch(
            source_batch=source_batch,
            destination_item=destination_item,
        )

    old_status = transfer.status.value

    # ------------------------------------------------------------------
    # SOURCE
    # ------------------------------------------------------------------

    source_item.quantity_on_hand -= transfer.quantity

    if source_batch is not None:
        source_batch.quantity_on_hand -= transfer.quantity

    source_movement = StockMovement(
        item_id=source_item.id,
        batch_id=source_batch.id if source_batch else None,
        movement_type=StockMovementType.TRANSFER_OUT,
        direction=StockMovementDirection.OUT,
        quantity=transfer.quantity,
        reason=transfer.reason,
        performed_by_id=performed_by_id,
        reference_type="inventory_transfer",
        reference_id=transfer.id,
    )

    db.session.add(source_movement)

    # ------------------------------------------------------------------
    # DESTINATION
    # ------------------------------------------------------------------

    destination_item.quantity_on_hand += transfer.quantity

    if destination_batch is not None:
        destination_batch.quantity_on_hand += transfer.quantity

    destination_movement = StockMovement(
        item_id=destination_item.id,
        batch_id=destination_batch.id if destination_batch else None,
        movement_type=StockMovementType.TRANSFER_IN,
        direction=StockMovementDirection.IN,
        quantity=transfer.quantity,
        reason=transfer.reason,
        performed_by_id=performed_by_id,
        reference_type="inventory_transfer",
        reference_id=transfer.id,
    )

    db.session.add(destination_movement)

    # ------------------------------------------------------------------
    # COMPLETE TRANSFER
    # ------------------------------------------------------------------

    transfer.status = InventoryTransferStatus.COMPLETED
    transfer.completed_at = _utcnow()

    db.session.flush()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="InventoryTransfer",
        entity_id=transfer.id,
        description=f"Inventory transfer {transfer.id} completed",
        old_value={
            "status": old_status,
        },
        new_value={
            "status": InventoryTransferStatus.COMPLETED.value,
            "performed_by_id": performed_by_id,
            "destination_item_id": destination_item.id,
            "destination_batch_id": (
                destination_batch.id
                if destination_batch
                else None
            ),
        },
    )

    return transfer


@transactional
def cancel_inventory_transfer(
    transfer_id: int,
    cancelled_by_id: int,
    reason: str | None = None,
) -> InventoryTransfer:
    transfer = get_inventory_transfer(transfer_id)

    if transfer.status in (
        InventoryTransferStatus.COMPLETED,
        InventoryTransferStatus.CANCELLED,
    ):
        raise ConflictError(
            f"Transfer {transfer.id} cannot be cancelled from "
            f"status '{transfer.status.value}'"
        )

    _validate_staff_for_clinic(
        staff_id=cancelled_by_id,
        clinic_id=transfer.source_clinic_id,
    )

    old_status = transfer.status.value

    transfer.status = InventoryTransferStatus.CANCELLED
    transfer.cancelled_at = _utcnow()

    if reason is not None:
        reason = _normalize_optional_text(reason)
        transfer.reason = reason

    db.session.flush()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="InventoryTransfer",
        entity_id=transfer.id,
        description=(
            f"Inventory transfer {transfer.id} cancelled"
            + (f": {reason}" if reason else "")
        ),
        old_value={
            "status": old_status,
        },
        new_value={
            "status": InventoryTransferStatus.CANCELLED.value,
            "cancelled_by_id": cancelled_by_id,
            "reason": reason,
        },
    )

    return transfer