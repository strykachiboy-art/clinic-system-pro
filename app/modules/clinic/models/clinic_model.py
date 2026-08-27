from datetime import datetime, timezone
from app.extensions import db
from app.core.enums.clinic_enums import ClinicStatus, ClinicType

def _utcnow():
    return datetime.now(timezone.utc)

class Clinic(db.Model):
    __tablename__ = "clinics"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(150), nullable=False)
    clinic_type = db.Column(db.Enum(ClinicType), default=ClinicType.GENERAL, nullable=False)
    status = db.Column(db.Enum(ClinicStatus), default=ClinicStatus.ACTIVE, nullable=False)

    # Multi-branch support
    parent_clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=True)
    is_headquarters = db.Column(db.Boolean, default=False)

    # Contact / location
    address = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    country = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)

    # Operating info
    timezone = db.Column(db.String(50), default="UTC")
    opening_time = db.Column(db.Time, nullable=True)
    closing_time = db.Column(db.Time, nullable=True)

    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    # AI feature cache/metering — see app/modules/ai
    ai_credits = db.Column(db.Integer, nullable=False, default=0)
    api_token = db.Column(db.String(255), nullable=True)
    ai_requests_this_month = db.Column(db.Integer, nullable=False, default=0)

    # Relationships
    branches = db.relationship("Clinic", backref=db.backref("parent_clinic", remote_side=[id]))

    appointments = db.relationship("Appointment", back_populates="clinic")
    invoices = db.relationship("Invoice", back_populates="clinic")
    patients = db.relationship("Patient", back_populates="clinic")
    staff = db.relationship("Staff", back_populates="clinic")
    ai_logs = db.relationship("AILog", back_populates="clinic")
    wards = db.relationship("Ward", back_populates="clinic")
    lab_orders = db.relationship("LabOrder", back_populates="clinic")
    prescriptions = db.relationship("Prescription", back_populates="clinic")
    inventory_items = db.relationship("InventoryItem", back_populates="clinic")
    consultations = db.relationship("Consultation", back_populates="clinic")
    generated_reports = db.relationship("GeneratedReport", back_populates="clinic")

    def __repr__(self):
        return f"<Clinic {self.name} ({self.status.value})>"