from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError as PydanticValidationError

from app.core.auth.user.models.user_model import User
from app.core.enums.role_enums import Role
from app.core.exceptions import DomainError, ValidationError
from app.core.utils.decorators import role_required

from app.modules.billing.schemas.billing_schema import (
    CreateInvoiceRequest,
    InvoiceResponse,
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
    user_id = getattr(
        g,
        "current_user_id",
        None,
    )

    if user_id is None:
        raise ValidationError(
            "Authenticated user could not be resolved"
        )

    user = User.query.get(user_id)

    if user is None:
        raise ValidationError(
            "Authenticated user could not be resolved"
        )

    return user


def _current_clinic_id():
    user = _current_user()

    if user.clinic_id is None:
        raise ValidationError(
            "Authenticated user is not assigned "
            "to a clinic"
        )

    return user.clinic_id


# ============================================================================
# Validation Helpers
# ============================================================================


def _sanitize_pydantic_errors(errors):
    """
    Make Pydantic validation errors JSON serializable.

    Pydantic v2 may include non-serializable exception
    objects inside the ctx field.
    """

    sanitized = []

    for error in errors:
        item = dict(error)

        if "ctx" in item and isinstance(
            item["ctx"],
            dict,
        ):
            item["ctx"] = {
                key: str(value)
                for key, value in item["ctx"].items()
            }

        sanitized.append(item)

    return sanitized


def _payload(schema):
    try:
        payload = schema.model_validate(
            request.get_json(silent=True) or {}
        )

        return payload, None

    except PydanticValidationError as exc:
        return (
            None,
            (
                jsonify(
                    {
                        "success": False,
                        "error": _sanitize_pydantic_errors(
                            exc.errors()
                        ),
                    }
                ),
                422,
            ),
        )


def _serialize_response(schema, value):
    return schema.model_validate(
        value
    ).model_dump(
        mode="json"
    )


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
    try:
        clinic_id = _current_clinic_id()

        invoices = get_outstanding_invoices(
            clinic_id=clinic_id
        )

        return (
            jsonify(
                {
                    "success": True,
                    "data": [
                        _serialize_response(
                            OutstandingInvoiceResponse,
                            invoice,
                        )
                        for invoice in invoices
                    ],
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