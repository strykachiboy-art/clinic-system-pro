from datetime import datetime, timezone
from app.extensions import db
from app.core.enums.ward_enums import BedStatus, AdmissionStatus, WardType

def _utcnow():
    return datetime.now(timezone.utc)

class Ward(db.Model):
    __tablename__ = "wards"

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=False)

    name = db.Column(db.String(150), nullable=False)          # e.g. "Ward A", "ICU 1"
    ward_type = db.Column(db.Enum(WardType), default=WardType.GENERAL, nullable=False)
    capacity = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=_utcnow)

    clinic = db.relationship("Clinic", back_populates="wards")
    beds = db.relationship("Bed", back_populates="ward", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Ward {self.name} ({self.ward_type.value})>"


class Bed(db.Model):
    __tablename__ = "beds"

    id = db.Column(db.Integer, primary_key=True)
    ward_id = db.Column(db.Integer, db.ForeignKey("wards.id"), nullable=False)

    bed_number = db.Column(db.String(30), nullable=False)
    status = db.Column(db.Enum(BedStatus), default=BedStatus.AVAILABLE, nullable=False)

    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    ward = db.relationship("Ward", back_populates="beds")
    admissions = db.relationship("Admission", back_populates="bed")

    def __repr__(self):
        return f"<Bed {self.bed_number} - {self.status.value}>"


class Admission(db.Model):
    __tablename__ = "admissions"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    bed_id = db.Column(db.Integer, db.ForeignKey("beds.id"), nullable=False)
    admitted_by_id = db.Column(db.Integer, db.ForeignKey("staff.id"), nullable=False)

    status = db.Column(db.Enum(AdmissionStatus), default=AdmissionStatus.ADMITTED, nullable=False)
    reason = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)
    admitted_at = db.Column(db.DateTime, default=_utcnow)
    discharged_at = db.Column(db.DateTime, nullable=True)

    patient = db.relationship("Patient", back_populates="admissions")
    bed = db.relationship("Bed", back_populates="admissions")
    admitted_by = db.relationship("Staff", back_populates="admissions")
    ambulance_trips = db.relationship("AmbulanceTrip", back_populates="admission")
    transfers = db.relationship("WardTransfer", back_populates="admission", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Admission Patient {self.patient_id} - Bed {self.bed_id} ({self.status.value})>"


class WardTransfer(db.Model):
    """Tracks bed-to-bed / ward-to-ward transfers within one admission."""
    __tablename__ = "ward_transfers"

    id = db.Column(db.Integer, primary_key=True)
    admission_id = db.Column(db.Integer, db.ForeignKey("admissions.id"), nullable=False)

    from_bed_id = db.Column(db.Integer, db.ForeignKey("beds.id"), nullable=True)
    to_bed_id = db.Column(db.Integer, db.ForeignKey("beds.id"), nullable=False)
    reason = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=_utcnow)
    transferred_at = db.Column(db.DateTime, default=_utcnow)

    admission = db.relationship("Admission", back_populates="transfers")
    from_bed = db.relationship("Bed", foreign_keys=[from_bed_id])
    to_bed = db.relationship("Bed", foreign_keys=[to_bed_id])

    def __repr__(self):
        return f"<WardTransfer Admission {self.admission_id} -> Bed {self.to_bed_id}>"