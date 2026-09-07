from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.core.enums.role_enums import Role
from app.core.exceptions import ValidationError
from app.core.utils.decorators import role_required

from app.core.auth.user.models.user_model import User
from app.modules.staff.models.staff_model import Staff

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


def _required_query_int(
    name: str,
) -> int:
    value = request.args.get(
        name,
        type=int,
    )

    if value is None or value <= 0:
        raise ValidationError(
            f"{name} query parameter is required "
            f"and must be greater than zero"
        )

    return value


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


def _get_current_user() -> User:
    """
    Resolve the authenticated application user from JWT identity.

    The user identity comes from the JWT and is never accepted from
    request parameters or request bodies.
    """

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

    user = User.query.get(
        user_id
    )

    if user is None:
        raise ValidationError(
            "Authenticated user not found"
        )

    if not user.is_active:
        raise ValidationError(
            "Authenticated user is inactive"
        )

    return user


def _get_current_clinic_id() -> int:
    """
    Resolve the authenticated user's clinic.

    Pharmacy operations are tenant-scoped and therefore must never
    trust a client-supplied clinic_id.
    """

    user = _get_current_user()

    if user.clinic_id is None:
        raise ValidationError(
            "Authenticated user is not associated with a clinic"
        )

    return user.clinic_id


def _get_current_staff() -> Staff:
    """
    Resolve the Staff record belonging to the authenticated user.

    Pharmacy dispensing must use the authenticated staff actor rather
    than accepting dispensed_by_id from the request.
    """

    user = _get_current_user()

    staff = (
        Staff.query
        .filter(
            Staff.user_id == user.id,
            Staff.clinic_id == user.clinic_id,
        )
        .first()
    )

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
    )

    # Global drugs are allowed in every clinic.
    # Clinic-specific drugs must belong to this clinic.
    if (
        drug.clinic_id is not None
        and drug.clinic_id != clinic_id
    ):
        raise ValidationError(
            f"Drug {drug_id} does not belong to "
            f"clinic {clinic_id}"
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


@pharmacy_bp.patch("/drugs/<int:drug_id>")
@role_required(
    Role.ADMIN,
    Role.PHARMACIST,
)
def update_drug_route(
    drug_id: int,
):
    clinic_id = _get_current_clinic_id()

    drug = get_drug(
        drug_id=drug_id,
    )

    if (
        drug.clinic_id is not None
        and drug.clinic_id != clinic_id
    ):
        raise ValidationError(
            f"Drug {drug_id} does not belong to "
            f"clinic {clinic_id}"
        )

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

    drug = get_drug(
        drug_id=drug_id,
    )

    if (
        drug.clinic_id is not None
        and drug.clinic_id != clinic_id
    ):
        raise ValidationError(
            f"Drug {drug_id} does not belong to "
            f"clinic {clinic_id}"
        )

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

    drug = get_drug(
        drug_id=drug_id,
    )

    if (
        drug.clinic_id is not None
        and drug.clinic_id != clinic_id
    ):
        raise ValidationError(
            f"Drug {drug_id} does not belong to "
            f"clinic {clinic_id}"
        )

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
    )

    if batch.clinic_id != clinic_id:
        raise ValidationError(
            f"Drug batch {batch_id} does not belong to "
            f"clinic {clinic_id}"
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
    """
    Create a pharmacy dispensing transaction.

    clinic_id and dispensed_by_id are deliberately NOT accepted
    from the client.

    Both are derived from the authenticated user.
    """

    clinic_id = _get_current_clinic_id()
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
    )

    if record.prescription is None:
        raise ValidationError(
            f"Dispense record {dispense_record_id} "
            f"has no prescription"
        )

    if record.prescription.clinic_id != clinic_id:
        raise ValidationError(
            f"Dispense record {dispense_record_id} "
            f"does not belong to clinic {clinic_id}"
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

    records = list_dispense_records_for_prescription(
        prescription_id=prescription_id,
    )

    if records:
        prescription = records[0].prescription

        if prescription is None:
            raise ValidationError(
                f"Prescription {prescription_id} "
                f"has no prescription record"
            )

        if prescription.clinic_id != clinic_id:
            raise ValidationError(
                f"Prescription {prescription_id} "
                f"does not belong to clinic {clinic_id}"
            )

    else:
        # The service may legitimately return no dispensing records.
        # We therefore need to verify the prescription itself before
        # returning an empty result.
        from app.modules.pharmacy.services.pharmacy_service import (
            _get_prescription_or_404,
        )

        prescription = _get_prescription_or_404(
            prescription_id
        )

        if prescription.clinic_id != clinic_id:
            raise ValidationError(
                f"Prescription {prescription_id} "
                f"does not belong to clinic {clinic_id}"
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
    """
    Cancel a dispensing transaction.

    The authenticated clinic is verified at the route boundary.

    The service itself restores the exact stock recorded in
    DispenseItem and performs the transactional update.
    """

    clinic_id = _get_current_clinic_id()

    # Validate the body even though it currently contains no fields.
    DispenseRecordCancelSchema.model_validate(
        _json_body()
    )

    record = get_dispense_record(
        dispense_record_id=dispense_record_id,
    )

    if record.prescription is None:
        raise ValidationError(
            f"Dispense record {dispense_record_id} "
            f"has no prescription"
        )

    if record.prescription.clinic_id != clinic_id:
        raise ValidationError(
            f"Dispense record {dispense_record_id} "
            f"does not belong to clinic {clinic_id}"
        )

    record = cancel_dispense_record(
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