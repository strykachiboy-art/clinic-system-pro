from __future__ import annotations

import json

from flask import Blueprint, jsonify, request
from pydantic import ValidationError as PydanticValidationError

from app.core.enums.role_enums import Role
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
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
    url_prefix="/api/inventory",
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


def _sanitize_pydantic_errors(
    exc: PydanticValidationError,
) -> list[dict]:
    """
    Convert Pydantic validation errors into JSON-safe dictionaries.

    Pydantic can place non-JSON-serializable exception objects such as
    ValueError inside the `ctx` field. Flask's jsonify cannot serialize
    those objects directly.
    """
    sanitized = []

    for error in exc.errors():
        item = dict(error)

        if "ctx" in item:
            ctx = item["ctx"]

            if isinstance(ctx, dict):
                item["ctx"] = {
                    key: str(value)
                    for key, value in ctx.items()
                }
            else:
                item["ctx"] = str(ctx)

        if "input" in item:
            input_value = item["input"]

            try:
                json.dumps(input_value)
            except (TypeError, ValueError):
                item["input"] = str(input_value)

        sanitized.append(item)

    return sanitized


def _validation_response(
    exc: PydanticValidationError,
):
    return (
        jsonify(
            {
                "error": "Validation error",
                "details": _sanitize_pydantic_errors(exc),
            }
        ),
        400,
    )


def _validate_json(schema):
    try:
        return schema.model_validate(_json_body()), None

    except PydanticValidationError as exc:
        return None, _validation_response(exc)

    except ValidationError as exc:
        return None, (
            jsonify(
                {
                    "error": str(exc),
                }
            ),
            400,
        )


def _query_without(*excluded: str) -> dict:
    excluded = set(excluded)

    return {
        key: value
        for key, value in request.args.to_dict().items()
        if key not in excluded
    }


def _required_query_int(name: str) -> int:
    raw_value = request.args.get(name)

    if raw_value is None:
        raise ValidationError(
            f"{name} query parameter is required and must be greater than zero"
        )

    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        raise ValidationError(
            f"{name} query parameter is required and must be greater than zero"
        )

    if value <= 0:
        raise ValidationError(
            f"{name} query parameter is required and must be greater than zero"
        )

    return value


