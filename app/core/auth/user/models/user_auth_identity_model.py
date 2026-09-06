from datetime import datetime, timezone

from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class UserAuthIdentity(db.Model):
    __tablename__ = "user_auth_identities"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    provider = db.Column(
        db.String(50),
        nullable=False,
    )

    provider_user_id = db.Column(
        db.String(255),
        nullable=False,
    )

    created_at = db.Column(
        db.DateTime,
        default=_utcnow,
        nullable=False,
    )

    updated_at = db.Column(
        db.DateTime,
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    user = db.relationship(
        "User",
        back_populates="auth_identities",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "provider",
            "provider_user_id",
            name="uq_user_auth_identity_provider_user",
        ),
        db.UniqueConstraint(
            "user_id",
            "provider",
            name="uq_user_auth_identity_user_provider",
        ),
    )

    def __repr__(self):
        return (
            f"<UserAuthIdentity "
            f"{self.provider}:{self.provider_user_id}>"
        )