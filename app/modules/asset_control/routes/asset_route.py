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

from app.modules.asset_control.schemas.asset_schema import (
    AssetCreateSchema,
    AssetDisposeSchema,
    AssetListQuerySchema,
    AssetResponseSchema,
    AssetRetireSchema,
    AssetUpdateSchema,
)
from app.modules.asset_control.services.asset_service import (
    create_asset,
    dispose_asset,
    get_asset,
    list_assets,
    retire_asset,
    update_asset,
)


# ============================================================================
# BLUEPRINT
# ============================================================================


asset_bp = Blueprint(
    "asset",
    __name__,
    url_prefix="/api/assets",
)


# ============================================================================
# ROLE GROUPS
# ============================================================================


ASSET_VIEW_ROLES = (
    Role.ADMIN,
    Role.ACCOUNTANT,
)

ASSET_MANAGEMENT_ROLES = (
    Role.ADMIN,
    Role.ACCOUNTANT,
)


# ============================================================================
# AUTHENTICATION / CONTEXT HELPERS
# ============================================================================


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


def _current_clinic_id(
    user: User,
) -> int:
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


# ============================================================================
# RESPONSE HELPERS
# ============================================================================


def _serialize_asset(asset):
    return AssetResponseSchema.model_validate(
        asset,
        from_attributes=True,
    ).model_dump(
        mode="json"
    )


def _serialize_assets(
    assets,
):
    return [
        _serialize_asset(asset)
        for asset in assets
    ]


# ============================================================================
# CREATE ASSET
# ============================================================================


@asset_bp.post("")
@role_required(*ASSET_MANAGEMENT_ROLES)
def create_asset_route():
    user = _current_user()
    clinic_id = _current_clinic_id(user)

    payload = request.get_json(
        silent=True
    )

    if payload is None:
        raise ValidationError(
            "Request body must contain valid JSON"
        )

    schema = AssetCreateSchema.model_validate(
        payload
    )

    asset = create_asset(
        clinic_id=clinic_id,
        actor_user_id=user.id,
        data=schema,
    )

    return jsonify(
        {
            "success": True,
            "asset": _serialize_asset(
                asset
            ),
        }
    ), 201


# ============================================================================
# LIST ASSETS
# ============================================================================


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


# ============================================================================
# GET SINGLE ASSET
# ============================================================================


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
            "asset": _serialize_asset(
                asset
            ),
        }
    )


# ============================================================================
# UPDATE ASSET
# ============================================================================


@asset_bp.patch("/<int:asset_id>")
@role_required(*ASSET_MANAGEMENT_ROLES)
def update_asset_route(
    asset_id: int,
):
    user = _current_user()
    clinic_id = _current_clinic_id(user)

    payload = request.get_json(
        silent=True
    )

    if payload is None:
        raise ValidationError(
            "Request body must contain valid JSON"
        )

    schema = AssetUpdateSchema.model_validate(
        payload
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
            "asset": _serialize_asset(
                asset
            ),
        }
    )


# ============================================================================
# RETIRE ASSET
# ============================================================================


@asset_bp.post("/<int:asset_id>/retire")
@role_required(*ASSET_MANAGEMENT_ROLES)
def retire_asset_route(
    asset_id: int,
):
    user = _current_user()
    clinic_id = _current_clinic_id(user)

    payload = request.get_json(
        silent=True
    ) or {}

    schema = AssetRetireSchema.model_validate(
        payload
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
            "asset": _serialize_asset(
                asset
            ),
        }
    )


# ============================================================================
# DISPOSE ASSET
# ============================================================================


@asset_bp.post("/<int:asset_id>/dispose")
@role_required(*ASSET_MANAGEMENT_ROLES)
def dispose_asset_route(
    asset_id: int,
):
    user = _current_user()
    clinic_id = _current_clinic_id(user)

    payload = request.get_json(
        silent=True
    )

    if payload is None:
        raise ValidationError(
            "Request body must contain valid JSON"
        )

    schema = AssetDisposeSchema.model_validate(
        payload
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
            "asset": _serialize_asset(
                asset
            ),
        }
    )