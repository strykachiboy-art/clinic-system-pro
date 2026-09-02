from app.extensions import db
from app.core.utils.decorators import transactional
from app.core.exceptions import NotFoundError, ValidationError, ConflictError
from app.core.audit.services.audit_services import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.inventory_enums import (
    InventoryCategory, StockMovementType,
    INCREASING_MOVEMENTS, DECREASING_MOVEMENTS,
)
from app.modules.inventory.models.inventory_model import (
    InventoryItem, InventorySupplier, StockMovement,
)

# Whitelist so a route can't push quantity_on_hand (or anything else)
# through the generic update path — stock changes only happen through
# record_stock_movement, to keep StockMovement the audit trail of truth.
_ITEM_EDITABLE_FIELDS = {
    "name", "category", "sku", "barcode", "unit",
    "reorder_level", "unit_cost", "expiry_date", "supplier_id",
}

_SUPPLIER_EDITABLE_FIELDS = {
    "name", "contact_person", "phone", "email", "address",
}


# ============================== items ==============================

def get_inventory_item(item_id: int) -> InventoryItem:
    item = InventoryItem.query.get(item_id)
    if item is None:
        raise NotFoundError(f"Inventory item {item_id} not found")
    return item


def list_inventory_items(
    clinic_id: int,
    category: InventoryCategory | None = None,
    low_stock_only: bool = False,
    include_inactive: bool = False,
) -> list[InventoryItem]:
    query = InventoryItem.query.filter_by(clinic_id=clinic_id)

    if not include_inactive:
        query = query.filter_by(is_active=True)
    if category is not None:
        query = query.filter_by(category=category)
    if low_stock_only:
        query = query.filter(InventoryItem.quantity_on_hand <= InventoryItem.reorder_level)

    return query.order_by(InventoryItem.name).all()


@transactional
def create_inventory_item(
    clinic_id: int,
    name: str,
    category: InventoryCategory = InventoryCategory.MEDICAL_SUPPLY,
    initial_quantity: int = 0,
    **fields,
) -> InventoryItem:
    if not name or not name.strip():
        raise ValidationError("Item name is required")

    unknown = set(fields) - _ITEM_EDITABLE_FIELDS
    if unknown:
        raise ValidationError(f"Unknown inventory item field(s): {', '.join(sorted(unknown))}")

    if initial_quantity < 0:
        raise ValidationError("initial_quantity cannot be negative")

    item = InventoryItem(
        clinic_id=clinic_id,
        name=name.strip(),
        category=category,
        quantity_on_hand=0,
        **fields,
    )
    db.session.add(item)
    db.session.flush()  # get item.id for the audit log and the opening movement

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="InventoryItem",
        entity_id=item.id,
        description=f"Inventory item '{item.name}' created",
        new_value={"category": category.value, "reorder_level": item.reorder_level},
    )

    if initial_quantity > 0:
        _apply_stock_movement(
            item,
            movement_type=StockMovementType.RESTOCK,
            quantity=initial_quantity,
            reason="Initial stock on item creation",
            performed_by_id=None,
        )

    return item


@transactional
def update_inventory_item(item_id: int, **fields) -> InventoryItem:
    item = get_inventory_item(item_id)

    unknown = set(fields) - _ITEM_EDITABLE_FIELDS
    if unknown:
        raise ValidationError(f"Unknown inventory item field(s): {', '.join(sorted(unknown))}")

    old_value = {}
    new_value = {}
    for key, value in fields.items():
        if value is None:
            continue
        current = getattr(item, key)
        if current == value:
            continue
        old_value[key] = current.value if hasattr(current, "value") else current
        setattr(item, key, value)
        new_value[key] = value.value if hasattr(value, "value") else value

    if new_value:
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
def deactivate_inventory_item(item_id: int) -> InventoryItem:
    item = get_inventory_item(item_id)
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
def reactivate_inventory_item(item_id: int) -> InventoryItem:
    item = get_inventory_item(item_id)
    if item.is_active:
        return item

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


# ============================== stock movements ==============================

