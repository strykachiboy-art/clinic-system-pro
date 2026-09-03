from app.extensions import db
from app.core.utils.decorators import transactional
from app.core.exceptions import NotFoundError, ValidationError, ConflictError
from app.core.audit.services.audit_services import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.ambulance_enums import TripType, TripStatus, VehicleStatus
from app.modules.ambulance.models.ambulance_model import AmbulanceVehicle, AmbulanceTrip
from app.modules.staff.models.staff_model import Staff


# ---------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------

def get_vehicle(vehicle_id: int) -> AmbulanceVehicle:
    vehicle = AmbulanceVehicle.query.get(vehicle_id)
    if vehicle is None:
        raise NotFoundError(f"Ambulance vehicle {vehicle_id} not found")
    return vehicle


def list_vehicles(clinic_id: int, status: VehicleStatus | None = None) -> list[AmbulanceVehicle]:
    query = AmbulanceVehicle.query.filter_by(clinic_id=clinic_id)
    if status is not None:
        query = query.filter_by(status=status)
    return query.order_by(AmbulanceVehicle.plate_number).all()


@transactional
def create_vehicle(clinic_id: int, plate_number: str, **fields) -> AmbulanceVehicle:
    if not plate_number or not plate_number.strip():
        raise ValidationError("Plate number is required")

    if AmbulanceVehicle.query.filter_by(plate_number=plate_number.strip()).first():
        raise ConflictError(f"Plate number '{plate_number}' already registered")

    vehicle = AmbulanceVehicle(clinic_id=clinic_id, plate_number=plate_number.strip(), **fields)
    db.session.add(vehicle)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="AmbulanceVehicle",
        entity_id=vehicle.id,
        description=f"Ambulance '{vehicle.plate_number}' registered",
    )
    return vehicle


@transactional
def set_vehicle_status(vehicle_id: int, new_status: VehicleStatus) -> AmbulanceVehicle:
    """
    Manual override for maintenance/out-of-service. ON_TRIP is set
    automatically by dispatch_trip(), not meant to be set here directly
    — not hard-blocked though, since dispatchers may need to correct it.
    """
    vehicle = get_vehicle(vehicle_id)
    if vehicle.status == new_status:
        return vehicle

    old_status = vehicle.status.value
    vehicle.status = new_status

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="AmbulanceVehicle",
        entity_id=vehicle.id,
        description=f"Vehicle status changed to '{new_status.value}'",
        old_value={"status": old_status},
        new_value={"status": new_status.value},
    )
    return vehicle


# ---------------------------------------------------------------------
# Trip lifecycle
# ---------------------------------------------------------------------

def get_trip(trip_id: int) -> AmbulanceTrip:
    trip = AmbulanceTrip.query.get(trip_id)
    if trip is None:
        raise NotFoundError(f"Ambulance trip {trip_id} not found")
    return trip


def list_trips(clinic_id: int, status: TripStatus | None = None) -> list[AmbulanceTrip]:
    query = AmbulanceTrip.query.filter_by(clinic_id=clinic_id)
    if status is not None:
        query = query.filter_by(status=status)
    return query.order_by(AmbulanceTrip.requested_at.desc()).all()


def _assert_status(trip: AmbulanceTrip, *allowed: TripStatus):
    if trip.status not in allowed:
        raise ConflictError(
            f"Trip {trip.id} is '{trip.status.value}', expected one of {[s.value for s in allowed]}"
        )


@transactional
def request_trip(clinic_id: int, trip_type: TripType, pickup_address: str | None = None,
                  patient_id: int | None = None, admission_id: int | None = None,
                  destination_address: str | None = None, notes: str | None = None) -> AmbulanceTrip:
    """
    Creates a trip in REQUESTED status. patient_id is intentionally
    optional — real emergency calls often start before the patient is
    identified; it can be linked later via link_patient().
    """
    if trip_type == TripType.INTER_FACILITY_TRANSFER and admission_id is None:
        raise ValidationError("An inter-facility transfer trip requires an admission_id")

    trip = AmbulanceTrip(
        clinic_id=clinic_id,
        trip_type=trip_type,
        status=TripStatus.REQUESTED,
        patient_id=patient_id,
        admission_id=admission_id,
        pickup_address=pickup_address,
        destination_address=destination_address,
        notes=notes,
    )
    db.session.add(trip)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="AmbulanceTrip",
        entity_id=trip.id,
        description=f"Ambulance trip requested ({trip_type.value})",
        new_value={"trip_type": trip_type.value, "pickup_address": pickup_address},
    )
    return trip


