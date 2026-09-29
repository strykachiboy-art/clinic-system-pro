from functools import wraps

from flask import g, jsonify
from flask_jwt_extended import (
    get_jwt_identity,
    verify_jwt_in_request,
)

from app.core.auth.user.models.user_model import User
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
    if getattr(
        g,
        "_auth_context_loaded",
        False,
    ):
        return

    verify_jwt_in_request()

    identity = get_jwt_identity()

    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        g.current_user_id = None
        g.current_user = None
        g.current_user_role = None
        g._auth_context_loaded = True
        return

    user = db.session.get(
        User,
        user_id,
    )

    if user is None or not user.is_active:
        g.current_user_id = None
        g.current_user = None
        g.current_user_role = None
        g._auth_context_loaded = True
        return

    g.current_user_id = user.id
    g.current_user = user
    g.current_user_role = user.role

    g._auth_context_loaded = True


def login_required(fn):

    @wraps(fn)
    def wrapper(*args, **kwargs):
        _load_auth_context()

        if g.current_user_id is None:
            return jsonify({
                "error": "Invalid authentication identity"
            }), 401

        return fn(*args, **kwargs)

    return wrapper


def role_required(*required_roles):
    allowed_roles = {
        role
        if isinstance(role, Role)
        else Role(str(role))
        for role in required_roles
    }

    def decorator(fn):

        @wraps(fn)
        def wrapper(*args, **kwargs):
            _load_auth_context()

            if g.current_user_id is None:
                return jsonify({
                    "error": "Invalid authentication identity"
                }), 401

            if g.current_user_role not in allowed_roles:
                return jsonify({
                    "error": "Insufficient permissions"
                }), 403

            return fn(*args, **kwargs)

        return wrapper

    return decorator


def require_roles(*allowed_roles):
    return role_required(*allowed_roles)