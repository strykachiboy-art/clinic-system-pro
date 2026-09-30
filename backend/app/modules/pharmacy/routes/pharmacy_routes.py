from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity
from sqlalchemy import select

from app.extensions import db

from app.core.auth.user.models.user_model import User
from app.core.enums.role_enums import Role
from app.core.exceptions import ValidationError
from app.core.utils.decorators import role_required

from app.modules.pharmacy.schemas.pharmacy_schema import (
    DispenseRecordCancelSchema,
    DispenseRecordCreateSchema,
    DispenseRecordListResponseSchema,
    DispenseRecordResponseSchema,
    DrugBatchCreateSchema,
    DrugBatchFilterSchema,
    DrugBatchListResponseSchema,
    DrugBatchResponseSchema,
    DrugCreateSchema,
    DrugFilterSchema,
    DrugListResponseSchema,
    DrugResponseSchema,
    DrugUpdateSchema,
    ExpiringDrugBatchListResponseSchema,
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

from app.modules.staff.models.staff_model import Staff


pharmacy_bp = Blueprint(
    "pharmacy",
    __name__,
    url_prefix="/pharmacy",
)


# ============================================================================
# ROUTE HELPERS
# ============================================================================


def _json_body() -> dict:
    payload = request.get_json(
        silent=True
    )

    if payload is None:
        return {}

    if not isinstance(payload, dict):
        raise ValidationError(
            "JSON body must be an object"
        )

    return payload


def _serialize(
    schema,
    value,
) -> dict:
    return (
        schema
        .model_validate(value)
        .model_dump(
            mode="json"
        )
    )


def _get_current_user() -> User:
    identity = get_jwt_identity()

    try:
        user_id = int(identity)
    except (
        TypeError,
        ValueError,
    ):
        raise ValidationError(
            "Invalid authentication identity"
        )

    if user_id <= 0:
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
    user = _get_current_user()

    if user.clinic_id is None:
        raise ValidationError(
            "Authenticated user is not associated with a clinic"
        )

    return user.clinic_id


def _get_current_staff() -> Staff:
    user = _get_current_user()

    if user.clinic_id is None:
        raise ValidationError(
            "Authenticated user is not associated with a clinic"
        )

    stmt = (
        select(Staff)
        .where(
            Staff.user_id == user.id,
            Staff.clinic_id == user.clinic_id,
        )
    )

    staff = db.session.execute(
        stmt
    ).scalar_one_or_none()

    if staff is None:
        raise ValidationError(
            "Authenticated user is not associated with a staff record"
        )

    return staff


# ============================================================================
# DRUG CATALOG
# ============================================================================


@pharmacy_bp.get("/drugs")
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def list_drugs_route():
    clinic_id = _get_current_clinic_id()

    filters = DrugFilterSchema.model_validate(
        request.args.to_dict()
    )

    result = list_drugs(
        clinic_id=clinic_id,
        include_inactive=filters.include_inactive,
        page=filters.page,
        per_page=filters.per_page,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                DrugListResponseSchema,
                result,
            ),
        }
    ), 200


@pharmacy_bp.get(
    "/drugs/<int:drug_id>"
)
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def get_drug_route(
    drug_id: int,
):
    clinic_id = _get_current_clinic_id()

    drug = get_drug(
        drug_id=drug_id,
        clinic_id=clinic_id,
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
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def create_drug_route():
    clinic_id = _get_current_clinic_id()

    payload = DrugCreateSchema.model_validate(
        _json_body()
    )

    drug = create_drug(
        clinic_id=clinic_id,
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
    ), 201


@pharmacy_bp.patch(
    "/drugs/<int:drug_id>"
)
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def update_drug_route(
    drug_id: int,
):
    clinic_id = _get_current_clinic_id()

    payload = DrugUpdateSchema.model_validate(
        _json_body()
    )

    drug = update_drug(
        drug_id=drug_id,
        clinic_id=clinic_id,
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


@pharmacy_bp.post(
    "/drugs/<int:drug_id>/activate"
)
@role_required(
    Role.ADMIN
)
def activate_drug_route(
    drug_id: int,
):
    clinic_id = _get_current_clinic_id()

    drug = set_drug_active_status(
        drug_id=drug_id,
        clinic_id=clinic_id,
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


@pharmacy_bp.post(
    "/drugs/<int:drug_id>/deactivate"
)
@role_required(
    Role.ADMIN
)
def deactivate_drug_route(
    drug_id: int,
):
    clinic_id = _get_current_clinic_id()

    drug = set_drug_active_status(
        drug_id=drug_id,
        clinic_id=clinic_id,
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


@pharmacy_bp.get(
    "/drugs/<int:drug_id>/batches"
)
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def list_batches_route(
    drug_id: int,
):
    clinic_id = _get_current_clinic_id()

    filters = DrugBatchFilterSchema.model_validate(
        request.args.to_dict()
    )

    result = list_batches(
        drug_id=drug_id,
        clinic_id=clinic_id,
        include_expired=filters.include_expired,
        page=filters.page,
        per_page=filters.per_page,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                DrugBatchListResponseSchema,
                result,
            ),
        }
    ), 200


@pharmacy_bp.get(
    "/batches/expiring"
)
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def list_expiring_batches_route():
    clinic_id = _get_current_clinic_id()

    filters = ExpiringDrugBatchQuerySchema.model_validate(
        request.args.to_dict()
    )

    result = list_expiring_batches(
        clinic_id=clinic_id,
        days=filters.days,
        page=filters.page,
        per_page=filters.per_page,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                ExpiringDrugBatchListResponseSchema,
                result,
            ),
        }
    ), 200


