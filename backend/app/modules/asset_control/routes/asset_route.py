from __future__ import annotations

from flask import (
    Blueprint,
    jsonify,
    request,
)
from flask_jwt_extended import get_jwt_identity

from app.extensions import db

from app.core.auth.user.models.user_model import User
from app.core.enums.role_enums import Role
from app.core.exceptions import (
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import role_required

from app.modules.asset_control.schemas.asset_assignment_schema import (
    AssetAssignmentCreateSchema,
    AssetAssignmentListQuerySchema,
    AssetAssignmentResponseSchema,
    AssetAssignmentReturnSchema,
)
from app.modules.asset_control.schemas.asset_history_schema import (
    AssetHistoryListQuerySchema,
    AssetHistoryResponseSchema,
)
from app.modules.asset_control.schemas.asset_maintenance_schema import (
    AssetMaintenanceCancelSchema,
    AssetMaintenanceCompleteSchema,
    AssetMaintenanceListQuerySchema,
    AssetMaintenanceResponseSchema,
    AssetMaintenanceScheduleSchema,
    AssetMaintenanceStartSchema,
)
from app.modules.asset_control.schemas.asset_schema import (
    AssetCreateSchema,
    AssetDisposeSchema,
    AssetListQuerySchema,
    AssetResponseSchema,
    AssetRetireSchema,
    AssetUpdateSchema,
)
from app.modules.asset_control.services.asset_assignment_service import (
    assign_asset,
    get_asset_assignment,
    list_asset_assignments,
    return_asset,
)
from app.modules.asset_control.services.asset_history_service import (
    get_asset_history,
    list_asset_history,
)
from app.modules.asset_control.services.asset_maintenance_service import (
    cancel_maintenance,
    complete_maintenance,
    get_asset_maintenance,
    list_asset_maintenance,
    schedule_maintenance,
    start_maintenance,
)
from app.modules.asset_control.services.asset_service import (
    create_asset,
    dispose_asset,
    get_asset,
    list_assets,
    retire_asset,
    update_asset,
)


asset_bp = Blueprint(
    "asset",
    __name__,
    url_prefix="/assets",
)


ASSET_VIEW_ROLES = (
    Role.ADMIN,
    Role.ACCOUNTANT,
)

ASSET_MANAGEMENT_ROLES = (
    Role.ADMIN,
    Role.ACCOUNTANT,
)


def _current_user() -> User:
    identity = get_jwt_identity()

    try:
        user_id = int(identity)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Invalid authentication identity"
        ) from exc

    if user_id <= 0:
        raise ValidationError(
            "Invalid authentication identity"
        )

    user = db.session.get(
        User,
        user_id,
    )

    if user is None:
        raise NotFoundError(
            "Authenticated user not found"
        )

    if not user.is_active:
        raise ValidationError(
            f"Authenticated user {user.id} is inactive"
        )

    return user


def _current_clinic_id(user: User) -> int:
    clinic_id = user.clinic_id

    if (
        isinstance(clinic_id, bool)
        or not isinstance(clinic_id, int)
        or clinic_id <= 0
    ):
        raise ValidationError(
            "Authenticated user is not associated "
            "with a valid clinic"
        )

    return clinic_id


def _json_body(
    *,
    required: bool = True,
) -> dict:
    payload = request.get_json(
        silent=True
    )

    if payload is None:
        if required:
            raise ValidationError(
                "Request body must contain valid JSON"
            )
        return {}

    if not isinstance(payload, dict):
        raise ValidationError(
            "Request body must be a JSON object"
        )

    return payload


def _serialize_asset(asset):
    return AssetResponseSchema.model_validate(
        asset,
        from_attributes=True,
    ).model_dump(
        mode="json"
    )


def _serialize_assets(assets):
    return [
        _serialize_asset(asset)
        for asset in assets
    ]


def _serialize_history(history):
    return AssetHistoryResponseSchema.model_validate(
        history,
        from_attributes=True,
    ).model_dump(
        mode="json"
    )


