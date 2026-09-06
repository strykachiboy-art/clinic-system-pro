from flask import g, has_request_context

from app.extensions import db

from app.core.auth.user.models.user_model import User

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

from app.core.utils.decorators import transactional

from app.core.audit.services.audit_service import (
    create_audit_log,
)

from app.core.enums.audit_enums import AuditAction

from app.core.enums.ambulance_enums import (
    TripStatus,
    TripType,
    VehicleStatus,
)

from app.core.enums.role_enums import Role

from app.core.enums.staff_enums import StaffStatus

from app.modules.clinic.services.clinic_service import (
    ensure_clinic_active,
)

from app.modules.patient.models.patient_model import (
    Patient,
)

from app.modules.staff.models.staff_model import (
    Staff,
)

from app.modules.billing.models.billing_model import (
    Invoice,
)

from app.modules.ward.models.ward_model import (
    Admission,
)

from app.modules.ambulance.models.ambulance_model import (
    AmbulanceTrip,
    AmbulanceVehicle,
)


# ============================================================
# AUTHENTICATION / CLINIC CONTEXT
# ============================================================


def _current_user() -> User:
    """
    Return the authenticated User from the decorator-provided
    authentication context.

    This helper is only enforced when the service is called
    inside an HTTP request. Direct service-level tests can still
    call the service without Flask request context.
    """
    if not has_request_context():
        raise ValidationError(
            "Authenticated request context is required"
        )

    user_id = getattr(g, "current_user_id", None)

    if user_id is None:
        raise ValidationError(
            "Authenticated user is required"
        )

    user = db.session.get(
        User,
        user_id,
    )

    if user is None:
        raise ValidationError(
            "Authenticated user was not found"
        )

    if not user.is_active:
        raise ValidationError(
            "User account is inactive"
        )

    return user


def _current_clinic_id() -> int:
    """
    Return the authenticated user's clinic ID.
    """
    user = _current_user()

    if user.clinic_id is None:
        raise ValidationError(
            "Authenticated user is not associated "
            "with a clinic"
        )

    return user.clinic_id


def _assert_authenticated_clinic(
    clinic_id: int,
) -> None:
    """
    Verify that the requested clinic belongs to the
    authenticated user.

    This prevents a client from accessing another clinic by
    supplying a different clinic_id.

    When the service is called directly without a Flask request
    context, this check is skipped so service-level tests and
    internal jobs can still operate using explicit clinic IDs.
    """
    if not has_request_context():
        return

    authenticated_clinic_id = _current_clinic_id()

    if authenticated_clinic_id != clinic_id:
        raise ValidationError(
            "Resource does not belong "
            "to the authenticated user's clinic"
        )


def _audit_user_id() -> int | None:
    """
    Return the authenticated user ID for audit logging.

    Returns None when the service is being executed outside
    an HTTP request context.
    """
    if not has_request_context():
        return None

    user_id = getattr(
        g,
        "current_user_id",
        None,
    )

    if user_id is None:
        return None

    return user_id


# ============================================================
# VEHICLE
# ============================================================


def get_vehicle(
    vehicle_id: int,
) -> AmbulanceVehicle:
    """
    Retrieve an ambulance vehicle.

    Historical vehicle information remains accessible even if
    the clinic is inactive.

    When called through an authenticated HTTP request, the
    vehicle must belong to the authenticated user's clinic.
    """
    vehicle = db.session.get(
        AmbulanceVehicle,
        vehicle_id,
    )

    if vehicle is None:
        raise NotFoundError(
            f"Ambulance vehicle {vehicle_id} not found"
        )

    _assert_authenticated_clinic(
        vehicle.clinic_id,
    )

    return vehicle


def list_vehicles(
    clinic_id: int,
    status: VehicleStatus | None = None,
) -> list[AmbulanceVehicle]:
    """
    List ambulance vehicles for a clinic.

    Read operations do not require the clinic to be active.

    The requested clinic is still required to match the
    authenticated user's clinic when called through an API
    request.
    """
    _assert_authenticated_clinic(
        clinic_id,
    )

    query = AmbulanceVehicle.query.filter_by(
        clinic_id=clinic_id,
    )

    if status is not None:
        query = query.filter_by(
            status=status,
        )

    return query.order_by(
        AmbulanceVehicle.plate_number.asc(),
    ).all()


