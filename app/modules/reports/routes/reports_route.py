from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.core.enums.role_enums import Role
from app.core.utils.decorators import role_required

from app.modules.reports.schemas.reports_schema import (
    GeneratedReportResponseSchema,
    ReportGenerateSchema,
    ReportQuerySchema,
)
from app.modules.reports.services.reports_service import (
    generate_report,
    get_report,
    list_reports,
)


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


def _serialize_report(report):
    return GeneratedReportResponseSchema.model_validate(
        report
    ).model_dump(mode="json")


@reports_bp.post("")
@role_required(*REPORT_GENERATION_ROLES)
def create_report():
    payload = ReportGenerateSchema.model_validate(
        request.get_json(silent=True) or {}
    )

    requester_user_id = int(
        get_jwt_identity()
    )

    report = generate_report(
        report_type=payload.report_type,
        report_format=payload.report_format,
        clinic_id=payload.clinic_id,
        requester_user_id=requester_user_id,
        filters=(
            payload.filters.model_dump(
                mode="json"
            )
            if payload.filters is not None
            else None
        ),
    )

    return jsonify(
        {
            "success": True,
            "message": "Report generated successfully",
            "data": _serialize_report(report),
        }
    ), 201


@reports_bp.get("")
@role_required(*REPORT_VIEW_ROLES)
def get_reports():
    requester_user_id = int(
        get_jwt_identity()
    )

    query_payload = {
        "clinic_id": request.args.get("clinic_id"),
        "report_type": request.args.get("report_type"),
        "report_format": request.args.get("report_format"),
        "date_from": request.args.get("date_from"),
        "date_to": request.args.get("date_to"),
        "generated_by_id": request.args.get("generated_by_id"),
        "page": request.args.get("page", 1),
        "per_page": request.args.get("per_page", 20),
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
        clinic_id=payload.clinic_id,
        generated_by_id=payload.generated_by_id,
        report_type=payload.report_type,
        report_format=payload.report_format,
        date_from=payload.date_from,
        date_to=payload.date_to,
        page=payload.page,
        per_page=payload.per_page,
    )

    return jsonify(
        {
            "success": True,
            "data": {
                "items": [
                    _serialize_report(report)
                    for report in result["items"]
                ],
                "total": result["total"],
                "page": result["page"],
                "per_page": result["per_page"],
            },
        }
    ), 200


@reports_bp.get("/<int:report_id>")
@role_required(*REPORT_VIEW_ROLES)
def get_single_report(report_id: int):
    requester_user_id = int(
        get_jwt_identity()
    )

    report = get_report(
        report_id=report_id,
        requester_user_id=requester_user_id,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize_report(report),
        }
    ), 200