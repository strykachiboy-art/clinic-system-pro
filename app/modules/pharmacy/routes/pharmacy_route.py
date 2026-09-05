from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.core.enums.role_enums import Role
from app.core.exceptions import ValidationError
from app.core.utils.decorators import role_required

from app.modules.pharmacy.schemas.pharmacy_schema import (
    DispenseRecordCancelSchema,
    DispenseRecordCreateSchema,
    DispenseRecordResponseSchema,
    DrugBatchCreateSchema,
    DrugBatchFilterSchema,
    DrugBatchResponseSchema,
    DrugCreateSchema,
    DrugFilterSchema,
    DrugResponseSchema,
    DrugUpdateSchema,
    ExpiringDrugBatchQuerySchema,
    StockSummaryResponseSchema,
)

from app.modules.pharmacy.services.pharmacy_service import (
    add_batch,
    cancel_dispense_record,
    create_dispense_record,
    create_drug,
    get_batch,
    get_dispense_record,
    get_drug,
    get_stock_summary,
    list_batches,
    list_dispense_records_for_prescription,
    list_drugs,
    list_expiring_batches,
    set_drug_active_status,
    update_drug,
)


pharmacy_bp = Blueprint(
    "pharmacy",
    __name__,
    url_prefix="/pharmacy",
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
# DRUG CATALOG
# ============================================================================

@pharmacy_bp.get("/drugs")
@role_required(Role.ADMIN, Role.PHARMACIST)
def list_drugs_route():
    clinic_id = request.args.get("clinic_id", type=int)

    filters = DrugFilterSchema.model_validate(
        request.args.to_dict()
    )

    drugs = list_drugs(
        clinic_id=clinic_id,
        include_inactive=filters.include_inactive,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize_many(
                DrugResponseSchema,
                drugs,
            ),
        }
    ), 200


@pharmacy_bp.get("/drugs/<int:drug_id>")
@role_required(Role.ADMIN, Role.PHARMACIST)
def get_drug_route(drug_id: int):
    drug = get_drug(
        drug_id=drug_id,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                DrugResponseSchema,
                drug,
            ),
        }
    ), 200


@pharmacy_bp.post("/drugs")
@role_required(Role.ADMIN, Role.PHARMACIST)
def create_drug_route():
    payload = DrugCreateSchema.model_validate(
        _json_body()
    )

    drug = create_drug(
        **payload.model_dump(
            exclude_unset=True
        )
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                DrugResponseSchema,
                drug,
            ),
        }
    ), 201


@pharmacy_bp.patch("/drugs/<int:drug_id>")
@role_required(Role.ADMIN, Role.PHARMACIST)
def update_drug_route(drug_id: int):
    payload = DrugUpdateSchema.model_validate(
        _json_body()
    )

    drug = update_drug(
        drug_id=drug_id,
        **payload.model_dump(
            exclude_unset=True
        ),
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                DrugResponseSchema,
                drug,
            ),
        }
    ), 200


@pharmacy_bp.post("/drugs/<int:drug_id>/activate")
@role_required(Role.ADMIN)
def activate_drug_route(drug_id: int):
    drug = set_drug_active_status(
        drug_id=drug_id,
        is_active=True,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                DrugResponseSchema,
                drug,
            ),
        }
    ), 200


@pharmacy_bp.post("/drugs/<int:drug_id>/deactivate")
@role_required(Role.ADMIN)
def deactivate_drug_route(drug_id: int):
    drug = set_drug_active_status(
        drug_id=drug_id,
        is_active=False,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                DrugResponseSchema,
                drug,
            ),
        }
    ), 200


# ============================================================================
# BATCHES / INVENTORY
# ============================================================================

@pharmacy_bp.get("/drugs/<int:drug_id>/batches")
@role_required(Role.ADMIN, Role.PHARMACIST)
def list_batches_route(drug_id: int):
    clinic_id = request.args.get("clinic_id", type=int)

    filters = DrugBatchFilterSchema.model_validate(
        request.args.to_dict()
    )

    batches = list_batches(
        drug_id=drug_id,
        clinic_id=clinic_id,
        include_expired=filters.include_expired,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize_many(
                DrugBatchResponseSchema,
                batches,
            ),
        }
    ), 200


@pharmacy_bp.get("/batches/expiring")
@role_required(Role.ADMIN, Role.PHARMACIST)
def list_expiring_batches_route():
    clinic_id = _required_query_int("clinic_id")

    filters = ExpiringDrugBatchQuerySchema.model_validate(
        request.args.to_dict()
    )

    batches = list_expiring_batches(
        clinic_id=clinic_id,
        days=filters.days,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize_many(
                DrugBatchResponseSchema,
                batches,
            ),
        }
    ), 200


@pharmacy_bp.get("/batches/<int:batch_id>")
@role_required(Role.ADMIN, Role.PHARMACIST)
def get_batch_route(batch_id: int):
    batch = get_batch(
        batch_id=batch_id,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                DrugBatchResponseSchema,
                batch,
            ),
        }
    ), 200


@pharmacy_bp.post("/batches")
@role_required(Role.ADMIN, Role.PHARMACIST)
def create_batch_route():
    payload = DrugBatchCreateSchema.model_validate(
        _json_body()
    )

    batch = add_batch(
        **payload.model_dump(
            exclude_unset=True
        )
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                DrugBatchResponseSchema,
                batch,
            ),
        }
    ), 201


@pharmacy_bp.get("/drugs/<int:drug_id>/stock-summary")
@role_required(Role.ADMIN, Role.PHARMACIST)
def get_stock_summary_route(drug_id: int):
    clinic_id = _required_query_int("clinic_id")

    summary = get_stock_summary(
        clinic_id=clinic_id,
        drug_id=drug_id,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                StockSummaryResponseSchema,
                summary,
            ),
        }
    ), 200


# ============================================================================
# DISPENSING
# ============================================================================

@pharmacy_bp.post("/dispense")
@role_required(Role.ADMIN, Role.PHARMACIST)
def create_dispense_record_route():
    payload = DispenseRecordCreateSchema.model_validate(
        _json_body()
    )

    record = create_dispense_record(
        clinic_id=payload.clinic_id,
        prescription_id=payload.prescription_id,
        dispensed_by_id=payload.dispensed_by_id,
        items=payload.to_service_items(),
        notes=payload.notes,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                DispenseRecordResponseSchema,
                record,
            ),
        }
    ), 201


@pharmacy_bp.get("/dispense/<int:dispense_record_id>")
@role_required(Role.ADMIN, Role.PHARMACIST)
def get_dispense_record_route(dispense_record_id: int):
    record = get_dispense_record(
        dispense_record_id=dispense_record_id,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                DispenseRecordResponseSchema,
                record,
            ),
        }
    ), 200


@pharmacy_bp.get("/prescriptions/<int:prescription_id>/dispense-records")
@role_required(Role.ADMIN, Role.PHARMACIST)
def list_dispense_records_route(prescription_id: int):
    records = list_dispense_records_for_prescription(
        prescription_id=prescription_id,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize_many(
                DispenseRecordResponseSchema,
                records,
            ),
        }
    ), 200


@pharmacy_bp.post("/dispense/<int:dispense_record_id>/cancel")
@role_required(Role.ADMIN, Role.PHARMACIST)
def cancel_dispense_record_route(dispense_record_id: int):
    payload = DispenseRecordCancelSchema.model_validate(
        _json_body()
    )

    record = cancel_dispense_record(
        clinic_id=payload.clinic_id,
        dispense_record_id=dispense_record_id,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                DispenseRecordResponseSchema,
                record,
            ),
        }
    ), 200