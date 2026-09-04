from flask import Blueprint, jsonify, request

from app.core.audit.schema.audit_request import AuditLogResponseSchema
from app.core.audit.services.audit_service import (
    get_audit_log_by_id,
    list_audit_logs,
)
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role
from app.core.utils.decorators import role_required


audit_bp = Blueprint(
    "audit",
    __name__,
    url_prefix="/api/audit-logs",
)


@audit_bp.get("")
@role_required(Role.ADMIN)
def get_audit_logs():
    user_id = request.args.get("user_id", type=int)
    action_value = request.args.get("action")
    entity_type = request.args.get("entity_type")
    entity_id = request.args.get("entity_id", type=int)

    page = request.args.get("page", default=1, type=int)
    per_page = request.args.get("per_page", default=20, type=int)

    action = None

    if action_value:
        action = AuditAction(action_value)

    pagination = list_audit_logs(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        page=page,
        per_page=per_page,
    )

    response_data = [
        AuditLogResponseSchema.model_validate(log).model_dump(mode="json")
        for log in pagination.items
    ]

    return jsonify(
        {
            "success": True,
            "data": {
                "items": response_data,
                "total": pagination.total,
                "page": pagination.page,
                "per_page": pagination.per_page,
                "pages": pagination.pages,
            },
        }
    ), 200


@audit_bp.get("/<int:log_id>")
@role_required(Role.ADMIN)
def get_audit_log(log_id: int):
    log = get_audit_log_by_id(log_id)

    result = AuditLogResponseSchema.model_validate(log).model_dump(
        mode="json"
    )

    return jsonify(
        {
            "success": True,
            "data": result,
        }
    ), 200