def _optional_query_int(name: str) -> int | None:
    raw_value = request.args.get(name)

    if raw_value is None:
        return None

    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        raise ValidationError(
            f"{name} query parameter must be an integer"
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


def _service_error_response(exc):
    if isinstance(exc, NotFoundError):
        return jsonify({"error": str(exc)}), 404

    if isinstance(exc, (ValidationError, ConflictError)):
        return jsonify({"error": str(exc)}), 400

    raise exc


# ============================================================================
# INVENTORY ITEMS
# ============================================================================


@inventory_bp.get("/items")
@role_required(Role.ADMIN, Role.PHARMACIST)
def list_items():
    try:
        clinic_id = _required_query_int("clinic_id")

        filters = InventoryItemFilterSchema.model_validate(
            _query_without("clinic_id")
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

    except PydanticValidationError as exc:
        return _validation_response(exc)

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


@inventory_bp.get("/items/low-stock")
@role_required(Role.ADMIN, Role.PHARMACIST)
def low_stock_items():
    try:
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

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


@inventory_bp.get("/items/<int:item_id>")
@role_required(Role.ADMIN, Role.PHARMACIST)
def get_item(item_id: int):
    try:
        clinic_id = _optional_query_int("clinic_id")

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

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


@inventory_bp.post("/items")
@role_required(Role.ADMIN, Role.PHARMACIST)
def create_item():
    payload, error = _validate_json(
        InventoryItemCreateSchema
    )

    if error:
        return error

    try:
        item = create_inventory_item(
            **payload.model_dump(
                exclude_unset=True
            )
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

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


@inventory_bp.patch("/items/<int:item_id>")
@role_required(Role.ADMIN, Role.PHARMACIST)
def update_item(item_id: int):
    try:
        clinic_id = _required_query_int("clinic_id")

        payload, error = _validate_json(
            InventoryItemUpdateSchema
        )

        if error:
            return error

        item = update_inventory_item(
            item_id=item_id,
            clinic_id=clinic_id,
            **payload.model_dump(
                exclude_unset=True
            ),
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

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


@inventory_bp.post("/items/<int:item_id>/deactivate")
@role_required(Role.ADMIN)
def deactivate_item(item_id: int):
    try:
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

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


@inventory_bp.post("/items/<int:item_id>/reactivate")
@role_required(Role.ADMIN)
def reactivate_item(item_id: int):
    try:
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

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


# ============================================================================
# INVENTORY BATCHES
# ============================================================================


@inventory_bp.get("/items/<int:item_id>/batches")
@role_required(Role.ADMIN, Role.PHARMACIST)
def list_batches(item_id: int):
    try:
        clinic_id = _required_query_int("clinic_id")

        filters = InventoryBatchFilterSchema.model_validate(
            _query_without("clinic_id")
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

    except PydanticValidationError as exc:
        return _validation_response(exc)

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


@inventory_bp.get("/batches/<int:batch_id>")
@role_required(Role.ADMIN, Role.PHARMACIST)
def get_batch(batch_id: int):
    try:
        clinic_id = _optional_query_int("clinic_id")

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

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


@inventory_bp.post("/batches")
@role_required(Role.ADMIN, Role.PHARMACIST)
def create_batch():
    payload, error = _validate_json(
        InventoryBatchCreateSchema
    )

    if error:
        return error

    try:
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

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


@inventory_bp.patch("/batches/<int:batch_id>")
@role_required(Role.ADMIN, Role.PHARMACIST)
def update_batch(batch_id: int):
    try:
        clinic_id = _required_query_int("clinic_id")

        payload, error = _validate_json(
            InventoryBatchUpdateSchema
        )

        if error:
            return error

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

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


@inventory_bp.get("/batches/expiring")
@role_required(Role.ADMIN, Role.PHARMACIST)
def expiring_batches():
    try:
        clinic_id = _required_query_int("clinic_id")

        filters = ExpiringInventoryBatchQuerySchema.model_validate(
            _query_without("clinic_id")
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

    except PydanticValidationError as exc:
        return _validation_response(exc)

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


# ============================================================================
# STOCK MOVEMENTS
# ============================================================================


@inventory_bp.get("/items/<int:item_id>/movements")
@role_required(Role.ADMIN, Role.PHARMACIST)
def list_movements(item_id: int):
    try:
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

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


@inventory_bp.post("/movements")
@role_required(Role.ADMIN, Role.PHARMACIST)
def create_movement():
    payload, error = _validate_json(
        StockMovementCreateSchema
    )

    if error:
        return error

    try:
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

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


# ============================================================================
# SUPPLIERS
# ============================================================================


@inventory_bp.get("/suppliers")
@role_required(Role.ADMIN, Role.PHARMACIST)
def list_inventory_suppliers():
    try:
        clinic_id = _optional_query_int("clinic_id")

        filters = InventorySupplierFilterSchema.model_validate(
            _query_without("clinic_id")
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

    except PydanticValidationError as exc:
        return _validation_response(exc)

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


@inventory_bp.get("/suppliers/<int:supplier_id>")
@role_required(Role.ADMIN, Role.PHARMACIST)
def get_inventory_supplier(supplier_id: int):
    try:
        clinic_id = _optional_query_int("clinic_id")

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

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


@inventory_bp.post("/suppliers")
@role_required(Role.ADMIN, Role.PHARMACIST)
def create_inventory_supplier():
    payload, error = _validate_json(
        InventorySupplierCreateSchema
    )

    if error:
        return error

    try:
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

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


@inventory_bp.patch("/suppliers/<int:supplier_id>")
@role_required(Role.ADMIN)
def update_inventory_supplier(supplier_id: int):
    try:
        clinic_id = _optional_query_int("clinic_id")

        payload, error = _validate_json(
            InventorySupplierUpdateSchema
        )

        if error:
            return error

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

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


@inventory_bp.post("/suppliers/<int:supplier_id>/deactivate")
@role_required(Role.ADMIN)
def deactivate_inventory_supplier(supplier_id: int):
    try:
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

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


@inventory_bp.post("/suppliers/<int:supplier_id>/reactivate")
@role_required(Role.ADMIN)
def reactivate_inventory_supplier(supplier_id: int):
    try:
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

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


# ============================================================================
# INVENTORY TRANSFERS
# ============================================================================


@inventory_bp.get("/transfers")
@role_required(Role.ADMIN, Role.PHARMACIST)
def list_transfers():
    try:
        clinic_id = _required_query_int("clinic_id")

        filters = InventoryTransferFilterSchema.model_validate(
            _query_without("clinic_id")
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

    except PydanticValidationError as exc:
        return _validation_response(exc)

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


@inventory_bp.get("/transfers/<int:transfer_id>")
@role_required(Role.ADMIN, Role.PHARMACIST)
def get_transfer(transfer_id: int):
    try:
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

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


@inventory_bp.post("/transfers")
@role_required(Role.ADMIN, Role.PHARMACIST)
def create_transfer():
    payload, error = _validate_json(
        InventoryTransferCreateSchema
    )

    if error:
        return error

    try:
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

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


@inventory_bp.post("/transfers/<int:transfer_id>/approve")
@role_required(Role.ADMIN, Role.PHARMACIST)
def approve_transfer(transfer_id: int):
    payload, error = _validate_json(
        InventoryTransferApproveSchema
    )

    if error:
        return error

    try:
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

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


@inventory_bp.post("/transfers/<int:transfer_id>/complete")
@role_required(Role.ADMIN, Role.PHARMACIST)
def complete_transfer(transfer_id: int):
    payload, error = _validate_json(
        InventoryTransferCompleteSchema
    )

    if error:
        return error

    try:
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

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)


@inventory_bp.post("/transfers/<int:transfer_id>/cancel")
@role_required(Role.ADMIN, Role.PHARMACIST)
def cancel_transfer(transfer_id: int):
    payload, error = _validate_json(
        InventoryTransferCancelSchema
    )

    if error:
        return error

    try:
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

    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _service_error_response(exc)