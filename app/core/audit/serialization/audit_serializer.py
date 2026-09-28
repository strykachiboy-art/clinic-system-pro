from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.core.audit.models.audit_model import AuditLog
from app.core.audit.schema.audit_response import AuditLogResponseSchema
from app.core.audit.services.audit_redaction import redact_audit_payload


def serialize_audit_log(
    audit_log: AuditLog,
) -> dict[str, Any]:
    if not isinstance(audit_log, AuditLog):
        raise TypeError("audit_log must be an AuditLog")

    result = (
        AuditLogResponseSchema
        .model_validate(audit_log)
        .model_dump(mode="json")
    )

    result["old_value"] = redact_audit_payload(
        result["old_value"]
    )
    result["new_value"] = redact_audit_payload(
        result["new_value"]
    )

    return result


def serialize_audit_logs(
    audit_logs: Iterable[AuditLog],
) -> list[dict[str, Any]]:
    return [
        serialize_audit_log(audit_log)
        for audit_log in audit_logs
    ]


def serialize_audit_page(
    pagination,
) -> dict[str, Any]:
    return {
        "items": serialize_audit_logs(
            pagination.items
        ),
        "total": pagination.total,
        "page": pagination.page,
        "per_page": pagination.per_page,
        "pages": pagination.pages,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev,
    }