@transactional
def create_vehicle(
    clinic_id: int,
    plate_number: str,
    equipment_level,
    capacity: int = 1,
    status: VehicleStatus = VehicleStatus.AVAILABLE,
    last_service_date=None,
) -> AmbulanceVehicle:
    """
    Register a new ambulance vehicle.

    New vehicles can only be created for an active clinic.
    The clinic must also belong to the authenticated user when
    called through an API request.
    """

    _assert_authenticated_clinic(
        clinic_id,
    )

    ensure_clinic_active(
        clinic_id,
    )

    if not isinstance(plate_number, str):
        raise ValidationError(
            "Plate number must be a string"
        )

    plate_number = plate_number.strip().upper()

    if not plate_number:
        raise ValidationError(
            "Plate number is required"
        )

    if capacity < 1:
        raise ValidationError(
            "Vehicle capacity must be at least 1"
        )

    if status != VehicleStatus.AVAILABLE:
        raise ValidationError(
            "A newly registered ambulance must "
            "start with AVAILABLE status"
        )

    existing = AmbulanceVehicle.query.filter_by(
        plate_number=plate_number,
    ).first()

    if existing is not None:
        raise ConflictError(
            f"Ambulance vehicle with plate "
            f"{plate_number} already exists"
        )

    vehicle = AmbulanceVehicle(
        clinic_id=clinic_id,
        plate_number=plate_number,
        equipment_level=equipment_level,
        capacity=capacity,
        status=VehicleStatus.AVAILABLE,
        last_service_date=last_service_date,
    )

    db.session.add(vehicle)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="AmbulanceVehicle",
        entity_id=vehicle.id,
        description=(
            f"Ambulance vehicle "
            f"{vehicle.plate_number} created"
        ),
        new_value={
            "clinic_id": clinic_id,
            "plate_number": vehicle.plate_number,
            "equipment_level": (
                vehicle.equipment_level.value
            ),
            "capacity": vehicle.capacity,
            "status": vehicle.status.value,
        },
        user_id=_audit_user_id(),
    )

    return vehicle


@transactional
def set_vehicle_status(
    vehicle_id: int,
    new_status: VehicleStatus,
) -> AmbulanceVehicle:
    """
    Manually change a vehicle's availability status.

    ON_TRIP is controlled by trip dispatch/completion/
    cancellation and cannot be manually assigned here.
    """

    vehicle = get_vehicle(
        vehicle_id,
    )

    ensure_clinic_active(
        vehicle.clinic_id,
    )

    if vehicle.status == new_status:
        return vehicle

    if new_status == VehicleStatus.ON_TRIP:
        raise ValidationError(
            "ON_TRIP is managed automatically by "
            "ambulance dispatch and cannot be set manually"
        )

    if vehicle.status == VehicleStatus.ON_TRIP:
        raise ConflictError(
            "Cannot manually change the status "
            "of an ambulance that is currently on a trip"
        )

    old_status = vehicle.status.value

    vehicle.status = new_status

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="AmbulanceVehicle",
        entity_id=vehicle.id,
        description=(
            f"Ambulance vehicle "
            f"{vehicle.plate_number} status changed "
            f"from {old_status} to {new_status.value}"
        ),
        old_value={
            "status": old_status,
        },
        new_value={
            "status": new_status.value,
        },
        user_id=_audit_user_id(),
    )

    return vehicle


# ============================================================
# TRIP RETRIEVAL
# ============================================================


def get_trip(
    trip_id: int,
) -> AmbulanceTrip:
    """
    Retrieve an ambulance trip.

    Historical trips remain retrievable even if their clinic
    is inactive or suspended.

    When called through an authenticated HTTP request, the
    trip must belong to the authenticated user's clinic.
    """
    trip = db.session.get(
        AmbulanceTrip,
        trip_id,
    )

    if trip is None:
        raise NotFoundError(
            f"Ambulance trip {trip_id} not found"
        )

    _assert_authenticated_clinic(
        trip.clinic_id,
    )

    return trip


