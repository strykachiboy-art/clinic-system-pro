from functools import wraps
from flask import jsonify
from flask_jwt_extended import get_jwt, jwt_required

from app.extensions import db
from app.core.enums.role_enums import Role


def transactional(fn):
    """
    Run a service function as a single DB transaction.
    Commits on success, rolls back on any exception, then re-raises.
    """
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


def role_required(*required_roles):
    """Require a valid JWT containing one of the supplied roles."""
    allowed_roles = {
        role.value if isinstance(role, Role) else str(role)
        for role in required_roles
    }

    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            current_role = claims.get("role")
            if current_role not in allowed_roles:
                return jsonify({"error": "Insufficient permissions"}), 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator



from functools import wraps
from flask import g, jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt
from app.core.enums.role_enums import Role


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        g.current_user_id = int(get_jwt_identity())
        return fn(*args, **kwargs)
    return wrapper


def require_roles(*allowed_roles: Role):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            user_role = claims.get("role")
            if user_role not in [r.value for r in allowed_roles]:
                return jsonify({"error": "Insufficient permissions"}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator