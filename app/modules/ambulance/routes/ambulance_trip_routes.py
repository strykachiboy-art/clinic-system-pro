from flask import (
    Blueprint,
    jsonify,
    request,
)

from pydantic import ValidationError as PydanticValidationError

from app.core.enums.ambulance_enums import (
    TripStatus,
)

from app.core.enums.role_enums import Role

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


trip_bp = Blueprint(
    "ambulance_trips",
    __name__,
    url_prefix="/api/ambulance/trips",
)


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


def _payload(schema):
    try:
        return schema.model_validate(
            request.get_json(silent=True) or {}
        )

    except PydanticValidationError as exc:
        return (
            jsonify(
                {
                    "success": False,
                    "error": exc.errors(),
                }
            ),
            422,
        )


def _trip_data(trip):
    return {
        "id": trip.id,
        "clinic_id": trip.clinic_id,

        "vehicle_id": trip.vehicle_id,

        "patient_id": trip.patient_id,

        "driver_id": trip.driver_id,

        "paramedic_id": trip.paramedic_id,

        "admission_id": trip.admission_id,

        "trip_type": trip.trip_type.value,

        "status": trip.status.value,

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

        "destination_address": (
            trip.destination_address
        ),

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

        "created_at": (
            trip.created_at.isoformat()
            if trip.created_at
            else None
        ),

        "updated_at": (
            trip.updated_at.isoformat()
            if trip.updated_at
            else None
        ),

        "requested_at": (
            trip.requested_at.isoformat()
            if trip.requested_at
            else None
        ),

        "dispatched_at": (
            trip.dispatched_at.isoformat()
            if trip.dispatched_at
            else None
        ),

        "pickup_at": (
            trip.pickup_at.isoformat()
            if trip.pickup_at
            else None
        ),

        "completed_at": (
            trip.completed_at.isoformat()
            if trip.completed_at
            else None
        ),

        "cancelled_at": (
            trip.cancelled_at.isoformat()
            if trip.cancelled_at
            else None
        ),

        "cancellation_reason": (
            trip.cancellation_reason
        ),

        "notes": trip.notes,

        "invoice_id": trip.invoice_id,
    }


# ============================================================
# REQUEST TRIP
# ============================================================


@trip_bp.post("")
@role_required(*TRIP_MANAGEMENT_ROLES)
def create_ambulance_trip():

    payload = _payload(
        AmbulanceTripRequestSchema,
    )

    if isinstance(payload, tuple):
        return payload

    trip = request_trip(
        **payload.model_dump(),
    )

    return (
        jsonify(
            {
                "success": True,
                "data": _trip_data(trip),
            }
        ),
        201,
    )


# ============================================================
# LIST TRIPS
# ============================================================


@trip_bp.get("")
@role_required(*TRIP_VIEW_ROLES)
def get_ambulance_trips():

    clinic_id = request.args.get(
        "clinic_id",
        type=int,
    )

    if clinic_id is None:
        return (
            jsonify(
                {
                    "success": False,
                    "error": (
                        "clinic_id query parameter "
                        "is required"
                    ),
                }
            ),
            400,
        )

    status_value = request.args.get(
        "status",
    )

    status = None

    if status_value is not None:
        try:
            status = TripStatus(
                status_value,
            )

        except ValueError:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": (
                            f"Invalid trip status: "
                            f"{status_value}"
                        ),
                    }
                ),
                422,
            )

    trips = list_trips(
        clinic_id=clinic_id,
        status=status,
    )

    return (
        jsonify(
            {
                "success": True,
                "data": [
                    _trip_data(trip)
                    for trip in trips
                ],
            }
        ),
        200,
    )


# ============================================================
# GET TRIP
# ============================================================


@trip_bp.get("/<int:trip_id>")
@role_required(*TRIP_VIEW_ROLES)
def get_ambulance_trip(
    trip_id,
):

    trip = get_trip(
        trip_id,
    )

    return (
        jsonify(
            {
                "success": True,
                "data": _trip_data(trip),
            }
        ),
        200,
    )


# ============================================================
# DISPATCH
# ============================================================


@trip_bp.post(
    "/<int:trip_id>/dispatch"
)
@role_required(*TRIP_MANAGEMENT_ROLES)
def dispatch_ambulance_trip(
    trip_id,
):

    payload = _payload(
        AmbulanceTripDispatchSchema,
    )

    if isinstance(payload, tuple):
        return payload

    trip = dispatch_trip(
        trip_id=trip_id,
        **payload.model_dump(),
    )

    return (
        jsonify(
            {
                "success": True,
                "data": _trip_data(trip),
            }
        ),
        200,
    )


# ============================================================
# ADVANCE STATUS
# ============================================================


@trip_bp.patch(
    "/<int:trip_id>/status"
)
@role_required(*TRIP_CREW_ROLES)
def update_ambulance_trip_status(
    trip_id,
):

    payload = _payload(
        AmbulanceTripStatusSchema,
    )

    if isinstance(payload, tuple):
        return payload

    trip = update_trip_status(
        trip_id=trip_id,
        new_status=payload.status,
    )

    return (
        jsonify(
            {
                "success": True,
                "data": _trip_data(trip),
            }
        ),
        200,
    )


# ============================================================
# LINK PATIENT
# ============================================================


@trip_bp.post(
    "/<int:trip_id>/patient"
)
@role_required(*TRIP_MANAGEMENT_ROLES)
def link_ambulance_trip_patient(
    trip_id,
):

    payload = _payload(
        AmbulanceTripPatientSchema,
    )

    if isinstance(payload, tuple):
        return payload

    trip = link_patient(
        trip_id=trip_id,
        patient_id=payload.patient_id,
    )

    return (
        jsonify(
            {
                "success": True,
                "data": _trip_data(trip),
            }
        ),
        200,
    )


# ============================================================
# COMPLETE
# ============================================================


@trip_bp.post(
    "/<int:trip_id>/complete"
)
@role_required(*TRIP_CREW_ROLES)
def complete_ambulance_trip(
    trip_id,
):

    trip = complete_trip(
        trip_id,
    )

    return (
        jsonify(
            {
                "success": True,
                "data": _trip_data(trip),
            }
        ),
        200,
    )


# ============================================================
# LINK INVOICE
# ============================================================


@trip_bp.post(
    "/<int:trip_id>/invoice"
)
@role_required(*TRIP_MANAGEMENT_ROLES)
def link_ambulance_trip_invoice(
    trip_id,
):

    payload = _payload(
        AmbulanceTripInvoiceSchema,
    )

    if isinstance(payload, tuple):
        return payload

    trip = link_invoice(
        trip_id=trip_id,
        invoice_id=payload.invoice_id,
    )

    return (
        jsonify(
            {
                "success": True,
                "data": _trip_data(trip),
            }
        ),
        200,
    )


# ============================================================
# CANCEL
# ============================================================


@trip_bp.post(
    "/<int:trip_id>/cancel"
)
@role_required(*TRIP_MANAGEMENT_ROLES)
def cancel_ambulance_trip(
    trip_id,
):

    payload = _payload(
        AmbulanceTripCancelSchema,
    )

    if isinstance(payload, tuple):
        return payload

    trip = cancel_trip(
        trip_id=trip_id,
        reason=payload.reason,
    )

    return (
        jsonify(
            {
                "success": True,
                "data": _trip_data(trip),
            }
        ),
        200,
    )