def list_trips(
    clinic_id: int,
    status: TripStatus | None = None,
) -> list[AmbulanceTrip]:
    """
    List ambulance trips for a clinic.

    Historical retrieval remains available regardless of
    clinic status.
    """

    _assert_authenticated_clinic(
        clinic_id,
    )

    query = AmbulanceTrip.query.filter_by(
        clinic_id=clinic_id,
    )

    if status is not None:
        query = query.filter_by(
            status=status,
        )

    return query.order_by(
        AmbulanceTrip.requested_at.desc(),
    ).all()


# ============================================================
# INTERNAL HELPERS
# ============================================================


def _assert_status(
    trip: AmbulanceTrip,
    *allowed_statuses: TripStatus,
):
    """
    Ensure a trip is currently in one of the expected states.
    """
    if trip.status not in allowed_statuses:
        allowed = ", ".join(
            status.value
            for status in allowed_statuses
        )

        raise ConflictError(
            f"Trip {trip.id} is currently "
            f"'{trip.status.value}' and cannot perform "
            f"this action. Allowed status: {allowed}"
        )


def _get_patient(
    patient_id: int,
    clinic_id: int,
) -> Patient:
    """
    Retrieve and validate a patient for ambulance use.
    """
    patient = db.session.get(
        Patient,
        patient_id,
    )

    if patient is None:
        raise NotFoundError(
            f"Patient {patient_id} not found"
        )

    if patient.clinic_id != clinic_id:
        raise ValidationError(
            "Patient does not belong "
            "to the trip clinic"
        )

    if not patient.is_active:
        raise ValidationError(
            "Cannot use an inactive patient "
            "for an ambulance trip"
        )

    return patient


def _get_admission(
    admission_id: int,
    clinic_id: int,
) -> Admission:
    """
    Retrieve and validate an admission.

    Clinic ownership is verified through the admission's
    patient.
    """
    admission = db.session.get(
        Admission,
        admission_id,
    )

    if admission is None:
        raise NotFoundError(
            f"Admission {admission_id} not found"
        )

    if admission.patient is None:
        raise ValidationError(
            "Admission is not linked to a patient"
        )

    if admission.patient.clinic_id != clinic_id:
        raise ValidationError(
            "Admission does not belong "
            "to the trip clinic"
        )

    return admission


def _get_ambulance_crew_member(
    staff_id: int,
    clinic_id: int,
    allowed_roles: tuple[Role, ...],
    position: str,
) -> Staff:
    """
    Validate an ambulance crew member.

    Checks:
    - staff exists
    - staff is active
    - staff belongs to trip clinic
    - linked user exists
    - linked user is active
    - linked user has an appropriate ambulance role
    """

    staff = db.session.get(
        Staff,
        staff_id,
    )

    if staff is None:
        raise NotFoundError(
            f"{position.capitalize()} "
            f"{staff_id} not found"
        )

    if staff.status != StaffStatus.ACTIVE:
        raise ValidationError(
            f"{position.capitalize()} must be active"
        )

    if staff.clinic_id != clinic_id:
        raise ValidationError(
            f"{position.capitalize()} must belong "
            "to the same clinic as the trip"
        )

    if staff.user is None:
        raise ValidationError(
            f"{position.capitalize()} is not linked "
            "to a user account"
        )

    if not staff.user.is_active:
        raise ValidationError(
            f"{position.capitalize()}'s user account "
            "is inactive"
        )

    if staff.user.role not in allowed_roles:
        allowed = ", ".join(
            role.value
            for role in allowed_roles
        )

        raise ValidationError(
            f"{position.capitalize()} must have "
            f"one of these roles: {allowed}"
        )

    return staff