def _serialize_assignment(assignment):
    return AssetAssignmentResponseSchema.model_validate(
        assignment,
        from_attributes=True,
    ).model_dump(
        mode="json"
    )


def _serialize_maintenance(maintenance):
    return AssetMaintenanceResponseSchema.model_validate(
        maintenance,
        from_attributes=True,
    ).model_dump(
        mode="json"
    )


@asset_bp.post("")
@role_required(*ASSET_MANAGEMENT_ROLES)
def create_asset_route():
    user = _current_user()
    clinic_id = _current_clinic_id(user)

    schema = AssetCreateSchema.model_validate(
        _json_body()
    )

    asset = create_asset(
        clinic_id=clinic_id,
        actor_user_id=user.id,
        data=schema,
    )

    return jsonify(
        {
            "success": True,
            "asset": _serialize_asset(asset),
        }
    ), 201


@asset_bp.get("")
@role_required(*ASSET_VIEW_ROLES)
def list_assets_route():
    user = _current_user()
    clinic_id = _current_clinic_id(user)

    query = AssetListQuerySchema.model_validate(
        request.args.to_dict()
    )

    result = list_assets(
        clinic_id=clinic_id,
        query=query,
    )

    return jsonify(
        {
            "success": True,
            "items": _serialize_assets(
                result["items"]
            ),
            "page": result["page"],
            "per_page": result["per_page"],
            "total": result["total"],
            "pages": result["pages"],
            "has_next": result["has_next"],
            "has_prev": result["has_prev"],
        }
    )


@asset_bp.get("/<int:asset_id>")
@role_required(*ASSET_VIEW_ROLES)
def get_asset_route(
    asset_id: int,
):
    user = _current_user()
    clinic_id = _current_clinic_id(user)

    asset = get_asset(
        asset_id=asset_id,
        clinic_id=clinic_id,
    )

    return jsonify(
        {
            "success": True,
            "asset": _serialize_asset(asset),
        }
    )


@asset_bp.patch("/<int:asset_id>")
@role_required(*ASSET_MANAGEMENT_ROLES)
def update_asset_route(
    asset_id: int,
):
    user = _current_user()
    clinic_id = _current_clinic_id(user)

    schema = AssetUpdateSchema.model_validate(
        _json_body()
    )

    asset = update_asset(
        asset_id=asset_id,
        clinic_id=clinic_id,
        actor_user_id=user.id,
        data=schema,
    )

    return jsonify(
        {
            "success": True,
            "asset": _serialize_asset(asset),
        }
    )


@asset_bp.post("/<int:asset_id>/retire")
@role_required(*ASSET_MANAGEMENT_ROLES)
def retire_asset_route(
    asset_id: int,
):
    user = _current_user()
    clinic_id = _current_clinic_id(user)

    schema = AssetRetireSchema.model_validate(
        _json_body(
            required=False
        )
    )

    asset = retire_asset(
        asset_id=asset_id,
        clinic_id=clinic_id,
        actor_user_id=user.id,
        retirement_date=schema.retirement_date,
    )

    return jsonify(
        {
            "success": True,
            "asset": _serialize_asset(asset),
        }
    )


@asset_bp.post("/<int:asset_id>/dispose")
@role_required(*ASSET_MANAGEMENT_ROLES)
def dispose_asset_route(
    asset_id: int,
):
    user = _current_user()
    clinic_id = _current_clinic_id(user)

    schema = AssetDisposeSchema.model_validate(
        _json_body()
    )

    asset = dispose_asset(
        asset_id=asset_id,
        clinic_id=clinic_id,
        actor_user_id=user.id,
        disposal_reason=schema.disposal_reason,
        disposal_date=schema.disposal_date,
    )

    return jsonify(
        {
            "success": True,
            "asset": _serialize_asset(asset),
        }
    )


