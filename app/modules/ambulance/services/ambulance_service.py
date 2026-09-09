from flask import g, has_request_context
from sqlalchemy.exc import IntegrityError

from app.extensions import db

from app.core.auth.user.models.user_model import User

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

from app.core.utils.decorators import transactional

from app.core.audit.services.audit_service import create_audit_log

from app.core.enums.audit_enums import AuditAction

from app.core.enums.ambulance_enums import (
    TripStatus,
    TripType,
    VehicleStatus,
)

from app.core.enums.role_enums import Role

from app.core.enums.staff_enums import StaffStatus

from app.modules.clinic.services.clinic_service import ensure_clinic_active

from app.modules.patient.models.patient_model import Patient

from app.modules.staff.models.staff_model import Staff

from app.modules.billing.models.billing_model import Invoice

from app.modules.ward.models.ward_model import Admission

from app.modules.ambulance.models.ambulance_model import (
    AmbulanceTrip,
    AmbulanceVehicle,
)


DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 500
MAX_PLATE_NUMBER_LENGTH = 30
MAX_CANCELLATION_REASON_LENGTH = 255


def _validate_positive_id(value, field_name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ValidationError(
            f"{field_name} must be a positive integer"
        )


def _validate_pagination(page: int, per_page: int) -> None:
    if (
        isinstance(page, bool)
        or not isinstance(page, int)
        or page <= 0
    ):
        raise ValidationError(
            "Page must be a positive integer"
        )

    if (
        isinstance(per_page, bool)
        or not isinstance(per_page, int)
        or per_page <= 0
    ):
        raise ValidationError(
            "Per page must be a positive integer"
        )

    if per_page > MAX_PER_PAGE:
        raise ValidationError(
            f"Per page cannot exceed {MAX_PER_PAGE}"
        )


def _normalize_enum(value, enum_class, field_name: str):
    if isinstance(value, enum_class):
        return value

    try:
        return enum_class(value)
    except (TypeError, ValueError):
        raise ValidationError(
            f"Invalid {field_name}"
        )


def _current_user() -> User:
    if not has_request_context():
        raise ValidationError(
            "Authenticated request context is required"
        )

    user_id = getattr(g, "current_user_id", None)

    if (
        isinstance(user_id, bool)
        or not isinstance(user_id, int)
        or user_id <= 0
    ):
        raise ValidationError(
            "Authenticated user is required"
        )

    user = db.session.get(User, user_id)

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
    user = _current_user()

    if user.clinic_id is None:
        raise ValidationError(
            "Authenticated user is not associated with a clinic"
        )

    _validate_positive_id(
        user.clinic_id,
        "Authenticated clinic ID",
    )

    return user.clinic_id


def _assert_authenticated_clinic(clinic_id: int) -> None:
    _validate_positive_id(clinic_id, "Clinic ID")

    if not has_request_context():
        return

    authenticated_clinic_id = _current_clinic_id()

    if authenticated_clinic_id != clinic_id:
        raise ValidationError(
            "Resource does not belong to the authenticated user's clinic"
        )


def _audit_user_id() -> int | None:
    if not has_request_context():
        return None

    user_id = getattr(g, "current_user_id", None)

    if (
        isinstance(user_id, bool)
        or not isinstance(user_id, int)
        or user_id <= 0
    ):
        return None

    return user_id


def get_vehicle(vehicle_id: int) -> AmbulanceVehicle:
    _validate_positive_id(vehicle_id, "Vehicle ID")

    vehicle = db.session.get(
        AmbulanceVehicle,
        vehicle_id,
    )

    if vehicle is None:
        raise NotFoundError(
            f"Ambulance vehicle {vehicle_id} not found"
        )

    _assert_authenticated_clinic(vehicle.clinic_id)

    return vehicle


def list_vehicles(
    clinic_id: int,
    status: VehicleStatus | None = None,
    page: int = DEFAULT_PAGE,
    per_page: int = DEFAULT_PER_PAGE,
):
    _assert_authenticated_clinic(clinic_id)
    _validate_pagination(page, per_page)

    if status is not None:
        status = _normalize_enum(
            status,
            VehicleStatus,
            "vehicle status",
        )

    query = AmbulanceVehicle.query.filter_by(
        clinic_id=clinic_id,
    )

    if status is not None:
        query = query.filter(
            AmbulanceVehicle.status == status
        )

    return (
        query
        .order_by(
            AmbulanceVehicle.plate_number.asc(),
            AmbulanceVehicle.id.asc(),
        )
        .paginate(
            page=page,
            per_page=per_page,
            error_out=False,
        )
    )


@transactional
def create_vehicle(
    clinic_id: int,
    plate_number: str,
    equipment_level,
    capacity: int = 1,
    status: VehicleStatus = VehicleStatus.AVAILABLE,
    last_service_date=None,
) -> AmbulanceVehicle:
    _assert_authenticated_clinic(clinic_id)
    ensure_clinic_active(clinic_id)

    if not isinstance(plate_number, str):
        raise ValidationError(
            "Plate number must be a string"
        )

    plate_number = plate_number.strip().upper()

    if not plate_number:
        raise ValidationError(
            "Plate number is required"
        )

    if len(plate_number) > MAX_PLATE_NUMBER_LENGTH:
        raise ValidationError(
            f"Plate number cannot exceed "
            f"{MAX_PLATE_NUMBER_LENGTH} characters"
        )

    if (
        isinstance(capacity, bool)
        or not isinstance(capacity, int)
        or capacity < 1
    ):
        raise ValidationError(
            "Vehicle capacity must be a positive integer"
        )

    status = _normalize_enum(
        status,
        VehicleStatus,
        "vehicle status",
    )

    if status != VehicleStatus.AVAILABLE:
        raise ValidationError(
            "A newly registered ambulance must start "
            "with AVAILABLE status"
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

    try:
        db.session.flush()
    except IntegrityError as exc:
        raise ConflictError(
            f"Ambulance vehicle with plate "
            f"{plate_number} already exists"
        ) from exc

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
    _validate_positive_id(vehicle_id, "Vehicle ID")

    new_status = _normalize_enum(
        new_status,
        VehicleStatus,
        "vehicle status",
    )

    vehicle = get_vehicle(vehicle_id)

    ensure_clinic_active(vehicle.clinic_id)

    if vehicle.status == new_status:
        return vehicle

    if new_status == VehicleStatus.ON_TRIP:
        raise ValidationError(
            "ON_TRIP is managed automatically by "
            "ambulance dispatch and cannot be set manually"
        )

    if vehicle.status == VehicleStatus.ON_TRIP:
        raise ConflictError(
            "Cannot manually change the status of an "
            "ambulance that is currently on a trip"
        )

    old_status = vehicle.status.value

    vehicle.status = new_status

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="AmbulanceVehicle",
        entity_id=vehicle.id,
        description=(
            f"Ambulance vehicle {vehicle.plate_number} "
            f"status changed from {old_status} "
            f"to {new_status.value}"
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


def get_trip(trip_id: int) -> AmbulanceTrip:
    _validate_positive_id(trip_id, "Trip ID")

    trip = db.session.get(
        AmbulanceTrip,
        trip_id,
    )

    if trip is None:
        raise NotFoundError(
            f"Ambulance trip {trip_id} not found"
        )

    _assert_authenticated_clinic(trip.clinic_id)

    return trip


def list_trips(
    clinic_id: int,
    status: TripStatus | None = None,
    page: int = DEFAULT_PAGE,
    per_page: int = DEFAULT_PER_PAGE,
):
    _assert_authenticated_clinic(clinic_id)
    _validate_pagination(page, per_page)

    if status is not None:
        status = _normalize_enum(
            status,
            TripStatus,
            "trip status",
        )

    query = AmbulanceTrip.query.filter_by(
        clinic_id=clinic_id,
    )

    if status is not None:
        query = query.filter(
            AmbulanceTrip.status == status
        )

    return (
        query
        .order_by(
            AmbulanceTrip.requested_at.desc(),
            AmbulanceTrip.id.desc(),
        )
        .paginate(
            page=page,
            per_page=per_page,
            error_out=False,
        )
    )


def _lock_trip(trip_id: int) -> AmbulanceTrip:
    _validate_positive_id(trip_id, "Trip ID")

    trip = (
        AmbulanceTrip.query
        .filter(AmbulanceTrip.id == trip_id)
        .with_for_update()
        .first()
    )

    if trip is None:
        raise NotFoundError(
            f"Ambulance trip {trip_id} not found"
        )

    _assert_authenticated_clinic(trip.clinic_id)

    return trip


def _assert_status(
    trip: AmbulanceTrip,
    *allowed_statuses: TripStatus,
):
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
    _validate_positive_id(
        patient_id,
        "Patient ID",
    )

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
            "Patient does not belong to the trip clinic"
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
    _validate_positive_id(
        admission_id,
        "Admission ID",
    )

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
            "Admission does not belong to the trip clinic"
        )

    return admission


def _get_ambulance_crew_member(
    staff_id: int,
    clinic_id: int,
    allowed_roles: tuple[Role, ...],
    position: str,
) -> Staff:
    _validate_positive_id(
        staff_id,
        f"{position.capitalize()} ID",
    )

    staff = db.session.get(
        Staff,
        staff_id,
    )

    if staff is None:
        raise NotFoundError(
            f"{position.capitalize()} {staff_id} not found"
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
            f"{position.capitalize()} must have one "
            f"of these roles: {allowed}"
        )

    return staff


def _lock_vehicle(vehicle_id: int) -> AmbulanceVehicle:
    _validate_positive_id(
        vehicle_id,
        "Vehicle ID",
    )

    vehicle = (
        AmbulanceVehicle.query
        .filter(AmbulanceVehicle.id == vehicle_id)
        .with_for_update()
        .first()
    )

    if vehicle is None:
        raise NotFoundError(
            f"Ambulance vehicle {vehicle_id} not found"
        )

    return vehicle


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
    _assert_authenticated_clinic(clinic_id)
    ensure_clinic_active(clinic_id)

    trip_type = _normalize_enum(
        trip_type,
        TripType,
        "trip type",
    )

    patient = None
    admission = None

    if patient_id is not None:
        patient = _get_patient(
            patient_id=patient_id,
            clinic_id=clinic_id,
        )

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


@transactional
def dispatch_trip(
    trip_id: int,
    vehicle_id: int,
    driver_id: int,
    paramedic_id: int | None = None,
) -> AmbulanceTrip:
    trip = _lock_trip(trip_id)

    ensure_clinic_active(trip.clinic_id)

    _assert_status(
        trip,
        TripStatus.REQUESTED,
    )

    vehicle = _lock_vehicle(vehicle_id)

    if vehicle.clinic_id != trip.clinic_id:
        raise ValidationError(
            "Vehicle does not belong to the trip clinic"
        )

    if vehicle.status != VehicleStatus.AVAILABLE:
        raise ConflictError(
            f"Vehicle {vehicle.id} is currently "
            f"'{vehicle.status.value}' and is not available"
        )

    driver = _get_ambulance_crew_member(
        staff_id=driver_id,
        clinic_id=trip.clinic_id,
        allowed_roles=(Role.DRIVER,),
        position="driver",
    )

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

    if (
        paramedic is not None
        and paramedic.id == driver.id
    ):
        raise ValidationError(
            "Driver and paramedic must be "
            "different staff members"
        )

    try:
        trip.vehicle = vehicle
        trip.driver = driver
        trip.paramedic = paramedic
    except ValueError as exc:
        raise ValidationError(
            str(exc)
        ) from exc

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


@transactional
def update_trip_status(
    trip_id: int,
    new_status: TripStatus,
) -> AmbulanceTrip:
    trip = _lock_trip(trip_id)

    ensure_clinic_active(trip.clinic_id)

    new_status = _normalize_enum(
        new_status,
        TripStatus,
        "trip status",
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
            f"Trip {trip.id} cannot move from "
            f"'{trip.status.value}' to "
            f"'{new_status.value}'"
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
            f"Ambulance trip {trip.id} status "
            f"changed to '{new_status.value}'"
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


@transactional
def link_patient(
    trip_id: int,
    patient_id: int,
) -> AmbulanceTrip:
    trip = _lock_trip(trip_id)

    ensure_clinic_active(trip.clinic_id)

    if trip.status in {
        TripStatus.COMPLETED,
        TripStatus.CANCELLED,
    }:
        raise ConflictError(
            "Cannot link a patient to a completed "
            "or cancelled trip"
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
            "Patient does not match the trip admission"
        )

    if trip.patient_id == patient.id:
        return trip

    trip.patient = patient

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="AmbulanceTrip",
        entity_id=trip.id,
        description=(
            f"Patient {patient.id} linked to "
            f"ambulance trip {trip.id}"
        ),
        new_value={
            "patient_id": patient.id,
        },
        user_id=_audit_user_id(),
    )

    return trip


@transactional
def complete_trip(
    trip_id: int,
) -> AmbulanceTrip:
    trip = _lock_trip(trip_id)

    ensure_clinic_active(trip.clinic_id)

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
        vehicle = _lock_vehicle(trip.vehicle_id)

        if vehicle.clinic_id != trip.clinic_id:
            raise ValidationError(
                "Trip vehicle does not belong "
                "to the trip clinic"
            )

        if vehicle.status != VehicleStatus.ON_TRIP:
            raise ConflictError(
                f"Vehicle {vehicle.id} is not currently "
                "marked ON_TRIP"
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
            "vehicle released"
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


@transactional
def link_invoice(
    trip_id: int,
    invoice_id: int,
) -> AmbulanceTrip:
    trip = _lock_trip(trip_id)

    ensure_clinic_active(trip.clinic_id)

    _validate_positive_id(
        invoice_id,
        "Invoice ID",
    )

    if trip.status != TripStatus.COMPLETED:
        raise ConflictError(
            "Can only attach an invoice to "
            "a completed ambulance trip"
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
            f"Invoice {invoice_id} is already linked "
            f"to ambulance trip "
            f"{invoice.ambulance_trip.id}"
        )

    trip.invoice = invoice

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="AmbulanceTrip",
        entity_id=trip.id,
        description=(
            f"Invoice {invoice.id} linked to "
            f"ambulance trip {trip.id}"
        ),
        new_value={
            "invoice_id": invoice.id,
        },
        user_id=_audit_user_id(),
    )

    return trip


@transactional
def cancel_trip(
    trip_id: int,
    reason: str,
) -> AmbulanceTrip:
    trip = _lock_trip(trip_id)

    ensure_clinic_active(trip.clinic_id)

    if trip.status == TripStatus.COMPLETED:
        raise ConflictError(
            "Cannot cancel a completed trip"
        )

    if trip.status == TripStatus.CANCELLED:
        raise ConflictError(
            "Trip is already cancelled"
        )

    if not isinstance(reason, str):
        raise ValidationError(
            "Cancellation reason must be a string"
        )

    reason = reason.strip()

    if not reason:
        raise ValidationError(
            "Cancellation reason is required"
        )

    if len(reason) > MAX_CANCELLATION_REASON_LENGTH:
        raise ValidationError(
            "Cancellation reason cannot exceed "
            f"{MAX_CANCELLATION_REASON_LENGTH} characters"
        )

    vehicle = None

    if trip.vehicle_id is not None:
        vehicle = _lock_vehicle(trip.vehicle_id)

        if vehicle.clinic_id != trip.clinic_id:
            raise ValidationError(
                "Trip vehicle does not belong "
                "to the trip clinic"
            )

    old_status = trip.status.value

    trip.status = TripStatus.CANCELLED
    trip.cancelled_at = db.func.now()
    trip.cancellation_reason = reason

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