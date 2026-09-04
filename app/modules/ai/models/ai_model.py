from datetime import datetime, timezone

from app.extensions import db
from app.core.enums.ai_enums import AIFeature


def _utcnow():
    return datetime.now(timezone.utc)


class AILog(db.Model):
    __tablename__ = "ai_logs"

    id = db.Column(db.Integer, primary_key=True)

    clinic_id = db.Column(
        db.Integer,
        db.ForeignKey("clinics.id"),
        nullable=False,
        index=True,
    )

    patient_id = db.Column(
        db.Integer,
        db.ForeignKey("patients.id"),
        nullable=True,
        index=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    feature_used = db.Column(
        db.Enum(AIFeature),
        nullable=False,
        index=True,
    )

    input_data = db.Column(
        db.JSON,
        nullable=True,
    )

    output_data = db.Column(
        db.JSON,
        nullable=True,
    )

    credits_used = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    created_at = db.Column(
        db.DateTime,
        default=_utcnow,
        nullable=False,
        index=True,
    )

    updated_at = db.Column(
        db.DateTime,
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    clinic = db.relationship(
        "Clinic",
        back_populates="ai_logs",
    )

    patient = db.relationship(
        "Patient",
        back_populates="ai_logs",
    )

    user = db.relationship(
        "User",
        back_populates="ai_logs",
    )

    def __repr__(self):
        return (
            f"<AILog id={self.id} "
            f"feature={self.feature_used.value} "
            f"clinic_id={self.clinic_id} "
            f"patient_id={self.patient_id} "
            f"user_id={self.user_id}>"
        )