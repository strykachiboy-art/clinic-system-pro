from __future__ import annotations

from flask import Blueprint, jsonify, request
from pydantic import ValidationError as PydanticValidationError

from app.core.enums.inventory_enums import InventoryTransferStatus
from app.core.enums.role_enums import Role
from app.core.exceptions import ValidationError
from app.core.utils.decorators import role_required

from app.modules.inventory.schemas.inventory_schema import (
    ExpiringInventoryBatchQuerySchema,
    InventoryBatchCreateSchema,
    InventoryBatchFilterSchema,
    InventoryBatchResponseSchema,
    InventoryBatchUpdateSchema,
    InventoryItemCreateSchema,
    InventoryItemFilterSchema,
    InventoryItemResponseSchema,
    InventoryItemUpdateSchema,
    InventorySupplierCreateSchema,
    InventorySupplierFilterSchema,
    InventorySupplierResponseSchema,
    InventorySupplierUpdateSchema,
    InventoryTransferApproveSchema,
    InventoryTransferCancelSchema,
    InventoryTransferCompleteSchema,
    InventoryTransferCreateSchema,
    InventoryTransferFilterSchema,
    InventoryTransferResponseSchema,
    StockMovementCreateSchema,
    StockMovementResponseSchema,
)

from app.modules.inventory.services.inventory_service import (
    approve_inventory_transfer,
    cancel_inventory_transfer,
    complete_inventory_transfer,
    create_inventory_batch,
    create_inventory_item,
    create_inventory_transfer,
    create_supplier,
    deactivate_inventory_item,
    deactivate_supplier,
    get_inventory_batch,
    get_inventory_item,
    get_inventory_transfer,
    get_low_stock_items,
    get_stock_movements,
    get_supplier,
    list_expiring_inventory_batches,
    list_inventory_batches,
    list_inventory_items,
    list_inventory_transfers,
    list_suppliers,
    reactivate_inventory_item,
    reactivate_supplier,
    record_stock_movement,
    update_inventory_batch,
    update_inventory_item,
    update_supplier,
)


inventory_bp = Blueprint(
    "inventory",
    __name__,
    url_prefix="/inventory",
)


# ============================================================================
# ROUTE HELPERS
# ============================================================================

def _json_body() -> dict:
    payload = request.get_json(silent=True)

    if payload is None:
        return {}

    if not isinstance(payload, dict):
        raise ValidationError("JSON body must be an object")

    return payload


def _required_query_int(name: str) -> int:
    value = request.args.get(name, type=int)

    if value is None or value <= 0:
        raise ValidationError(
            f"{name} query parameter is required and must be greater than zero"
        )

    return value


def _serialize(schema, value):
    return schema.model_validate(value).model_dump(
        mode="json"
    )


def _serialize_many(schema, values):
    return [
        schema.model_validate(value).model_dump(mode="json")
        for value in values
    ]


# ============================================================================
# INVENTORY ITEMS
# ============================================================================

@inventory_bp.get("/items")
@role_required(Role.ADMIN, Role.PHARMACIST)
def list_items():
    clinic_id = _required_query_int("clinic_id")

    filters = InventoryItemFilterSchema.model_validate(
        request.args.to_dict()
    )

    items = list_inventory_items(
        clinic_id=clinic_id,
        category=filters.category,
        low_stock_only=filters.low_stock_only,
        include_inactive=filters.include_inactive,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize_many(
                InventoryItemResponseSchema,
                items,
            ),
        }
    ), 200


@inventory_bp.get("/items/low-stock")
@role_required(Role.ADMIN, Role.PHARMACIST)
def low_stock_items():
    clinic_id = _required_query_int("clinic_id")

    items = get_low_stock_items(
        clinic_id=clinic_id,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize_many(
                InventoryItemResponseSchema,
                items,
            ),
        }
    ), 200


@inventory_bp.get("/items/<int:item_id>")
@role_required(Role.ADMIN, Role.PHARMACIST)
def get_item(item_id: int):
    clinic_id = request.args.get("clinic_id", type=int)

    item = get_inventory_item(
        item_id=item_id,
        clinic_id=clinic_id,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                InventoryItemResponseSchema,
                item,
            ),
        }
    ), 200


@inventory_bp.post("/items")
@role_required(Role.ADMIN, Role.PHARMACIST)
def create_item():
    payload = InventoryItemCreateSchema.model_validate(
        _json_body()
    )

    data = payload.model_dump(
        exclude_unset=True
    )

    item = create_inventory_item(
        **data
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                InventoryItemResponseSchema,
                item,
            ),
        }
    ), 201


@inventory_bp.patch("/items/<int:item_id>")
@role_required(Role.ADMIN, Role.PHARMACIST)
def update_item(item_id: int):
    clinic_id = _required_query_int("clinic_id")

    payload = InventoryItemUpdateSchema.model_validate(
        _json_body()
    )

    item = update_inventory_item(
        item_id=item_id,
        clinic_id=clinic_id,
        **payload.model_dump(exclude_unset=True),
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                InventoryItemResponseSchema,
                item,
            ),
        }
    ), 200