def _lock_vehicle(
    vehicle_id: int,
) -> AmbulanceVehicle:
    """
    Lock a vehicle row for a state-changing operation.

    Clinic ownership is checked by the caller because the
    expected clinic depends on the operation.
    """
    vehicle = (
        AmbulanceVehicle.query
        .filter_by(
            id=vehicle_id,
        )
        .with_for_update()
        .first()
    )

    if vehicle is None:
        raise NotFoundError(
            f"Ambulance vehicle "
            f"{vehicle_id} not found"
        )

    return vehicle


# ============================================================
# REQUEST TRIP
# ============================================================


@transactional
def request_trip(
    clinic_id: int,
    trip_type: TripType,
    patient_id: int | None = None,
    admission_id: int | None = None,
    pickup_address: str | None = None,
    pickup_lat=None,
    pickup_lng=None,
    destination_address: str | None = None,
    destination_lat=None,
    destination_lng=None,
    notes: str | None = None,
) -> AmbulanceTrip:
    """
    Create a new ambulance trip in REQUESTED status.

    Patient identification may be omitted for an initial
    emergency request and linked later.

    DISCHARGE_TRANSPORT and INTER_FACILITY_TRANSFER require
    an admission and patient.
    """

    _assert_authenticated_clinic(
        clinic_id,
    )

    ensure_clinic_active(
        clinic_id,
    )

    patient = None
    admission = None

    # --------------------------------------------------------
    # Patient
    # --------------------------------------------------------

    if patient_id is not None:
        patient = _get_patient(
            patient_id=patient_id,
            clinic_id=clinic_id,
        )

    # --------------------------------------------------------
    # Admission
    # --------------------------------------------------------

    if admission_id is not None:
        admission = _get_admission(
            admission_id=admission_id,
            clinic_id=clinic_id,
        )

        if (
            patient is not None
            and admission.patient_id != patient.id
        ):
            raise ValidationError(
                "Admission does not belong "
                "to the specified patient"
            )

        if patient is None:
            patient = admission.patient

            if (
                patient is not None
                and not patient.is_active
            ):
                raise ValidationError(
                    "Cannot create an ambulance trip "
                    "for an inactive patient"
                )

    # --------------------------------------------------------
    # Trip-type requirements
    # --------------------------------------------------------

    if trip_type in {
        TripType.DISCHARGE_TRANSPORT,
        TripType.INTER_FACILITY_TRANSFER,
    }:
        if admission is None:
            raise ValidationError(
                f"{trip_type.value} requires an admission"
            )

        if patient is None:
            raise ValidationError(
                f"{trip_type.value} requires a patient"
            )

    # --------------------------------------------------------
    # Create
    # --------------------------------------------------------

    trip = AmbulanceTrip(
        clinic_id=clinic_id,
        trip_type=trip_type,
        status=TripStatus.REQUESTED,
        pickup_address=pickup_address,
        pickup_lat=pickup_lat,
        pickup_lng=pickup_lng,
        destination_address=destination_address,
        destination_lat=destination_lat,
        destination_lng=destination_lng,
        notes=notes,
    )

    if patient is not None:
        trip.patient = patient

    if admission is not None:
        trip.admission = admission

    db.session.add(trip)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="AmbulanceTrip",
        entity_id=trip.id,
        description=(
            f"Ambulance trip {trip.id} requested"
        ),
        new_value={
            "clinic_id": clinic_id,
            "trip_type": trip_type.value,
            "patient_id": (
                patient.id
                if patient is not None
                else None
            ),
            "admission_id": (
                admission.id
                if admission is not None
                else None
            ),
            "status": trip.status.value,
        },
        user_id=_audit_user_id(),
    )

    return trip


# ============================================================
# DISPATCH TRIP
# ============================================================


