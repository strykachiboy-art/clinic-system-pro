from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity
from pydantic import ValidationError as PydanticValidationError

from app.extensions import db
from app.core.exceptions import DomainError, ValidationError
from app.core.auth.user.models.user_model import User
from app.core.enums.role_enums import Role
from app.core.exceptions import DomainError
from app.core.utils.decorators import role_required
from app.extensions import db

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

    user = db.session.get(User, user_id)

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
    Return the clinic belonging to the authenticated user.

    The clinic is derived from the authenticated database User and is
    never trusted from request JSON or query parameters.
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
    user = _get_current_user()

    staff = user.staff

    if staff is None:
        raise DomainError(
            "Authenticated user is not linked to a staff record"
        )

    return staff


def _get_current_staff_id() -> int:
    return _get_current_staff().id


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------


def _handle_route_error(
    exc: Exception,
):
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
    return (
        jsonify(
            {
                "success": False,
                "error": "Validation failed",
                "details": exc.errors(),
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
    return GeneratedReportResponseSchema.model_validate(
        report
    ).model_dump(
        mode="json"
    )


def _serialize_report_list(
    result: dict,
) -> dict:
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
    try:
        # Confirm the actual authenticated database user is active.
        user = _get_current_user()

        # Clinic ownership comes from authentication, never from the
        # request body.
        current_clinic_id = _get_current_clinic_id()

        payload = ReportGenerateSchema.model_validate(
            request.get_json(
                silent=True
            )
            or {}
        )

        requester_user_id = int(
            get_jwt_identity()
        )

        report = generate_report(
            report_type=payload.report_type,
            report_format=payload.report_format,
            clinic_id=current_clinic_id,
            requester_user_id=requester_user_id,
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
    try:
        # Authentication establishes the clinic scope.
        _get_current_user()
        current_clinic_id = _get_current_clinic_id()

        requester_user_id = int(
            get_jwt_identity()
        )

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
    try:
        # Authentication is still explicitly verified here.
        _get_current_user()

        requester_user_id = int(
            get_jwt_identity()
        )

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