@inventory_bp.post("/items/<int:item_id>/deactivate")
@role_required(Role.ADMIN)
def deactivate_item(item_id: int):
    clinic_id = _required_query_int("clinic_id")

    item = deactivate_inventory_item(
        item_id=item_id,
        clinic_id=clinic_id,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                InventoryItemResponseSchema,
                item,
            ),
        }
    ), 200


@inventory_bp.post("/items/<int:item_id>/reactivate")
@role_required(Role.ADMIN)
def reactivate_item(item_id: int):
    clinic_id = _required_query_int("clinic_id")

    item = reactivate_inventory_item(
        item_id=item_id,
        clinic_id=clinic_id,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                InventoryItemResponseSchema,
                item,
            ),
        }
    ), 200


# ============================================================================
# INVENTORY BATCHES
# ============================================================================

@inventory_bp.get("/items/<int:item_id>/batches")
@role_required(Role.ADMIN, Role.PHARMACIST)
def list_batches(item_id: int):
    clinic_id = _required_query_int("clinic_id")

    filters = InventoryBatchFilterSchema.model_validate(
        request.args.to_dict()
    )

    batches = list_inventory_batches(
        item_id=item_id,
        clinic_id=clinic_id,
        include_inactive=filters.include_inactive,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize_many(
                InventoryBatchResponseSchema,
                batches,
            ),
        }
    ), 200


@inventory_bp.get("/batches/<int:batch_id>")
@role_required(Role.ADMIN, Role.PHARMACIST)
def get_batch(batch_id: int):
    clinic_id = request.args.get("clinic_id", type=int)

    batch = get_inventory_batch(
        batch_id=batch_id,
        clinic_id=clinic_id,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                InventoryBatchResponseSchema,
                batch,
            ),
        }
    ), 200


@inventory_bp.post("/batches")
@role_required(Role.ADMIN, Role.PHARMACIST)
def create_batch():
    payload = InventoryBatchCreateSchema.model_validate(
        _json_body()
    )

    batch = create_inventory_batch(
        **payload.model_dump(
            exclude_unset=True
        )
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                InventoryBatchResponseSchema,
                batch,
            ),
        }
    ), 201


@inventory_bp.patch("/batches/<int:batch_id>")
@role_required(Role.ADMIN, Role.PHARMACIST)
def update_batch(batch_id: int):
    clinic_id = _required_query_int("clinic_id")

    payload = InventoryBatchUpdateSchema.model_validate(
        _json_body()
    )

    batch = update_inventory_batch(
        batch_id=batch_id,
        clinic_id=clinic_id,
        **payload.model_dump(
            exclude_unset=True
        ),
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                InventoryBatchResponseSchema,
                batch,
            ),
        }
    ), 200


@inventory_bp.get("/batches/expiring")
@role_required(Role.ADMIN, Role.PHARMACIST)
def expiring_batches():
    clinic_id = _required_query_int("clinic_id")

    filters = ExpiringInventoryBatchQuerySchema.model_validate(
        request.args.to_dict()
    )

    batches = list_expiring_inventory_batches(
        clinic_id=clinic_id,
        days=filters.days,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize_many(
                InventoryBatchResponseSchema,
                batches,
            ),
        }
    ), 200


# ============================================================================
# STOCK MOVEMENTS
# ============================================================================

@inventory_bp.get("/items/<int:item_id>/movements")
@role_required(Role.ADMIN, Role.PHARMACIST)
def list_movements(item_id: int):
    clinic_id = _required_query_int("clinic_id")

    movements = get_stock_movements(
        item_id=item_id,
        clinic_id=clinic_id,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize_many(
                StockMovementResponseSchema,
                movements,
            ),
        }
    ), 200


@inventory_bp.post("/movements")
@role_required(Role.ADMIN, Role.PHARMACIST)
def create_movement():
    payload = StockMovementCreateSchema.model_validate(
        _json_body()
    )

    movement = record_stock_movement(
        **payload.model_dump(
            exclude_unset=True
        )
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                StockMovementResponseSchema,
                movement,
            ),
        }
    ), 201


# ============================================================================
# SUPPLIERS
# ============================================================================

@inventory_bp.get("/suppliers")
@role_required(Role.ADMIN, Role.PHARMACIST)
def list_inventory_suppliers():
    clinic_id = request.args.get("clinic_id", type=int)

    filters = InventorySupplierFilterSchema.model_validate(
        request.args.to_dict()
    )

    suppliers = list_suppliers(
        clinic_id=clinic_id,
        include_inactive=filters.include_inactive,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize_many(
                InventorySupplierResponseSchema,
                suppliers,
            ),
        }
    ), 200


@inventory_bp.get("/suppliers/<int:supplier_id>")
@role_required(Role.ADMIN, Role.PHARMACIST)
def get_inventory_supplier(supplier_id: int):
    clinic_id = request.args.get("clinic_id", type=int)

    supplier = get_supplier(
        supplier_id=supplier_id,
        clinic_id=clinic_id,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                InventorySupplierResponseSchema,
                supplier,
            ),
        }
    ), 200


@inventory_bp.post("/suppliers")
@role_required(Role.ADMIN, Role.PHARMACIST)
def create_inventory_supplier():
    payload = InventorySupplierCreateSchema.model_validate(
        _json_body()
    )

    supplier = create_supplier(
        **payload.model_dump(
            exclude_unset=True
        )
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                InventorySupplierResponseSchema,
                supplier,
            ),
        }
    ), 201


@inventory_bp.patch("/suppliers/<int:supplier_id>")
@role_required(Role.ADMIN)
def update_inventory_supplier(supplier_id: int):
    clinic_id = request.args.get("clinic_id", type=int)

    payload = InventorySupplierUpdateSchema.model_validate(
        _json_body()
    )

    supplier = update_supplier(
        supplier_id=supplier_id,
        clinic_id=clinic_id,
        **payload.model_dump(
            exclude_unset=True
        ),
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                InventorySupplierResponseSchema,
                supplier,
            ),
        }
    ), 200


@inventory_bp.post("/suppliers/<int:supplier_id>/deactivate")
@role_required(Role.ADMIN)
def deactivate_inventory_supplier(supplier_id: int):
    clinic_id = _required_query_int("clinic_id")

    supplier = deactivate_supplier(
        supplier_id=supplier_id,
        clinic_id=clinic_id,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                InventorySupplierResponseSchema,
                supplier,
            ),
        }
    ), 200


@inventory_bp.post("/suppliers/<int:supplier_id>/reactivate")
@role_required(Role.ADMIN)
def reactivate_inventory_supplier(supplier_id: int):
    clinic_id = _required_query_int("clinic_id")

    supplier = reactivate_supplier(
        supplier_id=supplier_id,
        clinic_id=clinic_id,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                InventorySupplierResponseSchema,
                supplier,
            ),
        }
    ), 200


# ============================================================================
# INVENTORY TRANSFERS
# ============================================================================

@inventory_bp.get("/transfers")
@role_required(Role.ADMIN, Role.PHARMACIST)
def list_transfers():
    clinic_id = _required_query_int("clinic_id")

    filters = InventoryTransferFilterSchema.model_validate(
        request.args.to_dict()
    )

    transfers = list_inventory_transfers(
        clinic_id=clinic_id,
        status=filters.status,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize_many(
                InventoryTransferResponseSchema,
                transfers,
            ),
        }
    ), 200


@inventory_bp.get("/transfers/<int:transfer_id>")
@role_required(Role.ADMIN, Role.PHARMACIST)
def get_transfer(transfer_id: int):
    clinic_id = _required_query_int("clinic_id")

    transfer = get_inventory_transfer(
        transfer_id=transfer_id,
        clinic_id=clinic_id,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                InventoryTransferResponseSchema,
                transfer,
            ),
        }
    ), 200


@inventory_bp.post("/transfers")
@role_required(Role.ADMIN, Role.PHARMACIST)
def create_transfer():
    payload = InventoryTransferCreateSchema.model_validate(
        _json_body()
    )

    transfer = create_inventory_transfer(
        **payload.model_dump(
            exclude_unset=True
        )
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                InventoryTransferResponseSchema,
                transfer,
            ),
        }
    ), 201


@inventory_bp.post("/transfers/<int:transfer_id>/approve")
@role_required(Role.ADMIN, Role.PHARMACIST)
def approve_transfer(transfer_id: int):
    payload = InventoryTransferApproveSchema.model_validate(
        _json_body()
    )

    transfer = approve_inventory_transfer(
        transfer_id=transfer_id,
        **payload.model_dump(
            exclude_unset=True
        ),
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                InventoryTransferResponseSchema,
                transfer,
            ),
        }
    ), 200


@inventory_bp.post("/transfers/<int:transfer_id>/complete")
@role_required(Role.ADMIN, Role.PHARMACIST)
def complete_transfer(transfer_id: int):
    payload = InventoryTransferCompleteSchema.model_validate(
        _json_body()
    )

    transfer = complete_inventory_transfer(
        transfer_id=transfer_id,
        **payload.model_dump(
            exclude_unset=True
        ),
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                InventoryTransferResponseSchema,
                transfer,
            ),
        }
    ), 200


@inventory_bp.post("/transfers/<int:transfer_id>/cancel")
@role_required(Role.ADMIN, Role.PHARMACIST)
def cancel_transfer(transfer_id: int):
    payload = InventoryTransferCancelSchema.model_validate(
        _json_body()
    )

    transfer = cancel_inventory_transfer(
        transfer_id=transfer_id,
        **payload.model_dump(
            exclude_unset=True
        ),
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                InventoryTransferResponseSchema,
                transfer,
            ),
        }
    ), 200