def _apply_stock_movement(
    item: InventoryItem,
    movement_type: StockMovementType,
    quantity: int,
    reason: str | None,
    performed_by_id: int | None,
) -> StockMovement:
    """Applies sign convention, updates quantity_on_hand, writes the
    StockMovement row and its audit log. Caller owns the transaction."""

    if quantity == 0:
        raise ValidationError("Stock movement quantity cannot be zero")

    if movement_type in INCREASING_MOVEMENTS:
        signed_quantity = abs(quantity)
    elif movement_type in DECREASING_MOVEMENTS:
        signed_quantity = -abs(quantity)
    else:  # ADJUSTMENT — caller's sign is the correction itself
        signed_quantity = quantity

    new_total = item.quantity_on_hand + signed_quantity
    if new_total < 0:
        raise ConflictError(
            f"Cannot record movement of {signed_quantity} — only "
            f"{item.quantity_on_hand} units on hand for '{item.name}'"
        )

    old_quantity = item.quantity_on_hand
    item.quantity_on_hand = new_total

    movement = StockMovement(
        item_id=item.id,
        movement_type=movement_type,
        quantity=signed_quantity,
        reason=reason,
        performed_by_id=performed_by_id,
    )
    db.session.add(movement)
    db.session.flush()

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="InventoryItem",
        entity_id=item.id,
        description=f"Stock movement '{movement_type.value}' ({signed_quantity:+d}) on '{item.name}'",
        old_value={"quantity_on_hand": old_quantity},
        new_value={"quantity_on_hand": new_total},
    )

    return movement


@transactional
def record_stock_movement(
    item_id: int,
    movement_type: StockMovementType,
    quantity: int,
    reason: str | None = None,
    performed_by_id: int | None = None,
) -> StockMovement:
    item = get_inventory_item(item_id)
    return _apply_stock_movement(item, movement_type, quantity, reason, performed_by_id)


def get_stock_movements(item_id: int) -> list[StockMovement]:
    get_inventory_item(item_id)  # 404s if item doesn't exist
    return (
        StockMovement.query
        .filter_by(item_id=item_id)
        .order_by(StockMovement.created_at.desc())
        .all()
    )


def get_low_stock_items(clinic_id: int) -> list[InventoryItem]:
    return list_inventory_items(clinic_id, low_stock_only=True)


# ============================== suppliers ==============================

def get_supplier(supplier_id: int) -> InventorySupplier:
    supplier = InventorySupplier.query.get(supplier_id)
    if supplier is None:
        raise NotFoundError(f"Supplier {supplier_id} not found")
    return supplier


def list_suppliers(clinic_id: int | None = None, include_inactive: bool = False) -> list[InventorySupplier]:
    query = InventorySupplier.query
    if clinic_id is not None:
        query = query.filter(
            (InventorySupplier.clinic_id == clinic_id) | (InventorySupplier.clinic_id.is_(None))
        )
    if not include_inactive:
        query = query.filter_by(is_active=True)
    return query.order_by(InventorySupplier.name).all()


@transactional
def create_supplier(name: str, clinic_id: int | None = None, **fields) -> InventorySupplier:
    if not name or not name.strip():
        raise ValidationError("Supplier name is required")

    unknown = set(fields) - _SUPPLIER_EDITABLE_FIELDS
    if unknown:
        raise ValidationError(f"Unknown supplier field(s): {', '.join(sorted(unknown))}")

    supplier = InventorySupplier(name=name.strip(), clinic_id=clinic_id, **fields)
    db.session.add(supplier)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="InventorySupplier",
        entity_id=supplier.id,
        description=f"Supplier '{supplier.name}' created",
    )
    return supplier


@transactional
def update_supplier(supplier_id: int, **fields) -> InventorySupplier:
    supplier = get_supplier(supplier_id)

    unknown = set(fields) - _SUPPLIER_EDITABLE_FIELDS - {"is_active"}
    if unknown:
        raise ValidationError(f"Unknown supplier field(s): {', '.join(sorted(unknown))}")

    old_value = {}
    new_value = {}
    for key, value in fields.items():
        if value is None:
            continue
        current = getattr(supplier, key)
        if current == value:
            continue
        old_value[key] = current
        setattr(supplier, key, value)
        new_value[key] = value

    if new_value:
        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="InventorySupplier",
            entity_id=supplier.id,
            description=f"Supplier '{supplier.name}' updated",
            old_value=old_value,
            new_value=new_value,
        )
    return supplier