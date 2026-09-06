from flask import (
    Blueprint,
    g,
    jsonify,
    request,
)

from pydantic import ValidationError as PydanticValidationError

from app.core.auth.user.models.user_model import User

from app.core.enums.ambulance_enums import (
    TripStatus,
)

from app.core.enums.role_enums import Role

from app.core.exceptions import (
    DomainError,
    ValidationError,
)

from app.core.utils.decorators import (
    role_required,
)

from app.modules.ambulance.schemas.ambulance_trip_schema import (
    AmbulanceTripCancelSchema,
    AmbulanceTripDispatchSchema,
    AmbulanceTripInvoiceSchema,
    AmbulanceTripPatientSchema,
    AmbulanceTripRequestSchema,
    AmbulanceTripStatusSchema,
)

from app.modules.ambulance.services.ambulance_service import (
    cancel_trip,
    complete_trip,
    dispatch_trip,
    get_trip,
    link_invoice,
    link_patient,
    list_trips,
    request_trip,
    update_trip_status,
)


# ============================================================
# BLUEPRINT
# ============================================================


trip_bp = Blueprint(
    "ambulance_trips",
    __name__,
    url_prefix="/api/ambulance/trips",
)


# ============================================================
# ROLE GROUPS
# ============================================================


TRIP_MANAGEMENT_ROLES = (
    Role.ADMIN,
    Role.AMBULANCE_COORDINATOR,
    Role.AMBULANCE_DISPATCHER,
)


TRIP_VIEW_ROLES = (
    Role.ADMIN,
    Role.AMBULANCE_COORDINATOR,
    Role.AMBULANCE_DISPATCHER,
    Role.DRIVER,
    Role.PARAMEDIC,
    Role.EMT,
)


TRIP_CREW_ROLES = (
    Role.ADMIN,
    Role.AMBULANCE_COORDINATOR,
    Role.AMBULANCE_DISPATCHER,
    Role.DRIVER,
    Role.PARAMEDIC,
    Role.EMT,
)


# ============================================================
# HELPERS
# ============================================================


def _payload(schema):
    """
    Validate a JSON request body using the supplied Pydantic
    schema.

    Returns either the validated model or an HTTP error
    response.
    """
    try:
        return schema.model_validate(
            request.get_json(silent=True) or {}
        )

    except PydanticValidationError as exc:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Invalid request payload",
                    "details": exc.errors(),
                }
            ),
            422,
        )


