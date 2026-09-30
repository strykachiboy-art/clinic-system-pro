from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IntegrationConfig(db.Model):
    __tablename__ = "integration_configs"

    __table_args__ = (
        db.UniqueConstraint(
            "clinic_id",
            "provider",
            name="uq_integration_config_clinic_provider",
        ),
        db.CheckConstraint(
            "credentials_version >= 1",
            name="ck_integration_config_credentials_version_positive",
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    clinic_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "clinics.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    provider = db.Column(
        db.String(50),
        nullable=False,
        index=True,
    )

    is_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    # Non-sensitive integration configuration.
    #
    # Examples:
    # {
    #     "currency": "NGN",
    #     "environment": "live",
    #     "sender_name": "Clinic System"
    # }
    configuration = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
    )

    # Sensitive credentials encrypted at rest.
    # i didnt store plaintext secrets here.
    encrypted_credentials = db.Column(
        db.Text,
        nullable=True,
    )

    # Increment when credentials are rotated.
    credentials_version = db.Column(
        db.Integer,
        nullable=False,
        default=1,
    )

    # Timestamp of the most recent credential rotation.
    last_rotated_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=_utcnow,
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    clinic = db.relationship(
        "Clinic",
        back_populates="integration_configs",
    )

    def __repr__(self) -> str:
        return (
            f"<IntegrationConfig "
            f"clinic_id={self.clinic_id} "
            f"provider={self.provider!r} "
            f"enabled={self.is_enabled}>"
        )