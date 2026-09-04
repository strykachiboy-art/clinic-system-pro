from typing import Optional

from app.core.audit.models.audit_model import AuditLog
from app.core.enums.audit_enums import AuditAction
from app.core.exceptions import NotFoundError


def list_audit_logs(
    *,
    user_id: Optional[int] = None,
    action: Optional[AuditAction] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    page: int = 1,
    per_page: int = 20,
):
    query = AuditLog.query

    if user_id is not None:
        query = query.filter(
            AuditLog.user_id == user_id
        )

    if action is not None:
        query = query.filter(
            AuditLog.action == action
        )

    if entity_type:
        query = query.filter(
            AuditLog.entity_type == entity_type
        )

    if entity_id is not None:
        query = query.filter(
            AuditLog.entity_id == entity_id
        )

    return (
        query
        .order_by(AuditLog.created_at.desc())
        .paginate(
            page=page,
            per_page=per_page,
            error_out=False,
        )
    )


def get_audit_log_by_id(log_id: int) -> AuditLog:
    log = AuditLog.query.get(log_id)

    if not log:
        raise NotFoundError(
            f"Audit log {log_id} not found"
        )

    return log