@asset_bp.post("/<int:asset_id>/assign")
@role_required(*ASSET_MANAGEMENT_ROLES)
def assign_asset_route(
    asset_id: int,
):
    user = _current_user()
    clinic_id = _current_clinic_id(user)

    schema = AssetAssignmentCreateSchema.model_validate(
        _json_body()
    )

    assignment = assign_asset(
        asset_id=asset_id,
        clinic_id=clinic_id,
        actor_user_id=user.id,
        data=schema,
    )

    return jsonify(
        {
            "success": True,
            "assignment": _serialize_assignment(
                assignment
            ),
        }
    ), 201


@asset_bp.post("/<int:asset_id>/return")
@role_required(*ASSET_MANAGEMENT_ROLES)
def return_asset_route(
    asset_id: int,
):
    user = _current_user()
    clinic_id = _current_clinic_id(user)

    schema = AssetAssignmentReturnSchema.model_validate(
        _json_body(
            required=False
        )
    )

    assignment = return_asset(
        asset_id=asset_id,
        clinic_id=clinic_id,
        actor_user_id=user.id,
        data=schema,
    )

    return jsonify(
        {
            "success": True,
            "assignment": _serialize_assignment(
                assignment
            ),
        }
    )


@asset_bp.get("/<int:asset_id>/assignments")
@role_required(*ASSET_VIEW_ROLES)
def list_asset_assignments_route(
    asset_id: int,
):
    user = _current_user()
    clinic_id = _current_clinic_id(user)

    get_asset(
        asset_id=asset_id,
        clinic_id=clinic_id,
    )

    query_data = request.args.to_dict()
    query_data["asset_id"] = asset_id

    query = AssetAssignmentListQuerySchema.model_validate(
        query_data
    )

    result = list_asset_assignments(
        clinic_id=clinic_id,
        query=query,
    )

    return jsonify(
        {
            "success": True,
            "items": [
                _serialize_assignment(item)
                for item in result["items"]
            ],
            "page": result["page"],
            "per_page": result["per_page"],
            "total": result["total"],
            "pages": result["pages"],
            "has_next": result["has_next"],
            "has_prev": result["has_prev"],
        }
    )


@asset_bp.get("/assignments/<int:assignment_id>")
@role_required(*ASSET_VIEW_ROLES)
def get_asset_assignment_route(
    assignment_id: int,
):
    user = _current_user()
    clinic_id = _current_clinic_id(user)

    assignment = get_asset_assignment(
        assignment_id=assignment_id,
        clinic_id=clinic_id,
    )

    return jsonify(
        {
            "success": True,
            "assignment": _serialize_assignment(
                assignment
            ),
        }
    )


@asset_bp.get("/<int:asset_id>/history")
@role_required(*ASSET_VIEW_ROLES)
def list_asset_history_route(
    asset_id: int,
):
    user = _current_user()
    clinic_id = _current_clinic_id(user)

    get_asset(
        asset_id=asset_id,
        clinic_id=clinic_id,
    )

    query_data = request.args.to_dict()
    query_data["asset_id"] = asset_id

    query = AssetHistoryListQuerySchema.model_validate(
        query_data
    )

    result = list_asset_history(
        clinic_id=clinic_id,
        query=query,
    )

    return jsonify(
        {
            "success": True,
            "items": [
                _serialize_history(item)
                for item in result["items"]
            ],
            "page": result["page"],
            "per_page": result["per_page"],
            "total": result["total"],
            "pages": result["pages"],
            "has_next": result["has_next"],
            "has_prev": result["has_prev"],
        }
    )


@asset_bp.get("/history/<int:history_id>")
@role_required(*ASSET_VIEW_ROLES)
def get_asset_history_route(
    history_id: int,
):
    user = _current_user()
    clinic_id = _current_clinic_id(user)

    history = get_asset_history(
        history_id=history_id,
        clinic_id=clinic_id,
    )

    return jsonify(
        {
            "success": True,
            "history": _serialize_history(history),
        }
    )


