from datetime import datetime, timezone

from app.extensions import db
from app.core.enums.patient_enums import (
    Gender,
    BloodType,
    FamilyRelation,
)


def _utcnow():
    return datetime.now(timezone.utc)


class Patient(db.Model):
    __tablename__ = "patients"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    clinic_id = db.Column(
        db.Integer,
        db.ForeignKey("clinics.id"),
        nullable=False,
        index=True,
    )

    emirates_id = db.Column(
        db.String(20),
        unique=True,
        nullable=True,
        index=True,
    )

    umrn = db.Column(
        db.String(50),
        unique=True,
        nullable=True,
        index=True,
    )

    # -------------------------------------------------------------
    # Identity
    # -------------------------------------------------------------

    first_name = db.Column(
        db.String(80),
        nullable=False,
    )

    last_name = db.Column(
        db.String(80),
        nullable=False,
    )

    date_of_birth = db.Column(
        db.Date,
        nullable=True,
    )

    gender = db.Column(
        db.Enum(Gender),
        nullable=True,
    )

    blood_type = db.Column(
        db.Enum(BloodType),
        default=BloodType.UNKNOWN,
        nullable=False,
    )

    # -------------------------------------------------------------
    # Contact
    # -------------------------------------------------------------

    phone = db.Column(
        db.String(30),
        nullable=True,
    )

    email = db.Column(
        db.String(120),
        nullable=True,
    )

    address = db.Column(
        db.String(255),
        nullable=True,
    )

    # -------------------------------------------------------------
    # Medical baseline
    # -------------------------------------------------------------

    allergies = db.Column(
        db.Text,
        nullable=True,
    )

    chronic_conditions = db.Column(
        db.Text,
        nullable=True,
    )

    # -------------------------------------------------------------
    # Patient identity / lifecycle
    # -------------------------------------------------------------

    patient_number = db.Column(
        db.String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    is_active = db.Column(
        db.Boolean,
        default=True,
        nullable=False,
        index=True,
    )

    # -------------------------------------------------------------
    # AI feature cache
    # -------------------------------------------------------------

    ai_risk_score = db.Column(
        db.Float,
        nullable=True,
    )

    ai_summary = db.Column(
        db.Text,
        nullable=True,
    )

    ai_triage_data = db.Column(
        db.JSON,
        nullable=True,
    )

    # -------------------------------------------------------------
    # Timestamps
    # -------------------------------------------------------------

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

    # -------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------

    clinic = db.relationship(
        "Clinic",
        back_populates="patients",
    )

    family_members = db.relationship(
        "PatientFamilyMember",
        back_populates="patient",
        cascade="all, delete-orphan",
        foreign_keys="PatientFamilyMember.patient_id",
    )

    insurances = db.relationship(
        "PatientInsurance",
        back_populates="patient",
        cascade="all, delete-orphan",
    )

    vitals_history = db.relationship(
        "PatientVitals",
        back_populates="patient",
        cascade="all, delete-orphan",
    )

    ai_logs = db.relationship(
        "AILog",
        back_populates="patient",
    )

    appointments = db.relationship(
        "Appointment",
        back_populates="patient",
    )

    invoices = db.relationship(
        "Invoice",
        back_populates="patient",
    )

    consultations = db.relationship(
        "Consultation",
        back_populates="patient",
    )

    lab_orders = db.relationship(
        "LabOrder",
        back_populates="patient",
    )

    prescriptions = db.relationship(
        "Prescription",
        back_populates="patient",
    )

    admissions = db.relationship(
        "Admission",
        back_populates="patient",
    )

    bed_reservations = db.relationship(
        "BedReservation",
        back_populates="patient",
    )

    hie_submissions = db.relationship(
        "HIESubmission",
        back_populates="patient",
    )

    ambulance_trips = db.relationship(
        "AmbulanceTrip",
        back_populates="patient",
    )

    def __repr__(self):
        return (
            f"<Patient {self.first_name} "
            f"{self.last_name} ({self.patient_number})>"
        )


class PatientFamilyMember(db.Model):
    __tablename__ = "patient_family_members"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    patient_id = db.Column(
        db.Integer,
        db.ForeignKey("patients.id"),
        nullable=False,
        index=True,
    )

    # Optional link if this family member is also
    # a registered patient.
    related_patient_id = db.Column(
        db.Integer,
        db.ForeignKey("patients.id"),
        nullable=True,
        index=True,
    )

    full_name = db.Column(
        db.String(150),
        nullable=False,
    )

    relation = db.Column(
        db.Enum(FamilyRelation),
        nullable=False,
    )

    phone = db.Column(
        db.String(30),
        nullable=True,
    )

    is_emergency_contact = db.Column(
        db.Boolean,
        default=False,
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

    patient = db.relationship(
        "Patient",
        back_populates="family_members",
        foreign_keys=[patient_id],
    )

    related_patient = db.relationship(
        "Patient",
        foreign_keys=[related_patient_id],
    )

    def __repr__(self):
        return (
            f"<PatientFamilyMember "
            f"{self.full_name} ({self.relation.value})>"
        )


class PatientInsurance(db.Model):
    __tablename__ = "patient_insurances"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    patient_id = db.Column(
        db.Integer,
        db.ForeignKey("patients.id"),
        nullable=False,
        index=True,
    )

    provider_name = db.Column(
        db.String(150),
        nullable=False,
    )

    policy_number = db.Column(
        db.String(100),
        nullable=False,
    )

    plan_type = db.Column(
        db.String(100),
        nullable=True,
    )

    coverage_start = db.Column(
        db.Date,
        nullable=True,
    )

    coverage_end = db.Column(
        db.Date,
        nullable=True,
    )

    is_primary = db.Column(
        db.Boolean,
        default=True,
        nullable=False,
    )

    is_active = db.Column(
        db.Boolean,
        default=True,
        nullable=False,
        index=True,
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

    patient = db.relationship(
        "Patient",
        back_populates="insurances",
    )

    def __repr__(self):
        return (
            f"<PatientInsurance "
            f"{self.provider_name} - {self.policy_number}>"
        )


class PatientVitals(db.Model):
    """
    Historical vitals log.

    One row represents one clinical reading, allowing the application
    to build patient vital-sign trends over time.
    """

    __tablename__ = "patient_vitals"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    patient_id = db.Column(
        db.Integer,
        db.ForeignKey("patients.id"),
        nullable=False,
        index=True,
    )

    consultation_id = db.Column(
        db.Integer,
        db.ForeignKey("consultations.id"),
        nullable=True,
        index=True,
    )

    recorded_by_id = db.Column(
        db.Integer,
        db.ForeignKey("staff.id"),
        nullable=True,
        index=True,
    )

    temperature_c = db.Column(
        db.Numeric(4, 1),
        nullable=True,
    )

    blood_pressure_systolic = db.Column(
        db.Integer,
        nullable=True,
    )

    blood_pressure_diastolic = db.Column(
        db.Integer,
        nullable=True,
    )

    heart_rate_bpm = db.Column(
        db.Integer,
        nullable=True,
    )

    respiratory_rate = db.Column(
        db.Integer,
        nullable=True,
    )

    oxygen_saturation = db.Column(
        db.Numeric(4, 1),
        nullable=True,
    )

    weight_kg = db.Column(
        db.Numeric(5, 2),
        nullable=True,
    )

    height_cm = db.Column(
        db.Numeric(5, 2),
        nullable=True,
    )

    recorded_at = db.Column(
        db.DateTime,
        default=_utcnow,
        nullable=False,
        index=True,
    )

    patient = db.relationship(
        "Patient",
        back_populates="vitals_history",
    )

    def __repr__(self):
        return (
            f"<PatientVitals Patient "
            f"{self.patient_id} @ {self.recorded_at}>"
        )