@pharmacy_bp.get(
    "/batches/<int:batch_id>"
)
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def get_batch_route(
    batch_id: int,
):
    clinic_id = _get_current_clinic_id()

    batch = get_batch(
        batch_id=batch_id,
        clinic_id=clinic_id,
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
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def create_batch_route():
    clinic_id = _get_current_clinic_id()

    payload = DrugBatchCreateSchema.model_validate(
        _json_body()
    )

    batch = add_batch(
        clinic_id=clinic_id,
        **payload.model_dump(
            exclude_unset=True
        ),
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


@pharmacy_bp.get(
    "/drugs/<int:drug_id>/stock-summary"
)
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def get_stock_summary_route(
    drug_id: int,
):
    clinic_id = _get_current_clinic_id()

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
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def create_dispense_record_route():
    user = _get_current_user()

    if user.clinic_id is None:
        raise ValidationError(
            "Authenticated user is not associated with a clinic"
        )

    clinic_id = user.clinic_id

    staff = _get_current_staff()

    payload = DispenseRecordCreateSchema.model_validate(
        _json_body()
    )

    record = create_dispense_record(
        clinic_id=clinic_id,
        prescription_id=payload.prescription_id,
        dispensed_by_id=staff.id,
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


@pharmacy_bp.get(
    "/dispense/<int:dispense_record_id>"
)
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def get_dispense_record_route(
    dispense_record_id: int,
):
    clinic_id = _get_current_clinic_id()

    record = get_dispense_record(
        dispense_record_id=dispense_record_id,
        clinic_id=clinic_id,
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


@pharmacy_bp.get(
    "/prescriptions/<int:prescription_id>/dispense-records"
)
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def list_dispense_records_route(
    prescription_id: int,
):
    clinic_id = _get_current_clinic_id()

    filters = {
        "page": request.args.get(
            "page",
            1,
            type=int,
        ),
        "per_page": request.args.get(
            "per_page",
            50,
            type=int,
        ),
    }

    class _DispenseRecordPaginationInput:
        def __init__(
            self,
            page: int,
            per_page: int,
        ):
            self.page = page
            self.per_page = per_page

    pagination = _DispenseRecordPaginationInput(
        page=filters["page"],
        per_page=filters["per_page"],
    )

    if pagination.page < 1:
        raise ValidationError(
            "page must be a positive integer"
        )

    if pagination.per_page < 1:
        raise ValidationError(
            "per_page must be a positive integer"
        )

    if pagination.per_page > 500:
        raise ValidationError(
            "per_page cannot exceed 500"
        )

    allowed_query_keys = {
        "page",
        "per_page",
    }

    unknown_keys = (
        set(request.args.keys())
        - allowed_query_keys
    )

    if unknown_keys:
        raise ValidationError(
            "Unknown query parameters: "
            + ", ".join(
                sorted(unknown_keys)
            )
        )

    result = list_dispense_records_for_prescription(
        prescription_id=prescription_id,
        clinic_id=clinic_id,
        page=pagination.page,
        per_page=pagination.per_page,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                DispenseRecordListResponseSchema,
                result,
            ),
        }
    ), 200


@pharmacy_bp.post(
    "/dispense/<int:dispense_record_id>/cancel"
)
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def cancel_dispense_record_route(
    dispense_record_id: int,
):
    clinic_id = _get_current_clinic_id()

    DispenseRecordCancelSchema.model_validate(
        _json_body()
    )

    record = cancel_dispense_record(
        dispense_record_id=dispense_record_id,
        clinic_id=clinic_id,
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