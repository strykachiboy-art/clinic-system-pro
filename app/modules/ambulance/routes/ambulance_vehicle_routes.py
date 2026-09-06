from flask import (
    Blueprint,
    g,
    jsonify,
    request,
)

from pydantic import ValidationError as PydanticValidationError

from app.core.auth.user.models.user_model import User

from app.core.enums.ambulance_enums import (
    VehicleStatus,
)

from app.core.enums.role_enums import Role

from app.core.exceptions import (
    DomainError,
    ValidationError,
)

from app.core.utils.decorators import (
    role_required,
)

from app.modules.ambulance.schemas.ambulance_vehicle_schema import (
    AmbulanceVehicleCreateSchema,
    AmbulanceVehicleStatusSchema,
)

from app.modules.ambulance.services.ambulance_service import (
    create_vehicle,
    get_vehicle,
    list_vehicles,
    set_vehicle_status,
)


# ============================================================
# BLUEPRINT
# ============================================================


vehicle_bp = Blueprint(
    "ambulance_vehicles",
    __name__,
    url_prefix="/api/ambulance/vehicles",
)


# ============================================================
# ROLE GROUPS
# ============================================================


VEHICLE_MANAGEMENT_ROLES = (
    Role.ADMIN,
    Role.AMBULANCE_COORDINATOR,
)


VEHICLE_VIEW_ROLES = (
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
    """
    user = _current_user()

    if user.clinic_id is None:
        raise ValidationError(
            "Authenticated user is not associated "
            "with a clinic"
        )

    return user.clinic_id


def _vehicle_data(vehicle):
    """
    Serialize an ambulance vehicle for API responses.
    """
    return {
        "id": vehicle.id,
        "clinic_id": vehicle.clinic_id,
        "plate_number": vehicle.plate_number,
        "equipment_level": (
            vehicle.equipment_level.value
            if vehicle.equipment_level is not None
            else None
        ),
        "capacity": vehicle.capacity,
        "status": (
            vehicle.status.value
            if vehicle.status is not None
            else None
        ),
        "last_service_date": (
            vehicle.last_service_date.isoformat()
            if vehicle.last_service_date is not None
            else None
        ),
        "created_at": (
            vehicle.created_at.isoformat()
            if vehicle.created_at is not None
            else None
        ),
        "updated_at": (
            vehicle.updated_at.isoformat()
            if vehicle.updated_at is not None
            else None
        ),
    }


# ============================================================
# CREATE VEHICLE
# ============================================================


@vehicle_bp.post("")
@role_required(*VEHICLE_MANAGEMENT_ROLES)
def create_ambulance_vehicle():
    payload = _payload(
        AmbulanceVehicleCreateSchema,
    )

    if isinstance(payload, tuple):
        return payload

    try:
        clinic_id = _current_clinic_id()

        data = payload.model_dump()

        # The client must not choose which clinic receives
        # the vehicle.
        data.pop(
            "clinic_id",
            None,
        )

        vehicle = create_vehicle(
            clinic_id=clinic_id,
            **data,
        )

        return jsonify(
            {
                "success": True,
                "data": _vehicle_data(vehicle),
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
# LIST VEHICLES
# ============================================================


@vehicle_bp.get("")
@role_required(*VEHICLE_VIEW_ROLES)
def get_ambulance_vehicles():
    try:
        clinic_id = _current_clinic_id()

        status_value = request.args.get(
            "status",
        )

        status = None

        if status_value:
            try:
                status = VehicleStatus(
                    status_value,
                )
            except ValueError:
                raise ValidationError(
                    f"Invalid vehicle status: "
                    f"{status_value}"
                )

        vehicles = list_vehicles(
            clinic_id=clinic_id,
            status=status,
        )

        return jsonify(
            {
                "success": True,
                "data": [
                    _vehicle_data(vehicle)
                    for vehicle in vehicles
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
# GET VEHICLE
# ============================================================


@vehicle_bp.get("/<int:vehicle_id>")
@role_required(*VEHICLE_VIEW_ROLES)
def get_ambulance_vehicle(
    vehicle_id: int,
):
    try:
        vehicle = get_vehicle(
            vehicle_id,
        )

        return jsonify(
            {
                "success": True,
                "data": _vehicle_data(vehicle),
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
# UPDATE VEHICLE STATUS
# ============================================================


@vehicle_bp.patch("/<int:vehicle_id>/status")
@role_required(*VEHICLE_MANAGEMENT_ROLES)
def update_ambulance_vehicle_status(
    vehicle_id: int,
):
    payload = _payload(
        AmbulanceVehicleStatusSchema,
    )

    if isinstance(payload, tuple):
        return payload

    try:
        vehicle = set_vehicle_status(
            vehicle_id=vehicle_id,
            new_status=payload.status,
        )

        return jsonify(
            {
                "success": True,
                "data": _vehicle_data(vehicle),
            }
        ), 200

    except DomainError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), exc.status_code