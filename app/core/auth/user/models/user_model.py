from datetime import datetime, timezone

from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db
from app.core.enums.role_enums import Role


def _utcnow():
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    email = db.Column(
        db.String(120),
        unique=True,
        nullable=False,
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False,
    )

    role = db.Column(
        db.Enum(Role),
        nullable=False,
    )

    is_active = db.Column(
        db.Boolean,
        default=True,
        nullable=False,
    )

    clinic_id = db.Column(
        db.Integer,
        db.ForeignKey("clinics.id"),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        default=_utcnow,
    )

    updated_at = db.Column(
        db.DateTime,
        default=_utcnow,
        onupdate=_utcnow,
    )

    last_login_at = db.Column(
        db.DateTime,
        nullable=True,
    )
    
    ai_logs = db.relationship(
       "AILog",
       back_populates="user",
    )

    audit_logs = db.relationship(
        "AuditLog",
        back_populates="user",
    )

    staff = db.relationship(
        "Staff",
        back_populates="user",
        uselist=False,
    )

    def set_password(self, raw_password: str):
        self.password_hash = generate_password_hash(
            raw_password
        )

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(
            self.password_hash,
            raw_password,
        )

    def __repr__(self):
        return (
            f"<User {self.email} "
            f"({self.role.value})>"
        )