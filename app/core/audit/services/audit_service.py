from typing import Optional
from app.extensions import db
from app.core.audit.models.audit_model import AuditLog
from app.core.enums.audit_enums import AuditAction
from app.core.exceptions import NotFoundError


def create_audit_log(
    *,
    action: AuditAction,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    description: Optional[str] = None,
    old_value=None,
    new_value=None,
    user_id: Optional[int] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    details=None,
) -> AuditLog:
    """Create an audit record using either supported service API shape."""
    resolved_entity_type = entity_type or resource_type
    resolved_entity_id = entity_id if entity_id is not None else resource_id

    if resolved_entity_type is None or resolved_entity_id is None:
        raise ValueError("Audit entity type and entity ID are required")

    log = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=resolved_entity_type,
        entity_id=resolved_entity_id,
        description=description,
        old_value=old_value,
        new_value=new_value if new_value is not None else details,
    )
    db.session.add(log)
    return log


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
    log = db.session.get(AuditLog, log_id)

    if not log:
        raise NotFoundError(
            f"Audit log {log_id} not found"
        )

    return log