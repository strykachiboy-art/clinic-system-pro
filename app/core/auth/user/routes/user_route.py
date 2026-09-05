from flask import Blueprint, jsonify, request

from app.core.auth.user.services.user_service import authenticate_user, register_user
from app.core.enums.role_enums import Role


auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/api/auth",
)


@auth_bp.post("/register")
def register():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip()
    password = payload.get("password")
    role_value = payload.get("role")
    clinic_id = payload.get("clinic_id")

    if not email or not password:
        return jsonify({"success": False, "error": "Email and password are required"}), 400

    if role_value is None:
        return jsonify({"success": False, "error": "Role is required"}), 400

    try:
        role = Role(role_value)
    except ValueError:
        return jsonify({"success": False, "error": "Invalid role value"}), 400

    user = register_user(email=email, password=password, role=role, clinic_id=clinic_id)

    return jsonify(
        {
            "success": True,
            "data": {
                "id": user.id,
                "email": user.email,
                "role": user.role.value,
                "clinic_id": user.clinic_id,
                "created_at": user.created_at.isoformat() if user.created_at else None,
            },
        }
    ), 201


@auth_bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip()
    password = payload.get("password")

    if not email or not password:
        return jsonify({"success": False, "error": "Email and password are required"}), 400

    result = authenticate_user(email=email, password=password)

    return jsonify({"success": True, "data": result}), 200