@asset_bp.post("/<int:asset_id>/maintenance")
@role_required(*ASSET_MANAGEMENT_ROLES)
def schedule_maintenance_route(
    asset_id: int,
):
    user = _current_user()
    clinic_id = _current_clinic_id(user)

    schema = AssetMaintenanceScheduleSchema.model_validate(
        _json_body()
    )

    maintenance = schedule_maintenance(
        asset_id=asset_id,
        clinic_id=clinic_id,
        actor_user_id=user.id,
        data=schema,
    )

    return jsonify(
        {
            "success": True,
            "maintenance": _serialize_maintenance(
                maintenance
            ),
        }
    ), 201


@asset_bp.get("/<int:asset_id>/maintenance")
@role_required(*ASSET_VIEW_ROLES)
def list_asset_maintenance_route(
    asset_id: int,
):
    user = _current_user()
    clinic_id = _current_clinic_id(user)

    get_asset(
        asset_id=asset_id,
        clinic_id=clinic_id,
    )

    query_data = request.args.to_dict()
    query_data["asset_id"] = asset_id

    query = AssetMaintenanceListQuerySchema.model_validate(
        query_data
    )

    result = list_asset_maintenance(
        clinic_id=clinic_id,
        query=query,
    )

    return jsonify(
        {
            "success": True,
            "items": [
                _serialize_maintenance(item)
                for item in result["items"]
            ],
            "page": result["page"],
            "per_page": result["per_page"],
            "total": result["total"],
            "pages": result["pages"],
            "has_next": result["has_next"],
            "has_prev": result["has_prev"],
        }
    )


@asset_bp.get("/maintenance/<int:maintenance_id>")
@role_required(*ASSET_VIEW_ROLES)
def get_asset_maintenance_route(
    maintenance_id: int,
):
    user = _current_user()
    clinic_id = _current_clinic_id(user)

    maintenance = get_asset_maintenance(
        maintenance_id=maintenance_id,
        clinic_id=clinic_id,
    )

    return jsonify(
        {
            "success": True,
            "maintenance": _serialize_maintenance(
                maintenance
            ),
        }
    )


@asset_bp.post(
    "/maintenance/<int:maintenance_id>/start"
)
@role_required(*ASSET_MANAGEMENT_ROLES)
def start_maintenance_route(
    maintenance_id: int,
):
    user = _current_user()
    clinic_id = _current_clinic_id(user)

    schema = AssetMaintenanceStartSchema.model_validate(
        _json_body(
            required=False
        )
    )

    maintenance = start_maintenance(
        maintenance_id=maintenance_id,
        clinic_id=clinic_id,
        actor_user_id=user.id,
        data=schema,
    )

    return jsonify(
        {
            "success": True,
            "maintenance": _serialize_maintenance(
                maintenance
            ),
        }
    )


@asset_bp.post(
    "/maintenance/<int:maintenance_id>/complete"
)
@role_required(*ASSET_MANAGEMENT_ROLES)
def complete_maintenance_route(
    maintenance_id: int,
):
    user = _current_user()
    clinic_id = _current_clinic_id(user)

    schema = AssetMaintenanceCompleteSchema.model_validate(
        _json_body(
            required=False
        )
    )

    maintenance = complete_maintenance(
        maintenance_id=maintenance_id,
        clinic_id=clinic_id,
        actor_user_id=user.id,
        data=schema,
    )

    return jsonify(
        {
            "success": True,
            "maintenance": _serialize_maintenance(
                maintenance
            ),
        }
    )


@asset_bp.post(
    "/maintenance/<int:maintenance_id>/cancel"
)
@role_required(*ASSET_MANAGEMENT_ROLES)
def cancel_maintenance_route(
    maintenance_id: int,
):
    user = _current_user()
    clinic_id = _current_clinic_id(user)

    schema = AssetMaintenanceCancelSchema.model_validate(
        _json_body()
    )

    maintenance = cancel_maintenance(
        maintenance_id=maintenance_id,
        clinic_id=clinic_id,
        actor_user_id=user.id,
        data=schema,
    )

    return jsonify(
        {
            "success": True,
            "maintenance": _serialize_maintenance(
                maintenance
            ),
        }
    )