from datetime import datetime, timezone
from app.extensions import db
from app.core.enums.ai_enums import AIFeature


def _utcnow():
    return datetime.now(timezone.utc)


class AILog(db.Model):
    __tablename__ = "ai_logs"

    id = db.Column(db.Integer, primary_key=True)

    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=True)
    user_id = db.Column(db.Integer, nullable=True)

    feature_used = db.Column(db.Enum(AIFeature), nullable=False)

    input_data = db.Column(db.JSON, nullable=True)
    output_data = db.Column(db.JSON, nullable=True)

    credits_used = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, default=_utcnow)

    clinic = db.relationship("Clinic", back_populates="ai_logs")
    patient = db.relationship("Patient", back_populates="ai_logs")