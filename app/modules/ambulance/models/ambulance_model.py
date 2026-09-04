from datetime import datetime, timezone

from app.extensions import db

from app.core.enums.ambulance_enums import (
    EquipmentLevel,
    TripStatus,
    TripType,
    VehicleStatus,
)
from app.core.enums.staff_enums import StaffStatus


def _utcnow():
    return datetime.now(timezone.utc)


class AmbulanceVehicle(db.Model):
    __tablename__ = "ambulance_vehicles"

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

    plate_number = db.Column(
        db.String(30),
        unique=True,
        nullable=False,
    )

    equipment_level = db.Column(
        db.Enum(EquipmentLevel),
        default=EquipmentLevel.BLS,
        nullable=False,
    )

    capacity = db.Column(
        db.Integer,
        default=1,
        nullable=False,
    )

    status = db.Column(
        db.Enum(VehicleStatus),
        default=VehicleStatus.AVAILABLE,
        nullable=False,
    )

    last_service_date = db.Column(
        db.Date,
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

    clinic = db.relationship(
        "Clinic",
        back_populates="ambulance_vehicles",
    )

    trips = db.relationship(
        "AmbulanceTrip",
        back_populates="vehicle",
    )

    def __repr__(self):
        return (
            f"<AmbulanceVehicle "
            f"{self.plate_number} "
            f"({self.status.value})>"
        )


class AmbulanceTrip(db.Model):
    __tablename__ = "ambulance_trips"

    __table_args__ = (
        db.CheckConstraint(
            """
            driver_id IS NULL
            OR paramedic_id IS NULL
            OR driver_id != paramedic_id
            """,
            name="ck_ambulance_trip_distinct_crew",
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

    vehicle_id = db.Column(
        db.Integer,
        db.ForeignKey("ambulance_vehicles.id"),
        nullable=True,
        index=True,
    )

    patient_id = db.Column(
        db.Integer,
        db.ForeignKey("patients.id"),
        nullable=True,
        index=True,
    )

    driver_id = db.Column(
        db.Integer,
        db.ForeignKey("staff.id"),
        nullable=True,
        index=True,
    )

    paramedic_id = db.Column(
        db.Integer,
        db.ForeignKey("staff.id"),
        nullable=True,
        index=True,
    )

    trip_type = db.Column(
        db.Enum(TripType),
        nullable=False,
    )

    status = db.Column(
        db.Enum(TripStatus),
        default=TripStatus.REQUESTED,
        nullable=False,
    )

    admission_id = db.Column(
        db.Integer,
        db.ForeignKey("admissions.id"),
        nullable=True,
        index=True,
    )

    pickup_address = db.Column(
        db.String(255),
        nullable=True,
    )

    pickup_lat = db.Column(
        db.Numeric(9, 6),
        nullable=True,
    )

    pickup_lng = db.Column(
        db.Numeric(9, 6),
        nullable=True,
    )

    destination_address = db.Column(
        db.String(255),
        nullable=True,
    )

    destination_lat = db.Column(
        db.Numeric(9, 6),
        nullable=True,
    )

    destination_lng = db.Column(
        db.Numeric(9, 6),
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

    requested_at = db.Column(
        db.DateTime,
        default=_utcnow,
        nullable=False,
    )

    dispatched_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    pickup_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    completed_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    cancelled_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    cancellation_reason = db.Column(
        db.String(255),
        nullable=True,
    )

    notes = db.Column(
        db.Text,
        nullable=True,
    )

    invoice_id = db.Column(
        db.Integer,
        db.ForeignKey("invoices.id"),
        nullable=True,
        unique=True,
        index=True,
    )

    clinic = db.relationship(
        "Clinic",
        back_populates="ambulance_trips",
    )

    vehicle = db.relationship(
        "AmbulanceVehicle",
        back_populates="trips",
    )

    patient = db.relationship(
        "Patient",
        back_populates="ambulance_trips",
    )

    driver = db.relationship(
        "Staff",
        back_populates="driver_trips",
        foreign_keys=[driver_id],
    )

    paramedic = db.relationship(
        "Staff",
        back_populates="paramedic_trips",
        foreign_keys=[paramedic_id],
    )

    admission = db.relationship(
        "Admission",
        back_populates="ambulance_trips",
    )

    invoice = db.relationship(
        "Invoice",
        back_populates="ambulance_trip",
        uselist=False,
    )

    @db.validates("driver", "paramedic")
    def validate_crew_member(
        self,
        relationship_name,
        staff,
    ):
        if staff is None:
            return staff

        if staff.status != StaffStatus.ACTIVE:
            raise ValueError(
                f"Ambulance {relationship_name} must be active"
            )

        if (
            self.clinic_id is not None
            and staff.clinic_id != self.clinic_id
        ):
            raise ValueError(
                f"Ambulance {relationship_name} "
                "must belong to the same clinic"
            )

        return staff

    def __repr__(self):
        return (
            f"<AmbulanceTrip {self.id} "
            f"({self.trip_type.value} - "
            f"{self.status.value})>"
        )