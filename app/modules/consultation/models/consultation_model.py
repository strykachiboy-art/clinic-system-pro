from datetime import datetime, timezone
from app.extensions import db
from app.core.enums.consultation_enums import ConsultationStatus, ConsultationType

def _utcnow():
    return datetime.now(timezone.utc)

class Consultation(db.Model):
    __tablename__ = "consultations"

    id = db.Column(db.Integer, primary_key=True)

    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey("staff.id"), nullable=False)
    appointment_id = db.Column(db.Integer, db.ForeignKey("appointments.id"), nullable=True)

    consultation_type = db.Column(db.Enum(ConsultationType), default=ConsultationType.GENERAL, nullable=False)
    status = db.Column(db.Enum(ConsultationStatus), default=ConsultationStatus.IN_PROGRESS, nullable=False)

    chief_complaint = db.Column(db.Text, nullable=True)
    symptoms = db.Column(db.Text, nullable=True)
    diagnosis = db.Column(db.Text, nullable=True)
    treatment_plan = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    voice_note_url = db.Column(db.String(255), nullable=True)
    transcribed_text = db.Column(db.Text, nullable=True)

    template_id = db.Column(db.Integer, db.ForeignKey("consultation_templates.id"), nullable=True)

    started_at = db.Column(db.DateTime, default=_utcnow)
    ended_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    clinic = db.relationship("Clinic", back_populates="consultations")
    patient = db.relationship("Patient", back_populates="consultations")
    staff = db.relationship("Staff", back_populates="consultations")
    appointment = db.relationship("Appointment", back_populates="consultation")
    template = db.relationship("ConsultationTemplate", back_populates="consultations")

    prescriptions = db.relationship("Prescription", back_populates="consultation")
    lab_orders = db.relationship("LabOrder", back_populates="consultation")

    def __repr__(self):
        return f"<Consultation {self.id} - Patient {self.patient_id} ({self.status.value})>"


class ConsultationTemplate(db.Model):
    __tablename__ = "consultation_templates"

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=True)

    name = db.Column(db.String(150), nullable=False)
    specialty = db.Column(db.String(100), nullable=True)
    structure = db.Column(db.JSON, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    consultations = db.relationship("Consultation", back_populates="template")

    def __repr__(self):
        return f"<ConsultationTemplate {self.name}>"