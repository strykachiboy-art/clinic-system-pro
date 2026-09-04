from datetime import timedelta
from flask_jwt_extended import create_access_token, create_refresh_token
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
    return User.query.filter_by(email=email.lower().strip()).first()


@transactional
def register_user(email: str, password: str, role: Role, clinic_id: int | None = None) -> User:
    if not email or "@" not in email:
        raise ValidationError("A valid email is required")
    if not password or len(password) < 8:
        raise ValidationError("Password must be at least 8 characters")

    email = email.lower().strip()
    if get_user_by_email(email):
        raise ConflictError(f"Email '{email}' is already registered")

    user = User(email=email, role=role, clinic_id=clinic_id)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()

    # NOTE: no create_audit_log user_id here — this route runs before
    # any login exists, so there's no g.current_user_id to attribute
    # to.
    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="User",
        entity_id=user.id,
        description=f"User registered: {email} ({role.value})",
    )
    return user


def authenticate_user(email: str, password: str) -> dict:

    user = get_user_by_email(email)
    if user is None or not user.check_password(password):
        raise ValidationError("Invalid email or password")
    if not user.is_active:
        raise ValidationError("This account has been deactivated")

    # Role embedded as a JWT claim — read by require_roles() on every
    # protected route without a DB lookup per request.
    additional_claims = {"role": user.role.value}
    access_token = create_access_token(
        identity=str(user.id), additional_claims=additional_claims, expires_delta=timedelta(hours=8)
    )
    refresh_token = create_refresh_token(identity=str(user.id), expires_delta=timedelta(days=30))

    user.last_login_at = db.func.now()
    db.session.commit()

    create_audit_log(
        action=AuditAction.LOGIN,
        entity_type="User",
        entity_id=user.id,
        description=f"User '{email}' logged in",
    )
    db.session.commit()  # commits the LOGIN audit log too (user.last_login_at already committed above)

    return {"access_token": access_token, "refresh_token": refresh_token, "user_id": user.id, "role": user.role.value}