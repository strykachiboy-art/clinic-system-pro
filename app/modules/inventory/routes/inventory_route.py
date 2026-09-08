from __future__ import annotations

import json

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select

from app.extensions import db
from app.core.auth.user.models.user_model import User
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

from app.modules.staff.models.staff_model import Staff


# ============================================================================
# BLUEPRINT
# ============================================================================

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
        raise ValidationError(
            "JSON body must be an object"
        )

    return payload


def _sanitize_pydantic_errors(
    exc: PydanticValidationError,
) -> list[dict]:
    sanitized: list[dict] = []

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
        return (
            schema.model_validate(
                _json_body()
            ),
            None,
        )

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


def _serialize(
    schema,
    value,
):
    return schema.model_validate(
        value
    ).model_dump(
        mode="json"
    )


def _serialize_many(
    schema,
    values,
):
    return [
        schema.model_validate(
            value
        ).model_dump(
            mode="json"
        )
        for value in values
    ]


def _get_current_user():
    """
    Return the authenticated user.
    """
    identity = get_jwt_identity()

    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        raise ValidationError(
            "Invalid authentication identity"
        )

    user = db.session.get(
        User,
        user_id,
    )

    if user is None:
        raise ValidationError(
            "Authenticated user could not be resolved"
        )

    if not user.is_active:
        raise ValidationError(
            "User account is inactive"
        )

    return user


def _get_current_clinic_id() -> int:
    """
    Resolve the authoritative clinic from the authenticated user.

    Client-supplied clinic_id values are never used as the
    authoritative tenant identity.
    """
    user = _get_current_user()

    if user.clinic_id is None or user.clinic_id <= 0:
        raise ValidationError(
            "Authenticated user is not associated "
            "with a clinic"
        )

    return user.clinic_id


def _get_current_staff_id() -> int:
    """
    Resolve the Staff record belonging to the authenticated user.

    Actor identity is always derived from JWT context.
    """
    user = _get_current_user()

    statement = (
        select(Staff)
        .where(
            Staff.user_id == user.id,
            Staff.clinic_id == user.clinic_id,
        )
    )

    staff = (
        db.session.execute(
            statement
        )
        .scalars()
        .first()
    )

    if staff is None:
        raise ValidationError(
            "Authenticated user is not associated "
            "with a staff record"
        )

    return staff.id


def _get_requested_clinic_id(
    payload_clinic_id: int | None,
    *,
    allow_global: bool = False,
) -> int | None:
    """
    Validate a client-supplied clinic ID against the
    authenticated clinic.

    A client cannot select another clinic.

    When allow_global=True, None may represent a global/shared
    resource. Explicit global creation is restricted to ADMIN.
    """
    current_clinic_id = _get_current_clinic_id()

    if payload_clinic_id is None:
        if allow_global:
            user = _get_current_user()

            if getattr(user, "role", None) == Role.ADMIN:
                return None

        return current_clinic_id

    if payload_clinic_id != current_clinic_id:
        raise ValidationError(
            "Requested clinic does not match "
            "the authenticated user's clinic"
        )

    return current_clinic_id


def _service_error_response(
    exc,
):
    if isinstance(exc, NotFoundError):
        return jsonify(
            {
                "error": str(exc),
            }
        ), 404

    if isinstance(exc, ConflictError):
        return jsonify(
            {
                "error": str(exc),
            }
        ), 409

    if isinstance(exc, ValidationError):
        return jsonify(
            {
                "error": str(exc),
            }
        ), 400

    raise exc


# ============================================================================
# INVENTORY ITEMS
# ============================================================================

@inventory_bp.get("/items")
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def list_items():
    try:
        clinic_id = _get_current_clinic_id()

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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


@inventory_bp.get("/items/low-stock")
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def low_stock_items():
    try:
        clinic_id = _get_current_clinic_id()

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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


@inventory_bp.get("/items/<int:item_id>")
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def get_item(
    item_id: int,
):
    try:
        clinic_id = _get_current_clinic_id()

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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


