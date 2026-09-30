from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from app.core.enums.role_enums import Role
from app.core.exceptions import (
    DomainError,
)
from app.core.observability.failure_dashboard_service import (
    get_failure_dashboard,
)
from app.core.utils.decorators import role_required


failure_dashboard_bp = Blueprint(
    "failure_dashboard",
    __name__,
    url_prefix="/operations/failures",
)


@failure_dashboard_bp.get("")
@role_required(
    Role.ADMIN,
    Role.SUPER_ADMIN,
)
def get_failure_dashboard_route():
    try:
        limit = request.args.get(
            "limit",
            default=50,
            type=int,
        )

        result = get_failure_dashboard(
            actor_id=g.current_user_id,
            limit=limit,
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
