from datetime import datetime, timezone

from app.extensions import db
from app.core.enums.ward_enums import (
    AdmissionStatus,
    BedStatus,
    WardType,
)


def _utcnow():
    return datetime.now(timezone.utc)


class Ward(db.Model):
    __tablename__ = "wards"

    __table_args__ = (
        db.CheckConstraint(
            "capacity >= 0",
            name="ck_wards_capacity_non_negative",
        ),
        db.UniqueConstraint(
            "clinic_id",
            "name",
            name="uq_wards_clinic_name",
        ),
    )

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

    name = db.Column(
        db.String(150),
        nullable=False,
    )

    ward_type = db.Column(
        db.Enum(WardType),
        default=WardType.GENERAL,
        nullable=False,
        index=True,
    )

    capacity = db.Column(
        db.Integer,
        default=0,
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

    clinic = db.relationship(
        "Clinic",
        back_populates="wards",
    )

    beds = db.relationship(
        "Bed",
        back_populates="ward",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Ward {self.name} ({self.ward_type.value})>"


class Bed(db.Model):
    __tablename__ = "beds"

    __table_args__ = (
        db.UniqueConstraint(
            "ward_id",
            "bed_number",
            name="uq_beds_ward_bed_number",
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    ward_id = db.Column(
        db.Integer,
        db.ForeignKey("wards.id"),
        nullable=False,
        index=True,
    )

    bed_number = db.Column(
        db.String(30),
        nullable=False,
    )

    status = db.Column(
        db.Enum(BedStatus),
        default=BedStatus.AVAILABLE,
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

    ward = db.relationship(
        "Ward",
        back_populates="beds",
    )

    admissions = db.relationship(
        "Admission",
        back_populates="bed",
    )

    from_transfers = db.relationship(
        "WardTransfer",
        foreign_keys="WardTransfer.from_bed_id",
        back_populates="from_bed",
    )

    to_transfers = db.relationship(
        "WardTransfer",
        foreign_keys="WardTransfer.to_bed_id",
        back_populates="to_bed",
    )

    def __repr__(self):
        return f"<Bed {self.bed_number} - {self.status.value}>"


class Admission(db.Model):
    __tablename__ = "admissions"

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

    bed_id = db.Column(
        db.Integer,
        db.ForeignKey("beds.id"),
        nullable=False,
        index=True,
    )

    admitted_by_id = db.Column(
        db.Integer,
        db.ForeignKey("staff.id"),
        nullable=False,
        index=True,
    )

    status = db.Column(
        db.Enum(AdmissionStatus),
        default=AdmissionStatus.ADMITTED,
        nullable=False,
        index=True,
    )

    reason = db.Column(
        db.Text,
        nullable=True,
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

    admitted_at = db.Column(
        db.DateTime,
        default=_utcnow,
        nullable=False,
    )

    discharged_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    patient = db.relationship(
        "Patient",
        back_populates="admissions",
    )

    bed = db.relationship(
        "Bed",
        back_populates="admissions",
    )

    admitted_by = db.relationship(
        "Staff",
        back_populates="admissions",
    )

    ambulance_trips = db.relationship(
        "AmbulanceTrip",
        back_populates="admission",
    )

    transfers = db.relationship(
        "WardTransfer",
        back_populates="admission",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return (
            f"<Admission Patient {self.patient_id} "
            f"- Bed {self.bed_id} ({self.status.value})>"
        )


class WardTransfer(db.Model):
    """
    Tracks bed-to-bed / ward-to-ward transfers
    within a single admission.
    """

    __tablename__ = "ward_transfers"

    __table_args__ = (
        db.CheckConstraint(
            "from_bed_id IS NULL OR from_bed_id != to_bed_id",
            name="ck_ward_transfers_distinct_beds",
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    admission_id = db.Column(
        db.Integer,
        db.ForeignKey("admissions.id"),
        nullable=False,
        index=True,
    )

    from_bed_id = db.Column(
        db.Integer,
        db.ForeignKey("beds.id"),
        nullable=True,
        index=True,
    )

    to_bed_id = db.Column(
        db.Integer,
        db.ForeignKey("beds.id"),
        nullable=False,
        index=True,
    )

    reason = db.Column(
        db.String(255),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        default=_utcnow,
        nullable=False,
    )

    transferred_at = db.Column(
        db.DateTime,
        default=_utcnow,
        nullable=False,
    )

    admission = db.relationship(
        "Admission",
        back_populates="transfers",
    )

    from_bed = db.relationship(
        "Bed",
        foreign_keys=[from_bed_id],
        back_populates="from_transfers",
    )

    to_bed = db.relationship(
        "Bed",
        foreign_keys=[to_bed_id],
        back_populates="to_transfers",
    )

    def __repr__(self):
        return (
            f"<WardTransfer Admission {self.admission_id} "
            f"-> Bed {self.to_bed_id}>"
        )