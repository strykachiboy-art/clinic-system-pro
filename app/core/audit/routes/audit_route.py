from flask import Blueprint, jsonify, request
from app.extensions import db
from app.core.audit.models.audit_model import AuditLog
from app.core.audit.schema.audit_request import AuditLogResponseSchema
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role
from app.core.utils.decorators import role_required

audit_bp = Blueprint("audit", __name__, url_prefix="/api/audit-logs")


@audit_bp.route("", methods=["GET"])
@role_required(Role.ADMIN)
def get_audit_logs():
    user_id = request.args.get("user_id", type=int)
    action_str = request.args.get("action", type=str)
    entity_type = request.args.get("entity_type", type=str)
    entity_id = request.args.get("entity_id", type=int)
    
    query = AuditLog.query

    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    if action_str:
        try:
            action_enum = AuditAction(action_str)
            query = query.filter_by(action=action_enum)
        except ValueError:
            return jsonify({"error": f"Invalid action value: {action_str}"}), 400
    if entity_type:
        query = query.filter_by(entity_type=entity_type)
    if entity_id is not None:
        query = query.filter_by(entity_id=entity_id)

    logs = query.order_by(AuditLog.created_at.desc()).all()

    response_data = [AuditLogResponseSchema.model_validate(log).model_dump(mode='json') for log in logs]

    return jsonify({
        "success": True,
        "count": len(response_data),
        "data": response_data
    }), 200


@audit_bp.route("/<int:log_id>", methods=["GET"])
@role_required(Role.ADMIN)
def get_audit_log_by_id(log_id: int):
    log = db.session.get(AuditLog, log_id)
    if not log:
        return jsonify({"error": "Audit log not found"}), 404

    result = AuditLogResponseSchema.model_validate(log).model_dump(mode='json')
    return jsonify({
        "success": True,
        "data": result
    }), 200