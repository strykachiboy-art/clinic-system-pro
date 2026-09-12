from __future__ import annotations

from math import ceil

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.core.auth.user.models.user_model import User
from app.core.enums.role_enums import Role
from app.core.exceptions import ValidationError
from app.core.utils.decorators import role_required
from app.extensions import db

from app.modules.access_control.schemas.access_control_schema import (
    AccessControlRoleChangeResponseSchema,
    AccessControlRoleUpdateSchema,
    AccessControlStatusChangeResponseSchema,
    AccessControlStatusUpdateSchema,
    AccessControlUserListQuerySchema,
    AccessControlUserResponseSchema,
)
from app.modules.access_control.services.access_control_service import (
    change_user_role,
    change_user_status,
    get_access_control_user,
    list_access_control_users,
)


access_control_bp = Blueprint(
    "access_control",
    __name__,
    url_prefix="/access-control",
)


def _json_body() -> dict:
    payload = request.get_json(
        silent=True
    )

    if payload is None:
        return {}

    if not isinstance(payload, dict):
        raise ValidationError(
            "JSON body must be an object"
        )

    return payload


def _get_current_user() -> User:
    identity = get_jwt_identity()

    try:
        user_id = int(identity)
    except (
        TypeError,
        ValueError,
    ) as exc:
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
        raise ValidationError(
            "Authenticated user could not be resolved"
        )

    if not user.is_active:
        raise ValidationError(
            "User account is inactive"
        )

    return user


def _serialize(
    schema,
    value,
) -> dict:
    return (
        schema
        .model_validate(
            value,
            from_attributes=True,
        )
        .model_dump(
            mode="json"
        )
    )


@access_control_bp.get("/users")
@role_required(
    Role.ADMIN,
    Role.SUPER_ADMIN,
)
def list_access_control_users_route():
    current_user = _get_current_user()

    query = AccessControlUserListQuerySchema.model_validate(
        request.args.to_dict()
    )

    users, total = list_access_control_users(
        actor_id=current_user.id,
        query=query,
    )

    total_pages = (
        ceil(total / query.per_page)
        if total
        else 0
    )

    return jsonify(
        {
            "success": True,
            "data": {
                "items": [
                    _serialize(
                        AccessControlUserResponseSchema,
                        user,
                    )
                    for user in users
                ],
                "pagination": {
                    "page": query.page,
                    "per_page": query.per_page,
                    "total": total,
                    "pages": total_pages,
                },
            },
        }
    ), 200


@access_control_bp.get(
    "/users/<int:user_id>"
)
@role_required(
    Role.ADMIN,
    Role.SUPER_ADMIN,
)
def get_access_control_user_route(
    user_id: int,
):
    current_user = _get_current_user()

    user = get_access_control_user(
        actor_id=current_user.id,
        user_id=user_id,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                AccessControlUserResponseSchema,
                user,
            ),
        }
    ), 200


@access_control_bp.patch(
    "/users/<int:user_id>/role"
)
@role_required(
    Role.SUPER_ADMIN,
)
def change_user_role_route(
    user_id: int,
):
    current_user = _get_current_user()

    payload = AccessControlRoleUpdateSchema.model_validate(
        _json_body()
    )

    result = change_user_role(
        actor_id=current_user.id,
        user_id=user_id,
        new_role=payload.role,
        reason=payload.reason,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                AccessControlRoleChangeResponseSchema,
                result,
            ),
        }
    ), 200


@access_control_bp.patch(
    "/users/<int:user_id>/status"
)
@role_required(
    Role.ADMIN,
    Role.SUPER_ADMIN,
)
def change_user_status_route(
    user_id: int,
):
    current_user = _get_current_user()

    payload = AccessControlStatusUpdateSchema.model_validate(
        _json_body()
    )

    result = change_user_status(
        actor_id=current_user.id,
        user_id=user_id,
        is_active=payload.is_active,
        reason=payload.reason,
    )

    return jsonify(
        {
            "success": True,
            "data": _serialize(
                AccessControlStatusChangeResponseSchema,
                result,
            ),
        }
    ), 200