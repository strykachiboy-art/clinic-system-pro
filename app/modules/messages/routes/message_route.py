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

from app.modules.messages.schemas.message_schema import (
    MessageCreateSchema,
    MessageReadSchema,
    MessageUpdateSchema,
)

from app.modules.messages.services.message_service import (
    archive_message,
    create_message,
    delete_message,
    get_inbox,
    get_message_for_user,
    get_message_thread,
    get_sent_messages,
    mark_message_read,
    update_message,
)


# ============================================================================
# BLUEPRINT
# ============================================================================


message_bp = Blueprint(
    "message",
    __name__,
    url_prefix="/api/messages",
)


# ============================================================================
# HELPERS
# ============================================================================


def _payload(schema):
    """
    Validate incoming JSON using the supplied Pydantic schema.
    """

    try:
        payload = schema.model_validate(
            request.get_json(silent=True) or {}
        )

        return payload

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
    Resolve the authenticated JWT identity to an active User.

    The user's clinic_id is used as the tenant boundary for
    every message operation.
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


def _serialize_message(message):
    """
    Convert a Message model into an API-safe response.
    """

    return {
        "id": message.id,
        "clinic_id": message.clinic_id,
        "sender_id": message.sender_id,
        "recipient_id": message.recipient_id,
        "subject": message.subject,
        "body": message.body,
        "message_type": message.message_type.value,
        "status": message.status.value,
        "priority": message.priority.value,
        "parent_message_id": message.parent_message_id,
        "sent_at": (
            message.sent_at.isoformat()
            if message.sent_at
            else None
        ),
        "read_at": (
            message.read_at.isoformat()
            if message.read_at
            else None
        ),
        "deleted_at": (
            message.deleted_at.isoformat()
            if message.deleted_at
            else None
        ),
        "created_at": (
            message.created_at.isoformat()
            if message.created_at
            else None
        ),
        "updated_at": (
            message.updated_at.isoformat()
            if message.updated_at
            else None
        ),
    }


# ============================================================================
# SEND MESSAGE
# ============================================================================


@message_bp.post("/")
@jwt_required()
def create():
    """
    Send a new message.

    POST /api/messages/

    The authenticated user is always the sender.

    clinic_id and sender_id are NEVER accepted from the
    request body.
    """

    payload = _payload(
        MessageCreateSchema
    )

    if isinstance(payload, tuple):
        return payload

    try:
        user = _get_authenticated_user()

        message = create_message(
            clinic_id=user.clinic_id,
            sender_id=user.id,
            **payload.model_dump(),
        )

        return jsonify({
            "success": True,
            "data": _serialize_message(message),
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


# ============================================================================
# INBOX
# ============================================================================


@message_bp.get("/inbox")
@jwt_required()
def inbox():
    """
    Get messages received by the authenticated user.

    GET /api/messages/inbox
    """

    try:
        user = _get_authenticated_user()

        messages = get_inbox(
            user_id=user.id,
            clinic_id=user.clinic_id,
        )

        return jsonify({
            "success": True,
            "data": [
                _serialize_message(message)
                for message in messages
            ],
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


# ============================================================================
# UNREAD INBOX
# ============================================================================


@message_bp.get("/inbox/unread")
@jwt_required()
def unread_inbox():
    """
    Get unread messages received by the authenticated user.

    GET /api/messages/inbox/unread
    """

    try:
        user = _get_authenticated_user()

        messages = get_inbox(
            user_id=user.id,
            clinic_id=user.clinic_id,
            unread_only=True,
        )

        return jsonify({
            "success": True,
            "data": [
                _serialize_message(message)
                for message in messages
            ],
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


# ============================================================================
# SENT MESSAGES
# ============================================================================


@message_bp.get("/sent")
@jwt_required()
def sent():
    """
    Get messages sent by the authenticated user.

    GET /api/messages/sent
    """

    try:
        user = _get_authenticated_user()

        messages = get_sent_messages(
            user_id=user.id,
            clinic_id=user.clinic_id,
        )

        return jsonify({
            "success": True,
            "data": [
                _serialize_message(message)
                for message in messages
            ],
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


# ============================================================================
# GET MESSAGE
# ============================================================================


@message_bp.get("/<int:message_id>")
@jwt_required()
def get(message_id: int):
    """
    Get a single message.

    GET /api/messages/<message_id>

    Access is restricted to the sender or recipient.
    """

    try:
        user = _get_authenticated_user()

        message = get_message_for_user(
            message_id=message_id,
            user_id=user.id,
            clinic_id=user.clinic_id,
        )

        return jsonify({
            "success": True,
            "data": _serialize_message(message),
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


# ============================================================================
# UPDATE MESSAGE
# ============================================================================


@message_bp.patch("/<int:message_id>")
@jwt_required()
def update(message_id: int):
    """
    Update editable message fields.

    PATCH /api/messages/<message_id>

    The service determines whether the authenticated user
    is allowed to modify the message.
    """

    payload = _payload(
        MessageUpdateSchema
    )

    if isinstance(payload, tuple):
        return payload

    try:
        user = _get_authenticated_user()

        fields = payload.model_dump(
            exclude_unset=True,
        )

        message = update_message(
            message_id=message_id,
            user_id=user.id,
            clinic_id=user.clinic_id,
            **fields,
        )

        return jsonify({
            "success": True,
            "data": _serialize_message(message),
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


# ============================================================================
# MARK READ
# ============================================================================


@message_bp.post("/<int:message_id>/read")
@jwt_required()
def read(message_id: int):
    """
    Mark a received message as read.

    POST /api/messages/<message_id>/read
    """

    payload = _payload(
        MessageReadSchema
    )

    if isinstance(payload, tuple):
        return payload

    try:
        user = _get_authenticated_user()

        message = mark_message_read(
            message_id=message_id,
            user_id=user.id,
            clinic_id=user.clinic_id,
        )

        return jsonify({
            "success": True,
            "data": _serialize_message(message),
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


# ============================================================================
# ARCHIVE
# ============================================================================


@message_bp.post("/<int:message_id>/archive")
@jwt_required()
def archive(message_id: int):
    """
    Archive a message.

    POST /api/messages/<message_id>/archive
    """

    try:
        user = _get_authenticated_user()

        message = archive_message(
            message_id=message_id,
            user_id=user.id,
            clinic_id=user.clinic_id,
        )

        return jsonify({
            "success": True,
            "data": _serialize_message(message),
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


# ============================================================================
# SOFT DELETE
# ============================================================================


@message_bp.delete("/<int:message_id>")
@jwt_required()
def delete(message_id: int):
    """
    Soft-delete a message.

    DELETE /api/messages/<message_id>
    """

    try:
        user = _get_authenticated_user()

        message = delete_message(
            message_id=message_id,
            user_id=user.id,
            clinic_id=user.clinic_id,
        )

        return jsonify({
            "success": True,
            "data": _serialize_message(message),
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


# ============================================================================
# THREAD
# ============================================================================


@message_bp.get("/<int:message_id>/thread")
@jwt_required()
def thread(message_id: int):
    """
    Get the complete conversation thread.

    GET /api/messages/<message_id>/thread
    """

    try:
        user = _get_authenticated_user()

        messages = get_message_thread(
            message_id=message_id,
            user_id=user.id,
            clinic_id=user.clinic_id,
        )

        return jsonify({
            "success": True,
            "data": [
                _serialize_message(message)
                for message in messages
            ],
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