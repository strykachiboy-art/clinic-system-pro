from flask import (
    Blueprint,
    jsonify,
    request,
)

from pydantic import ValidationError as PydanticValidationError

from app.core.enums.ambulance_enums import (
    VehicleStatus,
)

from app.core.enums.role_enums import Role

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


vehicle_bp = Blueprint(
    "ambulance_vehicles",
    __name__,
    url_prefix="/api/ambulance/vehicles",
)


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


def _vehicle_data(vehicle):
    return {
        "id": vehicle.id,
        "clinic_id": vehicle.clinic_id,
        "plate_number": vehicle.plate_number,
        "equipment_level": (
            vehicle.equipment_level.value
        ),
        "capacity": vehicle.capacity,
        "status": vehicle.status.value,
        "last_service_date": (
            vehicle.last_service_date.isoformat()
            if vehicle.last_service_date
            else None
        ),
        "created_at": (
            vehicle.created_at.isoformat()
            if vehicle.created_at
            else None
        ),
        "updated_at": (
            vehicle.updated_at.isoformat()
            if vehicle.updated_at
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

    data = payload.model_dump()

    clinic_id = data.pop(
        "clinic_id",
    )

    plate_number = data.pop(
        "plate_number",
    )

    vehicle = create_vehicle(
        clinic_id=clinic_id,
        plate_number=plate_number,
        **data,
    )

    return (
        jsonify(
            {
                "success": True,
                "data": _vehicle_data(vehicle),
            }
        ),
        201,
    )


# ============================================================
# LIST VEHICLES
# ============================================================


@vehicle_bp.get("")
@role_required(*VEHICLE_VIEW_ROLES)
def get_ambulance_vehicles():

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
            status = VehicleStatus(
                status_value,
            )

        except ValueError:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": (
                            f"Invalid vehicle status: "
                            f"{status_value}"
                        ),
                    }
                ),
                422,
            )

    vehicles = list_vehicles(
        clinic_id=clinic_id,
        status=status,
    )

    return (
        jsonify(
            {
                "success": True,
                "data": [
                    _vehicle_data(vehicle)
                    for vehicle in vehicles
                ],
            }
        ),
        200,
    )


# ============================================================
# GET VEHICLE
# ============================================================


@vehicle_bp.get("/<int:vehicle_id>")
@role_required(*VEHICLE_VIEW_ROLES)
def get_ambulance_vehicle(
    vehicle_id,
):

    vehicle = get_vehicle(
        vehicle_id,
    )

    return (
        jsonify(
            {
                "success": True,
                "data": _vehicle_data(vehicle),
            }
        ),
        200,
    )


# ============================================================
# UPDATE VEHICLE STATUS
# ============================================================


@vehicle_bp.patch(
    "/<int:vehicle_id>/status"
)
@role_required(*VEHICLE_MANAGEMENT_ROLES)
def update_ambulance_vehicle_status(
    vehicle_id,
):

    payload = _payload(
        AmbulanceVehicleStatusSchema,
    )

    if isinstance(payload, tuple):
        return payload

    vehicle = set_vehicle_status(
        vehicle_id=vehicle_id,
        new_status=payload.status,
    )

    return (
        jsonify(
            {
                "success": True,
                "data": _vehicle_data(vehicle),
            }
        ),
        200,
    )