@transactional
def dispatch_trip(
    trip_id: int,
    vehicle_id: int,
    driver_id: int,
    paramedic_id: int | None = None,
) -> AmbulanceTrip:
    """
    Dispatch a requested trip.

    REQUESTED -> DISPATCHED

    The vehicle is locked to prevent concurrent dispatches.
    """

    trip = get_trip(
        trip_id,
    )

    ensure_clinic_active(
        trip.clinic_id,
    )

    _assert_status(
        trip,
        TripStatus.REQUESTED,
    )

    # --------------------------------------------------------
    # Lock vehicle
    # --------------------------------------------------------

    vehicle = _lock_vehicle(
        vehicle_id,
    )

    if vehicle.clinic_id != trip.clinic_id:
        raise ValidationError(
            "Vehicle does not belong "
            "to the trip clinic"
        )

    if vehicle.status != VehicleStatus.AVAILABLE:
        raise ConflictError(
            f"Vehicle {vehicle.id} is currently "
            f"'{vehicle.status.value}' and is not available"
        )

    # --------------------------------------------------------
    # Driver
    # --------------------------------------------------------

    driver = _get_ambulance_crew_member(
        staff_id=driver_id,
        clinic_id=trip.clinic_id,
        allowed_roles=(
            Role.DRIVER,
        ),
        position="driver",
    )

    # --------------------------------------------------------
    # Paramedic / EMT
    # --------------------------------------------------------

    paramedic = None

    if paramedic_id is not None:
        paramedic = _get_ambulance_crew_member(
            staff_id=paramedic_id,
            clinic_id=trip.clinic_id,
            allowed_roles=(
                Role.PARAMEDIC,
                Role.EMT,
            ),
            position="paramedic",
        )

    # --------------------------------------------------------
    # Prevent same crew member
    # --------------------------------------------------------

    if (
        paramedic is not None
        and paramedic.id == driver.id
    ):
        raise ValidationError(
            "Driver and paramedic must be "
            "different staff members"
        )

    # --------------------------------------------------------
    # Assign relationships
    # --------------------------------------------------------

    try:
        trip.vehicle = vehicle
        trip.driver = driver
        trip.paramedic = paramedic

    except ValueError as exc:
        raise ValidationError(
            str(exc)
        ) from exc

    # --------------------------------------------------------
    # Update lifecycle
    # --------------------------------------------------------

    old_status = trip.status.value

    vehicle.status = VehicleStatus.ON_TRIP

    trip.status = TripStatus.DISPATCHED
    trip.dispatched_at = db.func.now()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="AmbulanceTrip",
        entity_id=trip.id,
        description=(
            f"Ambulance trip {trip.id} dispatched "
            f"with vehicle {vehicle.id}"
        ),
        old_value={
            "status": old_status,
        },
        new_value={
            "status": trip.status.value,
            "vehicle_id": vehicle.id,
            "driver_id": driver.id,
            "paramedic_id": (
                paramedic.id
                if paramedic is not None
                else None
            ),
        },
        user_id=_audit_user_id(),
    )

    return trip


# ============================================================
# UPDATE TRIP STATUS
# ============================================================


@transactional
def update_trip_status(
    trip_id: int,
    new_status: TripStatus,
) -> AmbulanceTrip:
    """
    Advance the operational ambulance lifecycle.

    DISPATCHED
        -> EN_ROUTE_TO_PICKUP

    EN_ROUTE_TO_PICKUP
        -> AT_PICKUP

    AT_PICKUP
        -> PATIENT_ON_BOARD

    PATIENT_ON_BOARD
        -> EN_ROUTE_TO_DESTINATION
    """

    trip = get_trip(
        trip_id,
    )

    ensure_clinic_active(
        trip.clinic_id,
    )

    valid_transitions = {
        TripStatus.DISPATCHED: (
            TripStatus.EN_ROUTE_TO_PICKUP,
        ),
        TripStatus.EN_ROUTE_TO_PICKUP: (
            TripStatus.AT_PICKUP,
        ),
        TripStatus.AT_PICKUP: (
            TripStatus.PATIENT_ON_BOARD,
        ),
        TripStatus.PATIENT_ON_BOARD: (
            TripStatus.EN_ROUTE_TO_DESTINATION,
        ),
    }

    allowed = valid_transitions.get(
        trip.status,
        (),
    )

    if new_status not in allowed:
        raise ConflictError(
            f"Trip {trip.id} cannot move "
            f"from '{trip.status.value}' "
            f"to '{new_status.value}'"
        )

    if new_status == TripStatus.PATIENT_ON_BOARD:
        if trip.patient_id is None:
            raise ValidationError(
                "Cannot mark a trip as "
                "PATIENT_ON_BOARD without a patient"
            )

        _get_patient(
            patient_id=trip.patient_id,
            clinic_id=trip.clinic_id,
        )

    old_status = trip.status.value

    trip.status = new_status

    if new_status == TripStatus.AT_PICKUP:
        trip.pickup_at = db.func.now()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="AmbulanceTrip",
        entity_id=trip.id,
        description=(
            f"Ambulance trip {trip.id} "
            f"status changed to "
            f"'{new_status.value}'"
        ),
        old_value={
            "status": old_status,
        },
        new_value={
            "status": new_status.value,
        },
        user_id=_audit_user_id(),
    )

    return trip


