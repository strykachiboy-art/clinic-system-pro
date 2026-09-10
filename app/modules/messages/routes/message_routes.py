from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
)
from pydantic import ValidationError as PydanticValidationError

from app.extensions import db
from app.core.auth.user.models.user_model import User
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

from app.modules.messages.schemas.message_schema import (
    MessageCreateSchema,
    MessageListQuerySchema,
    MessageReadSchema,
    MessageSentListQuerySchema,
    MessageThreadQuerySchema,
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


message_bp = Blueprint(
    "message",
    __name__,
    url_prefix="/api/messages",
)


def _payload(schema):
    try:
        return schema.model_validate(
            request.get_json(silent=True) or {}
        )
    except PydanticValidationError as exc:
        return (
            jsonify({
                "success": False,
                "error": "Validation failed",
                "details": exc.errors(),
            }),
            422,
        )


def _query_payload(schema):
    try:
        return schema.model_validate(
            request.args.to_dict()
        )
    except PydanticValidationError as exc:
        return (
            jsonify({
                "success": False,
                "error": "Validation failed",
                "details": exc.errors(),
            }),
            422,
        )


def _get_authenticated_user():
    identity = get_jwt_identity()

    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        raise ValidationError(
            "Invalid authenticated user identity"
        )

    if user_id <= 0:
        raise ValidationError(
            "Invalid authenticated user identity"
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
        raise ConflictError(
            "Authenticated user is inactive"
        )

    if user.clinic_id is None:
        raise ConflictError(
            "Authenticated user is not assigned to a clinic"
        )

    if (
        isinstance(user.clinic_id, bool)
        or not isinstance(user.clinic_id, int)
        or user.clinic_id <= 0
    ):
        raise ValidationError(
            "Authenticated user has an invalid clinic"
        )

    return user


def _serialize_message(message):
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


def _serialize_message_page(page):
    return {
        "items": [
            _serialize_message(message)
            for message in page.items
        ],
        "total": page.total,
        "page": page.page,
        "per_page": page.per_page,
    }


def _error_response(exc):
    if isinstance(exc, NotFoundError):
        status_code = 404
    elif isinstance(exc, ConflictError):
        status_code = 409
    elif isinstance(exc, ValidationError):
        status_code = 422
    else:
        status_code = 400

    return (
        jsonify({
            "success": False,
            "error": str(exc),
        }),
        status_code,
    )


@message_bp.post("/")
@jwt_required()
def create():
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

        return (
            jsonify({
                "success": True,
                "data": _serialize_message(message),
            }),
            201,
        )

    except (
        NotFoundError,
        ConflictError,
        ValidationError,
    ) as exc:
        return _error_response(exc)


@message_bp.get("/inbox")
@jwt_required()
def inbox():
    payload = _query_payload(
        MessageListQuerySchema
    )

    if isinstance(payload, tuple):
        return payload

    try:
        user = _get_authenticated_user()

        messages = get_inbox(
            user_id=user.id,
            clinic_id=user.clinic_id,
            unread_only=payload.unread_only,
            page=payload.page,
            per_page=payload.per_page,
        )

        return (
            jsonify({
                "success": True,
                "data": _serialize_message_page(messages),
            }),
            200,
        )

    except (
        NotFoundError,
        ConflictError,
        ValidationError,
    ) as exc:
        return _error_response(exc)


@message_bp.get("/inbox/unread")
@jwt_required()
def unread_inbox():
    payload = _query_payload(
        MessageSentListQuerySchema
    )

    if isinstance(payload, tuple):
        return payload

    try:
        user = _get_authenticated_user()

        messages = get_inbox(
            user_id=user.id,
            clinic_id=user.clinic_id,
            unread_only=True,
            page=payload.page,
            per_page=payload.per_page,
        )

        return (
            jsonify({
                "success": True,
                "data": _serialize_message_page(messages),
            }),
            200,
        )

    except (
        NotFoundError,
        ConflictError,
        ValidationError,
    ) as exc:
        return _error_response(exc)


@message_bp.get("/sent")
@jwt_required()
def sent():
    payload = _query_payload(
        MessageSentListQuerySchema
    )

    if isinstance(payload, tuple):
        return payload

    try:
        user = _get_authenticated_user()

        messages = get_sent_messages(
            user_id=user.id,
            clinic_id=user.clinic_id,
            page=payload.page,
            per_page=payload.per_page,
        )

        return (
            jsonify({
                "success": True,
                "data": _serialize_message_page(messages),
            }),
            200,
        )

    except (
        NotFoundError,
        ConflictError,
        ValidationError,
    ) as exc:
        return _error_response(exc)


@message_bp.get("/<int:message_id>")
@jwt_required()
def get(message_id: int):
    try:
        user = _get_authenticated_user()

        message = get_message_for_user(
            message_id=message_id,
            user_id=user.id,
            clinic_id=user.clinic_id,
        )

        return (
            jsonify({
                "success": True,
                "data": _serialize_message(message),
            }),
            200,
        )

    except (
        NotFoundError,
        ConflictError,
        ValidationError,
    ) as exc:
        return _error_response(exc)


@message_bp.patch("/<int:message_id>")
@jwt_required()
def update(message_id: int):
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

        return (
            jsonify({
                "success": True,
                "data": _serialize_message(message),
            }),
            200,
        )

    except (
        NotFoundError,
        ConflictError,
        ValidationError,
    ) as exc:
        return _error_response(exc)


@message_bp.post("/<int:message_id>/read")
@jwt_required()
def read(message_id: int):
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

        return (
            jsonify({
                "success": True,
                "data": _serialize_message(message),
            }),
            200,
        )

    except (
        NotFoundError,
        ConflictError,
        ValidationError,
    ) as exc:
        return _error_response(exc)


@message_bp.post("/<int:message_id>/archive")
@jwt_required()
def archive(message_id: int):
    try:
        user = _get_authenticated_user()

        message = archive_message(
            message_id=message_id,
            user_id=user.id,
            clinic_id=user.clinic_id,
        )

        return (
            jsonify({
                "success": True,
                "data": _serialize_message(message),
            }),
            200,
        )

    except (
        NotFoundError,
        ConflictError,
        ValidationError,
    ) as exc:
        return _error_response(exc)


@message_bp.delete("/<int:message_id>")
@jwt_required()
def delete(message_id: int):
    try:
        user = _get_authenticated_user()

        message = delete_message(
            message_id=message_id,
            user_id=user.id,
            clinic_id=user.clinic_id,
        )

        return (
            jsonify({
                "success": True,
                "data": _serialize_message(message),
            }),
            200,
        )

    except (
        NotFoundError,
        ConflictError,
        ValidationError,
    ) as exc:
        return _error_response(exc)


@message_bp.get("/<int:message_id>/thread")
@jwt_required()
def thread(message_id: int):
    payload = _query_payload(
        MessageThreadQuerySchema
    )

    if isinstance(payload, tuple):
        return payload

    try:
        user = _get_authenticated_user()

        messages = get_message_thread(
            message_id=message_id,
            user_id=user.id,
            clinic_id=user.clinic_id,
            page=payload.page,
            per_page=payload.per_page,
        )

        return (
            jsonify({
                "success": True,
                "data": _serialize_message_page(messages),
            }),
            200,
        )

    except (
        NotFoundError,
        ConflictError,
        ValidationError,
    ) as exc:
        return _error_response(exc)