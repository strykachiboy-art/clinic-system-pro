from __future__ import annotations

from flask import Blueprint, g, jsonify

from app.core.enums.role_enums import Role
from app.core.exceptions import DomainError
from app.core.observability.operations_dashboard_service import (
    get_operational_dashboard,
)
from app.core.utils.decorators import role_required


operations_bp = Blueprint(
    "operations",
    __name__,
    url_prefix="/operations",
)


@operations_bp.get("")
@role_required(
    Role.ADMIN,
    Role.SUPER_ADMIN,
)
def get_operations_dashboard_route():
    try:
        result = get_operational_dashboard(
            actor_id=g.current_user_id,
        )

        return (
            jsonify(
                {
                    "success": True,
                    "data": result,
                }
            ),
            200,
        )

    except DomainError as exc:
        return (
            jsonify(
                {
                    "success": False,
                    "error": str(exc),
                }
            ),
            exc.status_code,
        )
