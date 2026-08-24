from app.extensions import db
from app.core.audit.models.audit_model import AuditLog
from app.core.enums.audit_enums import AuditAction
from flask import request, g, has_request_context


def create_audit_log(action: AuditAction, entity_type: str, entity_id: int, description: str = None, old_value: dict = None, new_value: dict = None):

    user_id = None
    ip_address = None

    if has_request_context():
        user_id = getattr(g, "current_user_id", None)
        ip_address = request.remote_addr

    log = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address,
    )
    db.session.add(log)
    return log