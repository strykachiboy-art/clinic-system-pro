from functools import wraps

from flask import g, jsonify
from flask_jwt_extended import (
    get_jwt,
    get_jwt_identity,
    verify_jwt_in_request,
)

from app.core.enums.role_enums import Role
from app.extensions import db


def transactional(fn):

    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            result = fn(*args, **kwargs)
            db.session.commit()
            return result
        except Exception:
            db.session.rollback()
            raise

    return wrapper


def _load_auth_context():
    """
    Verify the JWT and load the authenticated user's identity and role
    into Flask's request-local `g` object.

    This function is shared by the authentication decorators so that
    `login_required` and `role_required` use the same authentication flow.
    """

    if getattr(g, "_auth_context_loaded", False):
        return

    verify_jwt_in_request()

    identity = get_jwt_identity()
    claims = get_jwt()

    try:
        g.current_user_id = int(identity)
    except (TypeError, ValueError):
        # Invalid JWT identity.
        g.current_user_id = None

    g.current_user_role = claims.get("role")
    g._auth_context_loaded = True


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        _load_auth_context()

        if g.current_user_id is None:
            return jsonify({"error": "Invalid authentication identity"}), 401

        return fn(*args, **kwargs)

    return wrapper


def role_required(*required_roles):
    allowed_roles = {
        role.value if isinstance(role, Role) else str(role)
        for role in required_roles
    }

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            _load_auth_context()

            if g.current_user_id is None:
                return jsonify({"error": "Invalid authentication identity"}), 401

            if g.current_user_role not in allowed_roles:
                return jsonify({"error": "Insufficient permissions"}), 403

            return fn(*args, **kwargs)

        return wrapper

    return decorator


def require_roles(*allowed_roles):

    return role_required(*allowed_roles)