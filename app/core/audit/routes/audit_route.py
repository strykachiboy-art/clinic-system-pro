from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.core.audit.schema.audit_request import AuditLogResponseSchema
from app.core.audit.services.audit_service import (
    get_audit_log_by_id,
    list_audit_logs,
)
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role
from app.core.exceptions import ValidationError
from app.core.utils.decorators import role_required


audit_bp = Blueprint(
    "audit",
    __name__,
    url_prefix="/api/audit-logs",
)


def _get_int_query_param(
    name: str,
    *,
    default: int | None = None,
) -> int | None:
    """
    Parse an integer query parameter without silently converting malformed
    values to None.

    Example:
        ?page=2     -> 2
        ?page=abc   -> ValidationError
        missing     -> default
    """

    raw_value = request.args.get(name)

    if raw_value is None:
        return default

    raw_value = raw_value.strip()

    if not raw_value:
        raise ValidationError(
            f"{name} must be an integer"
        )

    try:
        return int(raw_value)
    except (TypeError, ValueError):
        raise ValidationError(
            f"{name} must be an integer"
        )


@audit_bp.get("")
@role_required(Role.ADMIN)
def get_audit_logs():
    user_id = _get_int_query_param("user_id")
    entity_id = _get_int_query_param("entity_id")

    page = _get_int_query_param(
        "page",
        default=1,
    )

    per_page = _get_int_query_param(
        "per_page",
        default=20,
    )

    action_value = request.args.get("action")

    action = None

    if action_value is not None:
        action_value = action_value.strip()

        if not action_value:
            raise ValidationError(
                "Action cannot be empty"
            )

        try:
            action = AuditAction(action_value)
        except ValueError:
            raise ValidationError(
                "Invalid audit action"
            )

    entity_type = request.args.get(
        "entity_type"
    )

    pagination = list_audit_logs(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        page=page,
        per_page=per_page,
    )

    response_data = [
        AuditLogResponseSchema.model_validate(log).model_dump(
            mode="json"
        )
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

    result = (
        AuditLogResponseSchema
        .model_validate(log)
        .model_dump(mode="json")
    )

    return jsonify(
        {
            "success": True,
            "data": result,
        }
    ), 200