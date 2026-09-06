from datetime import timedelta

from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
)

from app.extensions import db
from app.core.utils.decorators import transactional
from app.core.exceptions import ValidationError, ConflictError
from app.core.audit.services.audit_service import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role
from app.core.auth.user.models.user_model import User


def get_user(user_id: int) -> User:
    user = User.query.get(user_id)

    if user is None:
        raise ValidationError(f"User {user_id} not found")

    return user


def get_user_by_email(email: str) -> User | None:
    if not email:
        return None

    return User.query.filter_by(
        email=email.lower().strip()
    ).first()


@transactional
def register_user(
    email: str,
    password: str,
    role: Role,
    clinic_id: int | None = None,
) -> User:

    if not email or "@" not in email:
        raise ValidationError("A valid email is required")

    if not password or len(password) < 8:
        raise ValidationError(
            "Password must be at least 8 characters"
        )

    if not isinstance(role, Role):
        raise ValidationError("Invalid user role")

    email = email.lower().strip()

    if get_user_by_email(email):
        raise ConflictError(
            f"Email '{email}' is already registered"
        )

    user = User(
        email=email,
        role=role,
        clinic_id=clinic_id,
    )

    user.set_password(password)

    db.session.add(user)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="User",
        entity_id=user.id,
        description=(
            f"User registered: {email} ({role.value})"
        ),
    )

    return user


def authenticate_user(email: str, password: str) -> dict:
    email = (email or "").lower().strip()

    if not email or not password:
        raise ValidationError(
            "Email and password are required"
        )

    user = get_user_by_email(email)

    if user is None or not user.check_password(password):
        raise ValidationError(
            "Invalid email or password"
        )

    if not user.is_active:
        raise ValidationError(
            "This account has been deactivated"
        )

    additional_claims = {
        "role": user.role.value,
    }

    # Expiration comes from:
    # JWT_ACCESS_TOKEN_EXPIRES
    access_token = create_access_token(
       identity=str(user.id),
       additional_claims=additional_claims,
    )

    refresh_token = create_refresh_token(
    identity=str(user.id),
    )
    

    user.last_login_at = db.func.now()

    create_audit_log(
        action=AuditAction.LOGIN,
        entity_type="User",
        entity_id=user.id,
        description=f"User '{email}' logged in",
        user_id=user.id,
    )

    db.session.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user_id": user.id,
        "role": user.role.value,
    }