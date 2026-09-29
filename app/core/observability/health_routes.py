from __future__ import annotations

from flask import Blueprint, jsonify

from app.core.observability import health


health_bp = Blueprint(
    "health",
    __name__,
    url_prefix="/health",
)


@health_bp.get("/live")
def liveness():
    return jsonify(
        {
            "success": True,
            "status": "ok",
        }
    ), 200


@health_bp.get("/ready")
def readiness():
    result = health.collect_readiness()

    if result["ready"]:
        return jsonify(
            {
                "success": True,
                "status": "ready",
            }
        ), 200

    return jsonify(
        {
            "success": False,
            "status": "not_ready",
        }
    ), 503