@transactional
def dispatch_trip(trip_id: int, vehicle_id: int, driver_id: int, paramedic_id: int | None = None) -> AmbulanceTrip:
    """
    Assigns vehicle + crew and moves REQUESTED -> DISPATCHED. Locks the
    vehicle row to prevent double-booking (same pattern as ward bed
    admission / pharmacy FEFO). Crew role/status/clinic validation
    happens in AmbulanceTrip.validate_crew_member (model-level) —
    triggered here by assigning trip.driver/paramedic as OBJECTS, not
    raw driver_id/paramedic_id columns, since @validates only fires on
    relationship attribute assignment, not FK column assignment.
    """
    trip = get_trip(trip_id)
    _assert_status(trip, TripStatus.REQUESTED)

    vehicle = AmbulanceVehicle.query.filter_by(id=vehicle_id).with_for_update().first()
    if vehicle is None:
        raise NotFoundError(f"Vehicle {vehicle_id} not found")
    if vehicle.status != VehicleStatus.AVAILABLE:
        raise ConflictError(f"Vehicle {vehicle_id} is '{vehicle.status.value}', not available")

    driver = Staff.query.get(driver_id)
    if driver is None:
        raise NotFoundError(f"Staff {driver_id} not found")

    paramedic = None
    if paramedic_id is not None:
        paramedic = Staff.query.get(paramedic_id)
        if paramedic is None:
            raise NotFoundError(f"Staff {paramedic_id} not found")

    try:
        trip.driver = driver          # triggers AmbulanceTrip.validate_crew_member
        trip.paramedic = paramedic    # triggers validate_crew_member (no-op if None)
    except ValueError as e:
        raise ValidationError(str(e)) from e

    vehicle.status = VehicleStatus.ON_TRIP
    trip.vehicle_id = vehicle_id
    trip.status = TripStatus.DISPATCHED
    trip.dispatched_at = db.func.now()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="AmbulanceTrip",
        entity_id=trip.id,
        description=f"Trip dispatched — vehicle {vehicle_id}, driver {driver_id}"
        + (f", paramedic {paramedic_id}" if paramedic_id else ""),
        old_value={"status": TripStatus.REQUESTED.value},
        new_value={"status": trip.status.value},
    )
    return trip


@transactional
def update_trip_status(trip_id: int, new_status: TripStatus) -> AmbulanceTrip:
    """
    Advances EN_ROUTE_TO_PICKUP -> AT_PICKUP -> EN_ROUTE_TO_DESTINATION.
    Kept as one generic advancer since these transitions carry no extra
    side effects — unlike dispatch (locks a vehicle) or complete
    (frees the vehicle + timestamps), which get their own functions.
    """
    trip = get_trip(trip_id)

    valid_transitions = {
        TripStatus.DISPATCHED: TripStatus.EN_ROUTE_TO_PICKUP,
        TripStatus.EN_ROUTE_TO_PICKUP: TripStatus.AT_PICKUP,
        TripStatus.AT_PICKUP: TripStatus.EN_ROUTE_TO_DESTINATION,
    }
    expected_next = valid_transitions.get(trip.status)
    if expected_next != new_status:
        raise ConflictError(
            f"Trip {trip.id} cannot move from '{trip.status.value}' to '{new_status.value}'"
        )

    old_status = trip.status.value
    trip.status = new_status
    if new_status == TripStatus.AT_PICKUP:
        trip.pickup_at = db.func.now()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="AmbulanceTrip",
        entity_id=trip.id,
        description=f"Trip status advanced to '{new_status.value}'",
        old_value={"status": old_status},
        new_value={"status": new_status.value},
    )
    return trip


@transactional
def link_patient(trip_id: int, patient_id: int) -> AmbulanceTrip:
    """Attach a patient once identified — typically called at or after pickup."""
    trip = get_trip(trip_id)
    if trip.patient_id is not None and trip.patient_id != patient_id:
        raise ConflictError(f"Trip {trip_id} is already linked to a different patient")

    trip.patient_id = patient_id
    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="AmbulanceTrip",
        entity_id=trip.id,
        description=f"Patient {patient_id} linked to trip",
    )
    return trip


@transactional
def complete_trip(trip_id: int) -> AmbulanceTrip:
    """Frees the vehicle and closes out the trip. Billing is NOT created
    here — same separation as lab/prescription; billing_service owns
    invoice creation. This only marks the trip ready to be billed."""
    trip = get_trip(trip_id)
    _assert_status(trip, TripStatus.EN_ROUTE_TO_DESTINATION)

    if trip.vehicle_id:
        vehicle = AmbulanceVehicle.query.get(trip.vehicle_id)
        vehicle.status = VehicleStatus.AVAILABLE

    old_status = trip.status.value
    trip.status = TripStatus.COMPLETED
    trip.completed_at = db.func.now()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="AmbulanceTrip",
        entity_id=trip.id,
        description="Trip completed, vehicle released",
        old_value={"status": old_status},
        new_value={"status": trip.status.value},
    )
    return trip


@transactional
def link_invoice(trip_id: int, invoice_id: int) -> AmbulanceTrip:
    """Called by billing_service (or a route orchestrating both) once
    an invoice has been created for a completed trip."""
    trip = get_trip(trip_id)
    if trip.status != TripStatus.COMPLETED:
        raise ConflictError("Can only attach an invoice to a completed trip")
    if trip.invoice_id is not None:
        raise ConflictError(f"Trip {trip_id} is already linked to invoice {trip.invoice_id}")

    trip.invoice_id = invoice_id
    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="AmbulanceTrip",
        entity_id=trip.id,
        description=f"Invoice {invoice_id} linked to trip",
    )
    return trip


@transactional
def cancel_trip(trip_id: int, reason: str | None = None) -> AmbulanceTrip:
    trip = get_trip(trip_id)
    if trip.status in (TripStatus.COMPLETED, TripStatus.CANCELLED):
        raise ConflictError(f"Cannot cancel a trip that is already {trip.status.value}")

    if trip.vehicle_id:
        vehicle = AmbulanceVehicle.query.get(trip.vehicle_id)
        if vehicle and vehicle.status == VehicleStatus.ON_TRIP:
            vehicle.status = VehicleStatus.AVAILABLE

    old_status = trip.status.value
    trip.status = TripStatus.CANCELLED
    trip.cancelled_at = db.func.now()
    trip.cancellation_reason = reason

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="AmbulanceTrip",
        entity_id=trip.id,
        description="Trip cancelled" + (f": {reason}" if reason else ""),
        old_value={"status": old_status},
        new_value={"status": trip.status.value},
    )
    return trip