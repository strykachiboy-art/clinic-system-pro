from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity
from pydantic import ValidationError as PydanticValidationError

from app.extensions import db

from app.core.auth.user.models.user_model import User
from app.core.enums.role_enums import Role
from app.core.exceptions import DomainError, ValidationError
from app.core.utils.decorators import role_required

from app.modules.reports.schemas.reports_schema import (
    GeneratedReportListResponseSchema,
    GeneratedReportResponseSchema,
    ReportGenerateSchema,
    ReportQuerySchema,
)
from app.modules.reports.services.reports_service import (
    generate_report,
    get_report,
    list_reports,
)
from app.modules.staff.models.staff_model import Staff


reports_bp = Blueprint(
    "reports",
    __name__,
    url_prefix="/api/reports",
)


REPORT_GENERATION_ROLES = (
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
    Role.RECEPTIONIST,
    Role.ACCOUNTANT,
    Role.PHARMACIST,
    Role.LAB_TECHNICIAN,
)


REPORT_VIEW_ROLES = (
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
    Role.RECEPTIONIST,
    Role.ACCOUNTANT,
    Role.PHARMACIST,
    Role.LAB_TECHNICIAN,
)


# ---------------------------------------------------------------------------
# Authentication helpers
# ---------------------------------------------------------------------------


def _get_current_user() -> User:
    """
    Return the authenticated active database user.
    """
    identity = get_jwt_identity()

    try:
        user_id = int(identity)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Invalid authentication identity"
        ) from exc

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
    """
    Return the clinic assigned to the authenticated user.

    Clinic scope is derived exclusively from the authenticated
    database user and is never trusted from request input.
    """
    user = _get_current_user()

    clinic_id = getattr(
        user,
        "clinic_id",
        None,
    )

    if clinic_id is None:
        raise DomainError(
            "Authenticated user is not assigned to a clinic"
        )

    if isinstance(clinic_id, bool):
        raise DomainError(
            "Authenticated user has an invalid clinic assignment"
        )

    try:
        clinic_id = int(clinic_id)
    except (TypeError, ValueError) as exc:
        raise DomainError(
            "Authenticated user has an invalid clinic assignment"
        ) from exc

    if clinic_id <= 0:
        raise DomainError(
            "Authenticated user has an invalid clinic assignment"
        )

    return clinic_id


def _get_current_staff() -> Staff:
    """
    Return the staff record linked to the authenticated user.
    """
    user = _get_current_user()

    staff = getattr(
        user,
        "staff",
        None,
    )

    if staff is None:
        raise DomainError(
            "Authenticated user is not linked to a staff record"
        )

    return staff


def _get_current_staff_id() -> int:
    """
    Return the authenticated staff ID.
    """
    return _get_current_staff().id


def _get_current_user_id() -> int:
    """
    Return the authenticated user ID.

    The value is resolved from the JWT identity only after the
    authenticated database user has been validated.
    """
    identity = get_jwt_identity()

    try:
        user_id = int(identity)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Invalid authentication identity"
        ) from exc

    if user_id <= 0:
        raise ValidationError(
            "Invalid authentication identity"
        )

    return user_id


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------


def _handle_route_error(
    exc: Exception,
):
    """
    Convert domain exceptions into their declared HTTP response.

    Unexpected exceptions intentionally receive a generic response so
    internal implementation details are not leaked to API clients.
    """
    if isinstance(exc, DomainError):
        return (
            jsonify(
                {
                    "success": False,
                    "error": str(exc),
                }
            ),
            exc.status_code,
        )

    return (
        jsonify(
            {
                "success": False,
                "error": "An unexpected error occurred",
            }
        ),
        400,
    )


def _validation_error_response(
    exc: PydanticValidationError,
):
    """
    Return a JSON-safe Pydantic validation response.

    Pydantic v2 may place the original ValueError object inside
    error["ctx"]["error"]. Flask's JSON encoder cannot serialize that
    exception object directly, so normalize it to a string first.
    """
    details = []

    for error in exc.errors():
        item = dict(error)

        ctx = item.get("ctx")

        if isinstance(ctx, dict) and "error" in ctx:
            ctx = dict(ctx)
            ctx["error"] = str(ctx["error"])
            item["ctx"] = ctx

        details.append(item)

    return (
        jsonify(
            {
                "success": False,
                "error": "Validation failed",
                "details": details,
            }
        ),
        422,
    )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _serialize_report(
    report,
) -> dict:
    """
    Serialize a GeneratedReport ORM instance through the response schema.
    """
    return GeneratedReportResponseSchema.model_validate(
        report
    ).model_dump(
        mode="json"
    )