@inventory_bp.post("/items")
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def create_item():
    payload, error = _validate_json(
        InventoryItemCreateSchema
    )

    if error:
        return error

    try:
        clinic_id = _get_current_clinic_id()
        staff_id = _get_current_staff_id()

        item_data = payload.model_dump(
            exclude_unset=True
        )

        # JWT-derived tenant and actor identity are authoritative.
        item_data["clinic_id"] = clinic_id
        item_data["performed_by_id"] = staff_id

        item = create_inventory_item(
            **item_data
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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


@inventory_bp.patch("/items/<int:item_id>")
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def update_item(
    item_id: int,
):
    try:
        clinic_id = _get_current_clinic_id()

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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


@inventory_bp.post("/items/<int:item_id>/deactivate")
@role_required(Role.ADMIN)
def deactivate_item(
    item_id: int,
):
    try:
        clinic_id = _get_current_clinic_id()

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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


@inventory_bp.post("/items/<int:item_id>/reactivate")
@role_required(Role.ADMIN)
def reactivate_item(
    item_id: int,
):
    try:
        clinic_id = _get_current_clinic_id()

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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


# ============================================================================
# INVENTORY BATCHES
# ============================================================================

@inventory_bp.get("/items/<int:item_id>/batches")
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def list_batches(
    item_id: int,
):
    try:
        clinic_id = _get_current_clinic_id()

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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


@inventory_bp.get("/batches/<int:batch_id>")
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def get_batch(
    batch_id: int,
):
    try:
        clinic_id = _get_current_clinic_id()

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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


@inventory_bp.post("/batches")
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def create_batch():
    payload, error = _validate_json(
        InventoryBatchCreateSchema
    )

    if error:
        return error

    try:
        clinic_id = _get_current_clinic_id()

        batch_data = payload.model_dump(
            exclude_unset=True
        )

        # InventoryBatch derives tenancy through its item.
        # The compatibility clinic_id is forced to JWT clinic.
        batch_data["clinic_id"] = clinic_id

        batch = create_inventory_batch(
            **batch_data
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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


@inventory_bp.patch("/batches/<int:batch_id>")
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def update_batch(
    batch_id: int,
):
    try:
        clinic_id = _get_current_clinic_id()

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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


@inventory_bp.get("/batches/expiring")
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def expiring_batches():
    try:
        clinic_id = _get_current_clinic_id()

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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


# ============================================================================
# STOCK MOVEMENTS
# ============================================================================

@inventory_bp.get("/items/<int:item_id>/movements")
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def list_movements(
    item_id: int,
):
    try:
        clinic_id = _get_current_clinic_id()

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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


@inventory_bp.post("/movements")
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def create_movement():
    payload, error = _validate_json(
        StockMovementCreateSchema
    )

    if error:
        return error

    try:
        clinic_id = _get_current_clinic_id()
        staff_id = _get_current_staff_id()

        movement_data = payload.model_dump(
            exclude_unset=True
        )

        # JWT-derived tenant and actor identity are authoritative.
        movement_data["clinic_id"] = clinic_id
        movement_data["performed_by_id"] = staff_id

        movement = record_stock_movement(
            **movement_data
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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


# ============================================================================
# SUPPLIERS
# ============================================================================

@inventory_bp.get("/suppliers")
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def list_inventory_suppliers():
    try:
        clinic_id = _get_current_clinic_id()

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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


@inventory_bp.get("/suppliers/<int:supplier_id>")
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def get_inventory_supplier(
    supplier_id: int,
):
    try:
        clinic_id = _get_current_clinic_id()

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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


@inventory_bp.post("/suppliers")
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def create_inventory_supplier():
    payload, error = _validate_json(
        InventorySupplierCreateSchema
    )

    if error:
        return error

    try:
        supplier_data = payload.model_dump(
            exclude_unset=True
        )

        current_clinic_id = _get_current_clinic_id()

        if "clinic_id" in payload.model_fields_set:
            requested_clinic_id = payload.clinic_id

            # Explicit null means global supplier.
            # Only ADMIN may create one.
            if requested_clinic_id is None:
                user = _get_current_user()

                if getattr(user, "role", None) != Role.ADMIN:
                    raise ValidationError(
                        "Only administrators can create "
                        "global suppliers"
                    )

                supplier_data["clinic_id"] = None

            elif requested_clinic_id != current_clinic_id:
                raise ValidationError(
                    "Requested clinic does not match "
                    "the authenticated user's clinic"
                )

            else:
                supplier_data["clinic_id"] = (
                    current_clinic_id
                )

        else:
            # Omitted clinic_id means the authenticated clinic.
            supplier_data["clinic_id"] = (
                current_clinic_id
            )

        supplier = create_supplier(
            **supplier_data
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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


@inventory_bp.patch("/suppliers/<int:supplier_id>")
@role_required(Role.ADMIN)
def update_inventory_supplier(
    supplier_id: int,
):
    try:
        clinic_id = _get_current_clinic_id()

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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


@inventory_bp.post(
    "/suppliers/<int:supplier_id>/deactivate"
)
@role_required(Role.ADMIN)
def deactivate_inventory_supplier(
    supplier_id: int,
):
    try:
        clinic_id = _get_current_clinic_id()

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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


@inventory_bp.post(
    "/suppliers/<int:supplier_id>/reactivate"
)
@role_required(Role.ADMIN)
def reactivate_inventory_supplier(
    supplier_id: int,
):
    try:
        clinic_id = _get_current_clinic_id()

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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


# ============================================================================
# INVENTORY TRANSFERS
# ============================================================================

@inventory_bp.get("/transfers")
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def list_transfers():
    try:
        clinic_id = _get_current_clinic_id()

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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


@inventory_bp.get(
    "/transfers/<int:transfer_id>"
)
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def get_transfer(
    transfer_id: int,
):
    try:
        clinic_id = _get_current_clinic_id()

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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


@inventory_bp.post("/transfers")
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def create_transfer():
    payload, error = _validate_json(
        InventoryTransferCreateSchema
    )

    if error:
        return error

    try:
        clinic_id = _get_current_clinic_id()
        staff_id = _get_current_staff_id()

        transfer_data = payload.model_dump(
            exclude_unset=True
        )

        supplied_source_clinic_id = (
            transfer_data.get(
                "source_clinic_id"
            )
        )

        if supplied_source_clinic_id != clinic_id:
            raise ValidationError(
                "Source clinic does not match "
                "the authenticated user's clinic"
            )

        transfer_data["source_clinic_id"] = (
            clinic_id
        )
        transfer_data["requested_by_id"] = (
            staff_id
        )

        transfer = create_inventory_transfer(
            **transfer_data
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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


@inventory_bp.post(
    "/transfers/<int:transfer_id>/approve"
)
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def approve_transfer(
    transfer_id: int,
):
    payload, error = _validate_json(
        InventoryTransferApproveSchema
    )

    if error:
        return error

    # Compatibility field is intentionally ignored.
    # Actor identity comes from JWT.
    del payload

    try:
        clinic_id = _get_current_clinic_id()
        staff_id = _get_current_staff_id()

        transfer = approve_inventory_transfer(
            transfer_id=transfer_id,
            clinic_id=clinic_id,
            approved_by_id=staff_id,
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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


@inventory_bp.post(
    "/transfers/<int:transfer_id>/complete"
)
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def complete_transfer(
    transfer_id: int,
):
    payload, error = _validate_json(
        InventoryTransferCompleteSchema
    )

    if error:
        return error

    # Compatibility field is intentionally ignored.
    # Actor identity comes from JWT.
    del payload

    try:
        clinic_id = _get_current_clinic_id()
        staff_id = _get_current_staff_id()

        transfer = complete_inventory_transfer(
            transfer_id=transfer_id,
            clinic_id=clinic_id,
            performed_by_id=staff_id,
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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)


@inventory_bp.post(
    "/transfers/<int:transfer_id>/cancel"
)
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def cancel_transfer(
    transfer_id: int,
):
    payload, error = _validate_json(
        InventoryTransferCancelSchema
    )

    if error:
        return error

    try:
        clinic_id = _get_current_clinic_id()
        staff_id = _get_current_staff_id()

        transfer = cancel_inventory_transfer(
            transfer_id=transfer_id,
            clinic_id=clinic_id,
            cancelled_by_id=staff_id,
            reason=payload.reason,
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

    except (
        ValidationError,
        ConflictError,
        NotFoundError,
    ) as exc:
        return _service_error_response(exc)