# ============================================================
# LINK PATIENT
# ============================================================


@transactional
def link_patient(
    trip_id: int,
    patient_id: int,
) -> AmbulanceTrip:
    """
    Link a patient to an ambulance trip.

    This is allowed while the trip is operational but not
    after completion/cancellation.
    """

    trip = get_trip(
        trip_id,
    )

    ensure_clinic_active(
        trip.clinic_id,
    )

    if trip.status in {
        TripStatus.COMPLETED,
        TripStatus.CANCELLED,
    }:
        raise ConflictError(
            "Cannot link a patient to a "
            "completed or cancelled trip"
        )

    patient = _get_patient(
        patient_id=patient_id,
        clinic_id=trip.clinic_id,
    )

    if (
        trip.patient_id is not None
        and trip.patient_id != patient.id
    ):
        raise ConflictError(
            f"Trip {trip_id} is already linked "
            f"to patient {trip.patient_id}"
        )

    if (
        trip.admission is not None
        and trip.admission.patient_id != patient.id
    ):
        raise ValidationError(
            "Patient does not match "
            "the trip admission"
        )

    if trip.patient_id == patient.id:
        return trip

    trip.patient = patient

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="AmbulanceTrip",
        entity_id=trip.id,
        description=(
            f"Patient {patient.id} linked "
            f"to ambulance trip {trip.id}"
        ),
        new_value={
            "patient_id": patient.id,
        },
        user_id=_audit_user_id(),
    )

    return trip


# ============================================================
# COMPLETE TRIP
# ============================================================


@transactional
def complete_trip(
    trip_id: int,
) -> AmbulanceTrip:
    """
    Complete an ambulance trip.

    EN_ROUTE_TO_DESTINATION -> COMPLETED

    The vehicle is released back to AVAILABLE.

    Billing is intentionally NOT created here.
    """

    trip = get_trip(
        trip_id,
    )

    ensure_clinic_active(
        trip.clinic_id,
    )

    _assert_status(
        trip,
        TripStatus.EN_ROUTE_TO_DESTINATION,
    )

    if trip.patient_id is None:
        raise ValidationError(
            "Cannot complete an ambulance trip "
            "without a patient"
        )

    _get_patient(
        patient_id=trip.patient_id,
        clinic_id=trip.clinic_id,
    )

    vehicle = None

    if trip.vehicle_id is not None:
        vehicle = _lock_vehicle(
            trip.vehicle_id,
        )

        if vehicle.clinic_id != trip.clinic_id:
            raise ValidationError(
                "Trip vehicle does not belong "
                "to the trip clinic"
            )

        if vehicle.status != VehicleStatus.ON_TRIP:
            raise ConflictError(
                f"Vehicle {vehicle.id} is not "
                "currently marked ON_TRIP"
            )

    old_status = trip.status.value

    trip.status = TripStatus.COMPLETED
    trip.completed_at = db.func.now()

    if vehicle is not None:
        vehicle.status = VehicleStatus.AVAILABLE

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="AmbulanceTrip",
        entity_id=trip.id,
        description=(
            f"Ambulance trip {trip.id} completed; "
            f"vehicle released"
        ),
        old_value={
            "status": old_status,
        },
        new_value={
            "status": trip.status.value,
            "vehicle_id": (
                vehicle.id
                if vehicle is not None
                else None
            ),
        },
        user_id=_audit_user_id(),
    )

    return trip