def _current_user() -> User:
    """
    Return the authenticated user.

    role_required() has already verified the JWT and populated
    g.current_user_id.
    """
    user = User.query.get(
        g.current_user_id,
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
    Return the authenticated user's clinic.

    The client must never be allowed to choose the clinic
    for ambulance API operations.
    """
    user = _current_user()

    if user.clinic_id is None:
        raise ValidationError(
            "Authenticated user is not associated "
            "with a clinic"
        )

    return user.clinic_id


def _trip_data(trip):
    """
    Serialize an ambulance trip for API responses.
    """
    return {
        "id": trip.id,
        "clinic_id": trip.clinic_id,
        "vehicle_id": trip.vehicle_id,
        "patient_id": trip.patient_id,
        "driver_id": trip.driver_id,
        "paramedic_id": trip.paramedic_id,
        "admission_id": trip.admission_id,
        "trip_type": (
            trip.trip_type.value
            if trip.trip_type is not None
            else None
        ),
        "status": (
            trip.status.value
            if trip.status is not None
            else None
        ),
        "pickup_address": trip.pickup_address,
        "pickup_lat": (
            float(trip.pickup_lat)
            if trip.pickup_lat is not None
            else None
        ),
        "pickup_lng": (
            float(trip.pickup_lng)
            if trip.pickup_lng is not None
            else None
        ),
        "destination_address": trip.destination_address,
        "destination_lat": (
            float(trip.destination_lat)
            if trip.destination_lat is not None
            else None
        ),
        "destination_lng": (
            float(trip.destination_lng)
            if trip.destination_lng is not None
            else None
        ),
        "requested_at": (
            trip.requested_at.isoformat()
            if trip.requested_at is not None
            else None
        ),
        "dispatched_at": (
            trip.dispatched_at.isoformat()
            if trip.dispatched_at is not None
            else None
        ),
        "pickup_at": (
            trip.pickup_at.isoformat()
            if trip.pickup_at is not None
            else None
        ),
        "completed_at": (
            trip.completed_at.isoformat()
            if trip.completed_at is not None
            else None
        ),
        "cancelled_at": (
            trip.cancelled_at.isoformat()
            if trip.cancelled_at is not None
            else None
        ),
        "cancellation_reason": trip.cancellation_reason,
        "notes": trip.notes,
        "invoice_id": trip.invoice_id,
    }


# ============================================================
# CREATE TRIP
# ============================================================


@trip_bp.post("")
@role_required(*TRIP_MANAGEMENT_ROLES)
def create_ambulance_trip():
    payload = _payload(
        AmbulanceTripRequestSchema,
    )

    if isinstance(payload, tuple):
        return payload

    try:
        clinic_id = _current_clinic_id()

        data = payload.model_dump()

        # Never trust clinic_id from the client.
        data.pop(
            "clinic_id",
            None,
        )

        trip = request_trip(
            clinic_id=clinic_id,
            **data,
        )

        return jsonify(
            {
                "success": True,
                "data": _trip_data(trip),
            }
        ), 201

    except DomainError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), exc.status_code


# ============================================================
# LIST TRIPS
# ============================================================


@trip_bp.get("")
@role_required(*TRIP_VIEW_ROLES)
def get_ambulance_trips():
    try:
        clinic_id = _current_clinic_id()

        status_value = request.args.get(
            "status",
        )

        status = None

        if status_value:
            try:
                status = TripStatus(
                    status_value,
                )
            except ValueError:
                raise ValidationError(
                    f"Invalid trip status: "
                    f"{status_value}"
                )

        trips = list_trips(
            clinic_id=clinic_id,
            status=status,
        )

        return jsonify(
            {
                "success": True,
                "data": [
                    _trip_data(trip)
                    for trip in trips
                ],
            }
        ), 200

    except DomainError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), exc.status_code


# ============================================================
# GET TRIP
# ============================================================


@trip_bp.get("/<int:trip_id>")
@role_required(*TRIP_VIEW_ROLES)
def get_ambulance_trip(
    trip_id: int,
):
    try:
        trip = get_trip(
            trip_id,
        )

        return jsonify(
            {
                "success": True,
                "data": _trip_data(trip),
            }
        ), 200

    except DomainError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), exc.status_code


# ============================================================
# DISPATCH TRIP
# ============================================================


@trip_bp.post("/<int:trip_id>/dispatch")
@role_required(*TRIP_MANAGEMENT_ROLES)
def dispatch_ambulance_trip(
    trip_id: int,
):
    payload = _payload(
        AmbulanceTripDispatchSchema,
    )

    if isinstance(payload, tuple):
        return payload

    try:
        trip = dispatch_trip(
            trip_id=trip_id,
            **payload.model_dump(),
        )

        return jsonify(
            {
                "success": True,
                "data": _trip_data(trip),
            }
        ), 200

    except DomainError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), exc.status_code


# ============================================================
# UPDATE TRIP STATUS
# ============================================================


@trip_bp.patch("/<int:trip_id>/status")
@role_required(*TRIP_CREW_ROLES)
def update_ambulance_trip_status(
    trip_id: int,
):
    payload = _payload(
        AmbulanceTripStatusSchema,
    )

    if isinstance(payload, tuple):
        return payload

    try:
        trip = update_trip_status(
            trip_id=trip_id,
            new_status=payload.status,
        )

        return jsonify(
            {
                "success": True,
                "data": _trip_data(trip),
            }
        ), 200

    except DomainError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), exc.status_code


# ============================================================
# LINK PATIENT
# ============================================================


@trip_bp.post("/<int:trip_id>/patient")
@role_required(*TRIP_MANAGEMENT_ROLES)
def link_ambulance_patient(
    trip_id: int,
):
    payload = _payload(
        AmbulanceTripPatientSchema,
    )

    if isinstance(payload, tuple):
        return payload

    try:
        trip = link_patient(
            trip_id=trip_id,
            patient_id=payload.patient_id,
        )

        return jsonify(
            {
                "success": True,
                "data": _trip_data(trip),
            }
        ), 200

    except DomainError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), exc.status_code


# ============================================================
# COMPLETE TRIP
# ============================================================


@trip_bp.post("/<int:trip_id>/complete")
@role_required(*TRIP_CREW_ROLES)
def complete_ambulance_trip(
    trip_id: int,
):
    try:
        trip = complete_trip(
            trip_id,
        )

        return jsonify(
            {
                "success": True,
                "data": _trip_data(trip),
            }
        ), 200

    except DomainError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), exc.status_code


# ============================================================
# LINK INVOICE
# ============================================================


@trip_bp.post("/<int:trip_id>/invoice")
@role_required(*TRIP_MANAGEMENT_ROLES)
def link_ambulance_invoice(
    trip_id: int,
):
    payload = _payload(
        AmbulanceTripInvoiceSchema,
    )

    if isinstance(payload, tuple):
        return payload

    try:
        trip = link_invoice(
            trip_id=trip_id,
            invoice_id=payload.invoice_id,
        )

        return jsonify(
            {
                "success": True,
                "data": _trip_data(trip),
            }
        ), 200

    except DomainError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), exc.status_code


# ============================================================
# CANCEL TRIP
# ============================================================


@trip_bp.post("/<int:trip_id>/cancel")
@role_required(*TRIP_MANAGEMENT_ROLES)
def cancel_ambulance_trip(
    trip_id: int,
):
    payload = _payload(
        AmbulanceTripCancelSchema,
    )

    if isinstance(payload, tuple):
        return payload

    try:
        trip = cancel_trip(
            trip_id=trip_id,
            reason=payload.reason,
        )

        return jsonify(
            {
                "success": True,
                "data": _trip_data(trip),
            }
        ), 200

    except DomainError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), exc.status_code