def _serialize_report_list(
    result: dict,
) -> dict:
    """
    Serialize a paginated report result through the response schema.
    """
    payload = GeneratedReportListResponseSchema.model_validate(
        result
    )

    return payload.model_dump(
        mode="json"
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@reports_bp.post("")
@role_required(*REPORT_GENERATION_ROLES)
def create_report():
    """
    Generate a report for the authenticated user's clinic.
    """
    try:
        # Resolve and validate the actual authenticated database user.
        _get_current_user()

        # Clinic scope is always derived from authentication.
        current_clinic_id = _get_current_clinic_id()

        payload = ReportGenerateSchema.model_validate(
            request.get_json(
                silent=True
            )
            or {}
        )

        requester_user_id = _get_current_user_id()

        report = generate_report(
            requester_user_id=requester_user_id,
            clinic_id=current_clinic_id,
            report_type=payload.report_type,
            report_format=payload.report_format,
            filters=(
                payload.filters.model_dump(
                    mode="json"
                )
                if payload.filters is not None
                else None
            ),
        )

        return (
            jsonify(
                {
                    "success": True,
                    "message": "Report generated successfully",
                    "data": _serialize_report(
                        report
                    ),
                }
            ),
            201,
        )

    except PydanticValidationError as exc:
        return _validation_error_response(
            exc
        )

    except Exception as exc:
        return _handle_route_error(
            exc
        )


@reports_bp.get("")
@role_required(*REPORT_VIEW_ROLES)
def get_reports():
    """
    Return paginated reports visible to the authenticated user.
    """
    try:
        # Resolve and validate the authenticated user first.
        _get_current_user()

        # Clinic scope is derived from authentication.
        current_clinic_id = _get_current_clinic_id()

        requester_user_id = _get_current_user_id()

        query_payload = {
            "report_type": request.args.get(
                "report_type"
            ),
            "report_format": request.args.get(
                "report_format"
            ),
            "date_from": request.args.get(
                "date_from"
            ),
            "date_to": request.args.get(
                "date_to"
            ),
            "generated_by_id": request.args.get(
                "generated_by_id"
            ),
            "page": request.args.get(
                "page",
                1,
            ),
            "per_page": request.args.get(
                "per_page",
                20,
            ),
        }

        # Remove omitted optional query parameters while preserving
        # pagination defaults.
        query_payload = {
            key: value
            for key, value in query_payload.items()
            if value is not None
        }

        payload = ReportQuerySchema.model_validate(
            query_payload
        )

        result = list_reports(
            requester_user_id=requester_user_id,
            clinic_id=current_clinic_id,
            generated_by_id=payload.generated_by_id,
            report_type=payload.report_type,
            report_format=payload.report_format,
            date_from=payload.date_from,
            date_to=payload.date_to,
            page=payload.page,
            per_page=payload.per_page,
        )

        return (
            jsonify(
                {
                    "success": True,
                    "data": _serialize_report_list(
                        result
                    ),
                }
            ),
            200,
        )

    except PydanticValidationError as exc:
        return _validation_error_response(
            exc
        )

    except Exception as exc:
        return _handle_route_error(
            exc
        )


@reports_bp.get("/<int:report_id>")
@role_required(*REPORT_VIEW_ROLES)
def get_single_report(
    report_id: int,
):
    """
    Return one report after service-layer authorization checks.
    """
    try:
        _get_current_user()

        requester_user_id = _get_current_user_id()

        report = get_report(
            report_id=report_id,
            requester_user_id=requester_user_id,
        )

        return (
            jsonify(
                {
                    "success": True,
                    "data": _serialize_report(
                        report
                    ),
                }
            ),
            200,
        )

    except PydanticValidationError as exc:
        return _validation_error_response(
            exc
        )

    except Exception as exc:
        return _handle_route_error(
            exc
        )