# ============================================================
# LINK INVOICE
# ============================================================


@transactional
def link_invoice(
    trip_id: int,
    invoice_id: int,
) -> AmbulanceTrip:
    """
    Attach an existing invoice to a completed ambulance trip.

    Invoice creation remains the responsibility of the
    billing service.
    """

    trip = get_trip(
        trip_id,
    )

    ensure_clinic_active(
        trip.clinic_id,
    )

    if trip.status != TripStatus.COMPLETED:
        raise ConflictError(
            "Can only attach an invoice "
            "to a completed ambulance trip"
        )

    if trip.invoice_id is not None:
        raise ConflictError(
            f"Trip {trip_id} is already linked "
            f"to invoice {trip.invoice_id}"
        )

    if trip.patient_id is None:
        raise ValidationError(
            "Cannot link an invoice to a trip "
            "without a patient"
        )

    invoice = db.session.get(
        Invoice,
        invoice_id,
    )

    if invoice is None:
        raise NotFoundError(
            f"Invoice {invoice_id} not found"
        )

    if invoice.clinic_id != trip.clinic_id:
        raise ValidationError(
            "Invoice does not belong "
            "to the trip clinic"
        )

    if invoice.patient_id != trip.patient_id:
        raise ValidationError(
            "Invoice does not belong "
            "to the trip patient"
        )

    if invoice.ambulance_trip is not None:
        raise ConflictError(
            f"Invoice {invoice_id} is already "
            f"linked to ambulance trip "
            f"{invoice.ambulance_trip.id}"
        )

    trip.invoice = invoice

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="AmbulanceTrip",
        entity_id=trip.id,
        description=(
            f"Invoice {invoice.id} linked "
            f"to ambulance trip {trip.id}"
        ),
        new_value={
            "invoice_id": invoice.id,
        },
        user_id=_audit_user_id(),
    )

    return trip


# ============================================================
# CANCEL TRIP
# ============================================================


@transactional
def cancel_trip(
    trip_id: int,
    reason: str,
) -> AmbulanceTrip:
    """
    Cancel an ambulance trip.

    Completed trips cannot be cancelled.

    If a vehicle has already been dispatched and is ON_TRIP,
    it is released back to AVAILABLE.
    """

    trip = get_trip(
        trip_id,
    )

    ensure_clinic_active(
        trip.clinic_id,
    )

    if trip.status == TripStatus.COMPLETED:
        raise ConflictError(
            "Cannot cancel a completed trip"
        )

    if trip.status == TripStatus.CANCELLED:
        raise ConflictError(
            "Trip is already cancelled"
        )

    if not reason or not reason.strip():
        raise ValidationError(
            "Cancellation reason is required"
        )

    vehicle = None

    if trip.vehicle_id is not None:
        vehicle = _lock_vehicle(
            trip.vehicle_id,
        )

        if vehicle.clinic_id != trip.clinic_id:
            raise ValidationError(
                "Trip vehicle does not belong "
                "to the trip clinic"
            )

    old_status = trip.status.value

    trip.status = TripStatus.CANCELLED
    trip.cancelled_at = db.func.now()
    trip.cancellation_reason = reason.strip()

    if (
        vehicle is not None
        and vehicle.status == VehicleStatus.ON_TRIP
    ):
        vehicle.status = VehicleStatus.AVAILABLE

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="AmbulanceTrip",
        entity_id=trip.id,
        description=(
            f"Ambulance trip {trip.id} cancelled: "
            f"{trip.cancellation_reason}"
        ),
        old_value={
            "status": old_status,
        },
        new_value={
            "status": trip.status.value,
            "reason": trip.cancellation_reason,
        },
        user_id=_audit_user_id(),
    )

    return trip