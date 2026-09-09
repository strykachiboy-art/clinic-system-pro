from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
)
from pydantic import ValidationError as PydanticValidationError

from app.core.auth.user.models.user_model import User
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

from app.core.notifications.schemas.notification_schema import (
    NotificationCreateSchema,
    NotificationListQuerySchema,
    NotificationReadSchema,
)

from app.core.notifications.services.notification_service import (
    create_notification,
    get_notification_for_user,
    get_user_notifications,
    mark_all_notifications_read,
    mark_notification_read,
)


notification_bp = Blueprint(
    "notification",
    __name__,
    url_prefix="/api/notifications",
)


def _payload(schema):
    """
    Validate and parse a JSON request payload.
    """
    try:
        return schema.model_validate(
            request.get_json(silent=True) or {}
        )
    except PydanticValidationError as exc:
        return (
            jsonify({
                "success": False,
                "error": exc.errors(),
            }),
            422,
        )


def _query_payload(schema):
    """
    Validate and parse query-string parameters.
    """
    try:
        return schema.model_validate(
            request.args.to_dict()
        )
    except PydanticValidationError as exc:
        return (
            jsonify({
                "success": False,
                "error": exc.errors(),
            }),
            422,
        )


def _get_authenticated_user():
    """
    Return the active authenticated user.

    Clinic ownership is derived from the authenticated
    user and is never accepted from the client.
    """
    identity = get_jwt_identity()

    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        raise ValidationError(
            "Invalid authenticated user identity"
        )

    user = User.query.filter(
        User.id == user_id,
    ).first()

    if user is None:
        raise NotFoundError(
            "Authenticated user not found"
        )

    if not user.is_active:
        raise ConflictError(
            "Authenticated user is inactive"
        )

    if user.clinic_id is None:
        raise ConflictError(
            "Authenticated user is not assigned to a clinic"
        )

    return user


def _serialize_notification(notification):
    """
    Serialize a notification model into an API-safe dictionary.
    """
    return {
        "id": notification.id,
        "clinic_id": notification.clinic_id,
        "user_id": notification.user_id,
        "title": notification.title,
        "message": notification.message,
        "notification_type": (
            notification.notification_type.value
        ),
        "priority": notification.priority.value,
        "channel": notification.channel.value,
        "status": notification.status.value,
        "reference_type": notification.reference_type,
        "reference_id": notification.reference_id,
        "is_read": notification.is_read,
        "read_at": (
            notification.read_at.isoformat()
            if notification.read_at
            else None
        ),
        "sent_at": (
            notification.sent_at.isoformat()
            if notification.sent_at
            else None
        ),
        "delivered_at": (
            notification.delivered_at.isoformat()
            if notification.delivered_at
            else None
        ),
        "failed_at": (
            notification.failed_at.isoformat()
            if notification.failed_at
            else None
        ),
        "error_message": notification.error_message,
        "retry_count": notification.retry_count,
        "created_at": (
            notification.created_at.isoformat()
            if notification.created_at
            else None
        ),
        "updated_at": (
            notification.updated_at.isoformat()
            if notification.updated_at
            else None
        ),
    }


def _serialize_notification_page(result):
    """
    Serialize a paginated notification service result.
    """
    return {
        "items": [
            _serialize_notification(notification)
            for notification in result["items"]
        ],
        "page": result["page"],
        "per_page": result["per_page"],
        "total": result["total"],
        "pages": result["pages"],
        "has_next": result["has_next"],
        "has_prev": result["has_prev"],
    }


@notification_bp.post("/")
@jwt_required()
def create():
    """
    Create a notification for the authenticated user.
    """
    payload = _payload(NotificationCreateSchema)

    if isinstance(payload, tuple):
        return payload

    try:
        user = _get_authenticated_user()

        notification = create_notification(
            clinic_id=user.clinic_id,
            **payload.model_dump(),
        )

        return jsonify({
            "success": True,
            "data": _serialize_notification(notification),
        }), 201

    except NotFoundError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 404

    except (ValidationError, ConflictError) as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 400


@notification_bp.get("/")
@jwt_required()
def list_notifications():
    """
    Return paginated notifications for the authenticated user.

    Default:
        page=1
        per_page=50

    Maximum:
        per_page=500
    """
    query_payload = _query_payload(
        NotificationListQuerySchema
    )

    if isinstance(query_payload, tuple):
        return query_payload

    try:
        user = _get_authenticated_user()

        result = get_user_notifications(
            user_id=user.id,
            clinic_id=user.clinic_id,
            unread_only=False,
            page=query_payload.page,
            per_page=query_payload.per_page,
        )

        return jsonify({
            "success": True,
            "data": _serialize_notification_page(
                result
            ),
        }), 200

    except NotFoundError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 404

    except (ValidationError, ConflictError) as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 400


@notification_bp.get("/unread")
@jwt_required()
def unread_notifications():
    """
    Return paginated unread notifications for
    the authenticated user.
    """
    query_payload = _query_payload(
        NotificationListQuerySchema
    )

    if isinstance(query_payload, tuple):
        return query_payload

    try:
        user = _get_authenticated_user()

        result = get_user_notifications(
            user_id=user.id,
            clinic_id=user.clinic_id,
            unread_only=True,
            page=query_payload.page,
            per_page=query_payload.per_page,
        )

        return jsonify({
            "success": True,
            "data": _serialize_notification_page(
                result
            ),
        }), 200

    except NotFoundError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 404

    except (ValidationError, ConflictError) as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 400


@notification_bp.get("/<int:notification_id>")
@jwt_required()
def get(notification_id: int):
    """
    Return one notification belonging to the
    authenticated user and clinic.
    """
    try:
        user = _get_authenticated_user()

        notification = get_notification_for_user(
            notification_id=notification_id,
            user_id=user.id,
            clinic_id=user.clinic_id,
        )

        return jsonify({
            "success": True,
            "data": _serialize_notification(
                notification
            ),
        }), 200

    except NotFoundError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 404

    except (ValidationError, ConflictError) as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 400


@notification_bp.post("/<int:notification_id>/read")
@jwt_required()
def read(notification_id: int):
    """
    Mark one notification as read.
    """
    payload = _payload(NotificationReadSchema)

    if isinstance(payload, tuple):
        return payload

    try:
        user = _get_authenticated_user()

        notification = mark_notification_read(
            notification_id=notification_id,
            user_id=user.id,
            clinic_id=user.clinic_id,
        )

        return jsonify({
            "success": True,
            "data": _serialize_notification(
                notification
            ),
        }), 200

    except NotFoundError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 404

    except (ValidationError, ConflictError) as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 400


@notification_bp.post("/read-all")
@jwt_required()
def read_all():
    """
    Mark all unread notifications for the authenticated
    user and clinic as read.
    """
    payload = _payload(NotificationReadSchema)

    if isinstance(payload, tuple):
        return payload

    try:
        user = _get_authenticated_user()

        count = mark_all_notifications_read(
            user_id=user.id,
            clinic_id=user.clinic_id,
        )

        return jsonify({
            "success": True,
            "data": {
                "updated_count": count,
            },
        }), 200

    except NotFoundError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 404

    except (ValidationError, ConflictError) as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 400