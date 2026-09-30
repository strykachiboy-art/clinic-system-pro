from datetime import datetime, timezone
from app.extensions import db
from app.core.enums.appointment_enums import AppointmentStatus, AppointmentType

def _utcnow():
    return datetime.now(timezone.utc)

class Appointment(db.Model):
    __tablename__ = "appointments"

    id = db.Column(db.Integer, primary_key=True)

    # Relationships
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey("staff.id"), nullable=False)  # doctor/practitioner

    # Scheduling
    scheduled_start = db.Column(db.DateTime, nullable=False)
    scheduled_end = db.Column(db.DateTime, nullable=False)

    status = db.Column(db.Enum(AppointmentStatus), default=AppointmentStatus.SCHEDULED, nullable=False)
    appointment_type = db.Column(db.Enum(AppointmentType), default=AppointmentType.IN_PERSON, nullable=False)

    reason = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    # Integrations
    google_calendar_event_id = db.Column(db.String(255), nullable=True)
    reminder_sent = db.Column(db.Boolean, default=False)

    # Audit
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    cancellation_reason = db.Column(db.String(255), nullable=True)

    # Relationships (back_populates)
    clinic = db.relationship("Clinic", back_populates="appointments")
    patient = db.relationship("Patient", back_populates="appointments")
    staff = db.relationship("Staff", back_populates="appointments")
    consultation = db.relationship("Consultation", back_populates="appointment", uselist=False)

    def __repr__(self):
        return f"<Appointment {self.id} - Patient {self.patient_id} with Staff {self.staff_id}>"