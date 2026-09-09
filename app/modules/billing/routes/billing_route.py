from flask import Blueprint, g, jsonify, request
from flask_jwt_extended import get_jwt_identity
from pydantic import ValidationError as PydanticValidationError

from app.extensions import db

from app.core.auth.user.models.user_model import User
from app.core.enums.role_enums import Role
from app.core.exceptions import (
    DomainError,
    ValidationError,
)
from app.core.utils.decorators import role_required

from app.modules.billing.schemas.billing_schema import (
    CreateInvoiceRequest,
    InvoiceResponse,
    OutstandingInvoiceQuery,
    OutstandingInvoiceResponse,
    PaymentResponse,
    RecordPaymentRequest,
)

from app.modules.billing.services.billing_service import (
    create_invoice,
    get_outstanding_invoices,
    mark_overdue_invoices,
    record_payment,
)


billing_bp = Blueprint(
    "billing",
    __name__,
    url_prefix="/api/billing",
)


# ============================================================================
# Authentication / Clinic Helpers
# ============================================================================


def _current_user():
    identity = get_jwt_identity()

    try:
        user_id = int(identity)
    except (TypeError, ValueError):
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


def _current_clinic_id():
    user = _current_user()

    if user.clinic_id is None:
        raise ValidationError(
            "Authenticated user is not assigned "
            "to a clinic"
        )

    if (
        isinstance(user.clinic_id, bool)
        or not isinstance(user.clinic_id, int)
        or user.clinic_id <= 0
    ):
        raise ValidationError(
            "Invalid clinic identity"
        )

    return user.clinic_id


# ============================================================================
# Validation Helpers
# ============================================================================


def _sanitize_pydantic_errors(errors):
    sanitized = []

    for error in errors:
        item = dict(error)

        if (
            "ctx" in item
            and isinstance(item["ctx"], dict)
        ):
            item["ctx"] = {
                key: str(value)
                for key, value in item["ctx"].items()
            }

        sanitized.append(item)

    return sanitized


def _payload(schema):
    raw = request.get_json(
        silent=True
    )

    if raw is None:
        raw = {}

    if not isinstance(raw, dict):
        return (
            None,
            (
                jsonify(
                    {
                        "success": False,
                        "error": (
                            "Request body must be "
                            "a JSON object"
                        ),
                    }
                ),
                422,
            ),
        )

    try:
        payload = schema.model_validate(
            raw
        )

        return payload, None

    except PydanticValidationError:
        return (
            None,
            (
                jsonify(
                    {
                        "success": False,
                        "error": (
                            "Invalid request payload"
                        ),
                    }
                ),
                422,
            ),
        )


def _query_payload(schema):
    data = request.args.to_dict()

    try:
        if "page" in data:
            data["page"] = int(
                data["page"]
            )

        if "per_page" in data:
            data["per_page"] = int(
                data["per_page"]
            )

    except (TypeError, ValueError):
        return (
            None,
            (
                jsonify(
                    {
                        "success": False,
                        "error": (
                            "Invalid query parameters"
                        ),
                    }
                ),
                422,
            ),
        )

    try:
        payload = schema.model_validate(
            data
        )

        return payload, None

    except PydanticValidationError:
        return (
            None,
            (
                jsonify(
                    {
                        "success": False,
                        "error": (
                            "Invalid query parameters"
                        ),
                    }
                ),
                422,
            ),
        )


def _serialize_response(
    schema,
    value,
):
    return (
        schema.model_validate(
            value
        ).model_dump(
            mode="json"
        )
    )


def _serialize_page(
    page,
    schema,
):
    return {
        "items": [
            _serialize_response(
                schema,
                item,
            )
            for item in page.items
        ],
        "page": page.page,
        "per_page": page.per_page,
        "total": page.total,
        "pages": page.pages,
        "has_next": page.has_next,
        "has_prev": page.has_prev,
    }


def _domain_error_response(exc):
    return (
        jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ),
        exc.status_code,
    )


# ============================================================================
# Invoice Creation
# ============================================================================


@billing_bp.route(
    "/invoices",
    methods=["POST"],
)
@role_required(Role.ADMIN)
def create_invoice_route():
    payload, error = _payload(
        CreateInvoiceRequest
    )

    if error:
        return error

    try:
        clinic_id = _current_clinic_id()

        invoice = create_invoice(
            clinic_id=clinic_id,
            patient_id=payload.patient_id,
            appointment_id=payload.appointment_id,
            due_date=payload.due_date,
            is_insurance_claim=(
                payload.is_insurance_claim
            ),
            insurance_provider=(
                payload.insurance_provider
            ),
            items=[
                item.model_dump()
                for item in payload.items
            ],
        )

        return (
            jsonify(
                {
                    "success": True,
                    "data": _serialize_response(
                        InvoiceResponse,
                        invoice,
                    ),
                }
            ),
            201,
        )

    except DomainError as exc:
        return _domain_error_response(exc)


# ============================================================================
# Outstanding Invoices
# ============================================================================


@billing_bp.route(
    "/invoices/outstanding",
    methods=["GET"],
)
@role_required(Role.ADMIN)
def get_outstanding_invoices_route():
    payload, error = _query_payload(
        OutstandingInvoiceQuery
    )

    if error:
        return error

    try:
        clinic_id = _current_clinic_id()

        invoices = get_outstanding_invoices(
            clinic_id=clinic_id,
            page=payload.page,
            per_page=payload.per_page,
        )

        return (
            jsonify(
                {
                    "success": True,
                    "data": _serialize_page(
                        invoices,
                        OutstandingInvoiceResponse,
                    ),
                }
            ),
            200,
        )

    except DomainError as exc:
        return _domain_error_response(exc)


# ============================================================================
# Payment Recording
# ============================================================================


@billing_bp.route(
    "/payments",
    methods=["POST"],
)
@role_required(Role.ADMIN)
def record_payment_route():
    payload, error = _payload(
        RecordPaymentRequest
    )

    if error:
        return error

    try:
        clinic_id = _current_clinic_id()

        payment = record_payment(
            clinic_id=clinic_id,
            invoice_id=payload.invoice_id,
            amount=payload.amount,
            method=payload.method,
            gateway=payload.gateway,
            reference=payload.reference,
            gateway_transaction_id=(
                payload.gateway_transaction_id
            ),
        )

        return (
            jsonify(
                {
                    "success": True,
                    "data": _serialize_response(
                        PaymentResponse,
                        payment,
                    ),
                }
            ),
            201,
        )

    except DomainError as exc:
        return _domain_error_response(exc)


# ============================================================================
# Mark Overdue Invoices
# ============================================================================


@billing_bp.route(
    "/invoices/mark-overdue",
    methods=["POST"],
)
@role_required(Role.ADMIN)
def mark_overdue_invoices_route():
    try:
        clinic_id = _current_clinic_id()

        updated_count = mark_overdue_invoices(
            clinic_id=clinic_id
        )

        return (
            jsonify(
                {
                    "success": True,
                    "data": {
                        "updated_count": updated_count,
                    },
                }
            ),
            200,
        )

    except DomainError as exc:
        return _domain_error_response(exc)