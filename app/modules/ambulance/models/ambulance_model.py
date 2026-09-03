from datetime import datetime, timezone
from app.extensions import db
from app.core.enums.ambulance_enums import TripType, TripStatus, VehicleStatus, EquipmentLevel
from app.core.enums.staff_enums import StaffRole, StaffStatus

def _utcnow():
    return datetime.now(timezone.utc)


class AmbulanceVehicle(db.Model):
    __tablename__ = "ambulance_vehicles"

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=False)

    plate_number = db.Column(db.String(30), unique=True, nullable=False)
    equipment_level = db.Column(db.Enum(EquipmentLevel), default=EquipmentLevel.BLS, nullable=False)
    capacity = db.Column(db.Integer, default=1) 

    status = db.Column(db.Enum(VehicleStatus), default=VehicleStatus.AVAILABLE, nullable=False)
    last_service_date = db.Column(db.Date, nullable=True)

    created_at = db.Column(db.DateTime, default=_utcnow)

    clinic = db.relationship("Clinic", back_populates="ambulance_vehicles")
    trips = db.relationship("AmbulanceTrip", back_populates="vehicle")

    def __repr__(self):
        return f"<AmbulanceVehicle {self.plate_number} ({self.status.value})>"


class AmbulanceTrip(db.Model):
    __tablename__ = "ambulance_trips"

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=False)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("ambulance_vehicles.id"), nullable=True)

    # Nullable — an emergency dispatch often starts before the patient
    # is identified. Linked once known.
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=True)

    # Crew two-person model (driver + paramedic), matching
    # typical real-world ambulance staffing. Both nullable since a
    # trip can be REQUESTED before crew is assigned.
    driver_id = db.Column(db.Integer, db.ForeignKey("staff.id"), nullable=True)
    paramedic_id = db.Column(db.Integer, db.ForeignKey("staff.id"), nullable=True)

    trip_type = db.Column(db.Enum(TripType), nullable=False)
    status = db.Column(db.Enum(TripStatus), default=TripStatus.REQUESTED, nullable=False)

    # Links this trip to the admission being transferred, giving
    # AdmissionStatus.TRANSFERRED an actual real-world counterpart.
    admission_id = db.Column(db.Integer, db.ForeignKey("admissions.id"), nullable=True)

    # Location — plain coordinates + free-text address, not live tracking.
    pickup_address = db.Column(db.String(255), nullable=True)
    pickup_lat = db.Column(db.Numeric(9, 6), nullable=True)
    pickup_lng = db.Column(db.Numeric(9, 6), nullable=True)
    destination_address = db.Column(db.String(255), nullable=True)
    destination_lat = db.Column(db.Numeric(9, 6), nullable=True)
    destination_lng = db.Column(db.Numeric(9, 6), nullable=True)

    # Status pipeline timestamps — mirrors LabOrder's pattern of one
    # timestamp per real-world milestone, so the full timeline is
    # reconstructable without parsing audit logs.
    requested_at = db.Column(db.DateTime, default=_utcnow)
    dispatched_at = db.Column(db.DateTime, nullable=True)
    pickup_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    cancellation_reason = db.Column(db.String(255), nullable=True)

    notes = db.Column(db.Text, nullable=True)

    # Billing hook — populated once the trip completes, same pattern
    # as lab/prescription NOT owning their own invoicing logic.
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=True)

    clinic = db.relationship("Clinic", back_populates="ambulance_trips")
    vehicle = db.relationship("AmbulanceVehicle", back_populates="trips")
    patient = db.relationship("Patient", back_populates="ambulance_trips")
    driver = db.relationship("Staff", back_populates="driver_trips", foreign_keys=[driver_id])
    paramedic = db.relationship("Staff", back_populates="paramedic_trips", foreign_keys=[paramedic_id])
    admission = db.relationship("Admission", back_populates="ambulance_trips")
    invoice = db.relationship("Invoice", back_populates="ambulance_trip", uselist=False)

    @db.validates("driver", "paramedic")
    def validate_crew_member(self, relationship_name, staff):
        if staff is None:
            return staff

        expected_role = StaffRole.DRIVER if relationship_name == "driver" else StaffRole.PARAMEDIC
        if staff.role != expected_role:
            raise ValueError(f"Ambulance {relationship_name} must have the {expected_role.value} role")
        if staff.status != StaffStatus.ACTIVE:
            raise ValueError(f"Ambulance {relationship_name} must be active")
        if self.clinic_id is not None and staff.clinic_id != self.clinic_id:
            raise ValueError(f"Ambulance {relationship_name} must belong to the same clinic")

        return staff

    def __repr__(self):
        return f"<AmbulanceTrip {self.id} ({self.trip_type.value} - {self.status.value})>"