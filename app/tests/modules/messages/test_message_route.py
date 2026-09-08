from datetime import datetime, timezone

import pytest
from flask_jwt_extended import create_access_token

from app.core.enums.message_enums import (
    MessagePriority,
    MessageStatus,
    MessageType,
)
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.messages.models.message_model import Message
from app.modules.messages.routes import message_routes


# ============================================================================
# HELPERS
# ============================================================================


def auth_headers(user):
    """
    Build JWT Authorization headers for a real application user.
    """
    token = create_access_token(
        identity=str(user.id),
    )

    return {
        "Authorization": f"Bearer {token}",
    }


def assert_success(response, status_code=200):
    """
    Assert standard successful API response.
    """
    assert response.status_code == status_code

    data = response.get_json()

    assert data is not None
    assert data["success"] is True
    assert "data" in data

    return data


def assert_error(response, status_code):
    """
    Assert standard error API response.
    """
    assert response.status_code == status_code

    data = response.get_json()

    assert data is not None
    assert data["success"] is False
    assert "error" in data

    return data


def create_message_users(
    make_user,
    clinic,
):
    """
    Create a sender and recipient inside the same clinic.
    """
    sender = make_user(
        clinic=clinic,
        email="message-route-sender@example.com",
    )

    recipient = make_user(
        clinic=clinic,
        email="message-route-recipient@example.com",
    )

    return sender, recipient


# ============================================================================
# AUTHENTICATION
# ============================================================================


def test_create_requires_authentication(client):
    response = client.post(
        "/api/messages/",
        json={
            "recipient_id": 1,
            "subject": "Test",
            "body": "Hello",
        },
    )

    assert response.status_code == 401


def test_inbox_requires_authentication(client):
    response = client.get(
        "/api/messages/inbox",
    )

    assert response.status_code == 401


def test_unread_inbox_requires_authentication(client):
    response = client.get(
        "/api/messages/inbox/unread",
    )

    assert response.status_code == 401


def test_sent_requires_authentication(client):
    response = client.get(
        "/api/messages/sent",
    )

    assert response.status_code == 401


def test_get_message_requires_authentication(client):
    response = client.get(
        "/api/messages/1",
    )

    assert response.status_code == 401


def test_update_message_requires_authentication(client):
    response = client.patch(
        "/api/messages/1",
        json={
            "subject": "Updated",
        },
    )

    assert response.status_code == 401


def test_mark_read_requires_authentication(client):
    response = client.post(
        "/api/messages/1/read",
        json={},
    )

    assert response.status_code == 401


def test_archive_requires_authentication(client):
    response = client.post(
        "/api/messages/1/archive",
    )

    assert response.status_code == 401


def test_delete_requires_authentication(client):
    response = client.delete(
        "/api/messages/1",
    )

    assert response.status_code == 401


def test_thread_requires_authentication(client):
    response = client.get(
        "/api/messages/1/thread",
    )

    assert response.status_code == 401


# ============================================================================
# CREATE MESSAGE
# ============================================================================


def test_create_message_success(
    client,
    clinic,
    make_user,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    response = client.post(
        "/api/messages/",
        headers=auth_headers(sender),
        json={
            "recipient_id": recipient.id,
            "subject": "Hello",
            "body": "This is a test message.",
            "message_type": "direct",
            "priority": "normal",
        },
    )

    data = assert_success(
        response,
        201,
    )

    message = data["data"]

    assert message["clinic_id"] == clinic.id
    assert message["sender_id"] == sender.id
    assert message["recipient_id"] == recipient.id
    assert message["subject"] == "Hello"
    assert message["body"] == "This is a test message."
    assert message["message_type"] == "direct"
    assert message["status"] == "sent"
    assert message["priority"] == "normal"
    assert message["parent_message_id"] is None
    assert message["sent_at"] is not None
    assert message["created_at"] is not None
    assert message["updated_at"] is not None


def test_create_message_does_not_accept_sender_id_from_payload(
    client,
    clinic,
    make_user,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    attacker = make_user(
        clinic=clinic,
        email="message-route-attacker@example.com",
    )

    response = client.post(
        "/api/messages/",
        headers=auth_headers(sender),
        json={
            "recipient_id": recipient.id,
            "sender_id": attacker.id,
            "clinic_id": 999999,
            "subject": "Injected",
            "body": "Attempted identity injection.",
        },
    )

    # Current schema does not declare extra="forbid", so the route may
    # accept the extra fields at schema level. The service call should
    # nevertheless use the authenticated sender and clinic.
    assert response.status_code == 201

    data = response.get_json()["data"]

    assert data["sender_id"] == sender.id
    assert data["clinic_id"] == clinic.id


def test_create_message_missing_recipient_returns_422(
    client,
    clinic,
    make_user,
):
    sender = make_user(
        clinic=clinic,
        email="message-validation-sender@example.com",
    )

    response = client.post(
        "/api/messages/",
        headers=auth_headers(sender),
        json={
            "subject": "Missing recipient",
            "body": "Body",
        },
    )

    data = assert_error(
        response,
        422,
    )

    assert isinstance(data["error"], list)


def test_create_message_empty_subject_returns_422(
    client,
    clinic,
    make_user,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    response = client.post(
        "/api/messages/",
        headers=auth_headers(sender),
        json={
            "recipient_id": recipient.id,
            "subject": "",
            "body": "Body",
        },
    )

    assert_error(
        response,
        422,
    )


def test_create_message_empty_body_returns_422(
    client,
    clinic,
    make_user,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    response = client.post(
        "/api/messages/",
        headers=auth_headers(sender),
        json={
            "recipient_id": recipient.id,
            "subject": "Subject",
            "body": "",
        },
    )

    assert_error(
        response,
        422,
    )


def test_create_message_invalid_message_type_returns_422(
    client,
    clinic,
    make_user,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    response = client.post(
        "/api/messages/",
        headers=auth_headers(sender),
        json={
            "recipient_id": recipient.id,
            "subject": "Invalid type",
            "body": "Body",
            "message_type": "invalid",
        },
    )

    assert_error(
        response,
        422,
    )


def test_create_message_invalid_priority_returns_422(
    client,
    clinic,
    make_user,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    response = client.post(
        "/api/messages/",
        headers=auth_headers(sender),
        json={
            "recipient_id": recipient.id,
            "subject": "Invalid priority",
            "body": "Body",
            "priority": "critical",
        },
    )

    assert_error(
        response,
        422,
    )


def test_create_message_service_not_found_becomes_404(
    client,
    clinic,
    make_user,
    monkeypatch,
):
    sender = make_user(
        clinic=clinic,
        email="message-notfound-sender@example.com",
    )

    def fake_create_message(**kwargs):
        raise NotFoundError("Recipient not found")

    monkeypatch.setattr(
        message_routes,
        "create_message",
        fake_create_message,
    )

    response = client.post(
        "/api/messages/",
        headers=auth_headers(sender),
        json={
            "recipient_id": 999999,
            "subject": "Test",
            "body": "Body",
        },
    )

    data = assert_error(
        response,
        404,
    )

    assert data["error"] == "Recipient not found"


def test_create_message_service_conflict_becomes_400(
    client,
    clinic,
    make_user,
    monkeypatch,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    def fake_create_message(**kwargs):
        raise ConflictError("Sender cannot message recipient")

    monkeypatch.setattr(
        message_routes,
        "create_message",
        fake_create_message,
    )

    response = client.post(
        "/api/messages/",
        headers=auth_headers(sender),
        json={
            "recipient_id": recipient.id,
            "subject": "Test",
            "body": "Body",
        },
    )

    data = assert_error(
        response,
        400,
    )

    assert data["error"] == "Sender cannot message recipient"


# ============================================================================
# INBOX
# ============================================================================


def test_inbox_success(
    client,
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic=clinic,
        sender=sender,
        recipient=recipient,
        subject="Inbox message",
        body="Inbox body",
    )

    response = client.get(
        "/api/messages/inbox",
        headers=auth_headers(recipient),
    )

    data = assert_success(
        response,
        200,
    )

    assert len(data["data"]) == 1

    item = data["data"][0]

    assert item["id"] == message.id
    assert item["recipient_id"] == recipient.id
    assert item["sender_id"] == sender.id
    assert item["subject"] == "Inbox message"
    assert item["status"] == "sent"


def test_inbox_excludes_deleted_messages(
    client,
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    make_message(
        clinic=clinic,
        sender=sender,
        recipient=recipient,
        subject="Deleted",
        deleted_at=datetime.now(timezone.utc),
    )

    response = client.get(
        "/api/messages/inbox",
        headers=auth_headers(recipient),
    )

    data = assert_success(
        response,
        200,
    )

    assert data["data"] == []


def test_inbox_service_not_found_becomes_404(
    client,
    clinic,
    make_user,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        email="inbox-notfound@example.com",
    )

    def fake_get_inbox(**kwargs):
        raise NotFoundError("User not found")

    monkeypatch.setattr(
        message_routes,
        "get_inbox",
        fake_get_inbox,
    )

    response = client.get(
        "/api/messages/inbox",
        headers=auth_headers(user),
    )

    data = assert_error(
        response,
        404,
    )

    assert data["error"] == "User not found"


# ============================================================================
# UNREAD INBOX
# ============================================================================


def test_unread_inbox_returns_only_unread(
    client,
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    unread = make_message(
        clinic=clinic,
        sender=sender,
        recipient=recipient,
        subject="Unread",
    )

    make_message(
        clinic=clinic,
        sender=sender,
        recipient=recipient,
        subject="Read",
        read_at=datetime.now(timezone.utc),
    )

    response = client.get(
        "/api/messages/inbox/unread",
        headers=auth_headers(recipient),
    )

    data = assert_success(
        response,
        200,
    )

    assert len(data["data"]) == 1
    assert data["data"][0]["id"] == unread.id
    assert data["data"][0]["read_at"] is None


def test_unread_inbox_calls_service_with_unread_only(
    client,
    clinic,
    make_user,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        email="unread-service@example.com",
    )

    captured = {}

    def fake_get_inbox(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(
        message_routes,
        "get_inbox",
        fake_get_inbox,
    )

    response = client.get(
        "/api/messages/inbox/unread",
        headers=auth_headers(user),
    )

    assert_success(
        response,
        200,
    )

    assert captured["user_id"] == user.id
    assert captured["clinic_id"] == clinic.id
    assert captured["unread_only"] is True


# ============================================================================
# SENT
# ============================================================================


def test_sent_messages_success(
    client,
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic=clinic,
        sender=sender,
        recipient=recipient,
        subject="Sent message",
        body="Sent body",
    )

    response = client.get(
        "/api/messages/sent",
        headers=auth_headers(sender),
    )

    data = assert_success(
        response,
        200,
    )

    assert len(data["data"]) == 1

    item = data["data"][0]

    assert item["id"] == message.id
    assert item["sender_id"] == sender.id
    assert item["recipient_id"] == recipient.id
    assert item["subject"] == "Sent message"


def test_sent_messages_excludes_deleted_messages(
    client,
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    make_message(
        clinic=clinic,
        sender=sender,
        recipient=recipient,
        deleted_at=datetime.now(timezone.utc),
    )

    response = client.get(
        "/api/messages/sent",
        headers=auth_headers(sender),
    )

    data = assert_success(
        response,
        200,
    )

    assert data["data"] == []


# ============================================================================
# GET MESSAGE
# ============================================================================


def test_get_message_success_as_recipient(
    client,
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic=clinic,
        sender=sender,
        recipient=recipient,
        subject="Get me",
        body="Message body",
    )

    response = client.get(
        f"/api/messages/{message.id}",
        headers=auth_headers(recipient),
    )

    data = assert_success(
        response,
        200,
    )

    item = data["data"]

    assert item["id"] == message.id
    assert item["subject"] == "Get me"
    assert item["body"] == "Message body"


def test_get_message_success_as_sender(
    client,
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic=clinic,
        sender=sender,
        recipient=recipient,
    )

    response = client.get(
        f"/api/messages/{message.id}",
        headers=auth_headers(sender),
    )

    data = assert_success(
        response,
        200,
    )

    assert data["data"]["id"] == message.id


def test_get_message_forbidden_user_is_hidden_as_404(
    client,
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    outsider = make_user(
        clinic=clinic,
        email="message-outsider@example.com",
    )

    message = make_message(
        clinic=clinic,
        sender=sender,
        recipient=recipient,
    )

    response = client.get(
        f"/api/messages/{message.id}",
        headers=auth_headers(outsider),
    )

    assert_error(
        response,
        404,
    )


def test_get_nonexistent_message_returns_404(
    client,
    clinic,
    make_user,
):
    user = make_user(
        clinic=clinic,
        email="message-missing@example.com",
    )

    response = client.get(
        "/api/messages/999999",
        headers=auth_headers(user),
    )

    assert_error(
        response,
        404,
    )


# ============================================================================
# UPDATE
# ============================================================================


def test_update_message_success(
    client,
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic=clinic,
        sender=sender,
        recipient=recipient,
        subject="Original",
        body="Original body",
    )

    response = client.patch(
        f"/api/messages/{message.id}",
        headers=auth_headers(sender),
        json={
            "subject": "Updated subject",
            "body": "Updated body",
            "priority": "urgent",
        },
    )

    data = assert_success(
        response,
        200,
    )

    item = data["data"]

    assert item["id"] == message.id
    assert item["subject"] == "Updated subject"
    assert item["body"] == "Updated body"
    assert item["priority"] == "urgent"


def test_update_message_uses_only_supplied_fields(
    client,
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic=clinic,
        sender=sender,
        recipient=recipient,
        subject="Original",
        body="Original body",
        priority=MessagePriority.NORMAL,
    )

    response = client.patch(
        f"/api/messages/{message.id}",
        headers=auth_headers(sender),
        json={
            "subject": "Only subject changed",
        },
    )

    data = assert_success(
        response,
        200,
    )

    item = data["data"]

    assert item["subject"] == "Only subject changed"
    assert item["body"] == "Original body"
    assert item["priority"] == "normal"


def test_update_message_invalid_subject_returns_422(
    client,
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic=clinic,
        sender=sender,
        recipient=recipient,
    )

    response = client.patch(
        f"/api/messages/{message.id}",
        headers=auth_headers(sender),
        json={
            "subject": "",
        },
    )

    assert_error(
        response,
        422,
    )


def test_update_message_invalid_priority_returns_422(
    client,
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic=clinic,
        sender=sender,
        recipient=recipient,
    )

    response = client.patch(
        f"/api/messages/{message.id}",
        headers=auth_headers(sender),
        json={
            "priority": "invalid",
        },
    )

    assert_error(
        response,
        422,
    )


def test_update_message_not_found_becomes_404(
    client,
    clinic,
    make_user,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        email="update-notfound@example.com",
    )

    def fake_update_message(**kwargs):
        raise NotFoundError("Message not found")

    monkeypatch.setattr(
        message_routes,
        "update_message",
        fake_update_message,
    )

    response = client.patch(
        "/api/messages/999999",
        headers=auth_headers(user),
        json={
            "subject": "Updated",
        },
    )

    data = assert_error(
        response,
        404,
    )

    assert data["error"] == "Message not found"


def test_update_message_conflict_becomes_400(
    client,
    clinic,
    make_user,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        email="update-conflict@example.com",
    )

    def fake_update_message(**kwargs):
        raise ConflictError("Archived messages cannot be updated")

    monkeypatch.setattr(
        message_routes,
        "update_message",
        fake_update_message,
    )

    response = client.patch(
        "/api/messages/1",
        headers=auth_headers(user),
        json={
            "subject": "Updated",
        },
    )

    data = assert_error(
        response,
        400,
    )

    assert data["error"] == "Archived messages cannot be updated"


# ============================================================================
# MARK READ
# ============================================================================


def test_mark_message_read_success(
    client,
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic=clinic,
        sender=sender,
        recipient=recipient,
    )

    response = client.post(
        f"/api/messages/{message.id}/read",
        headers=auth_headers(recipient),
        json={},
    )

    data = assert_success(
        response,
        200,
    )

    item = data["data"]

    assert item["id"] == message.id
    assert item["read_at"] is not None


def test_mark_message_read_by_sender_returns_404(
    client,
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic=clinic,
        sender=sender,
        recipient=recipient,
    )

    response = client.post(
        f"/api/messages/{message.id}/read",
        headers=auth_headers(sender),
        json={},
    )

    assert_error(
        response,
        404,
    )


def test_mark_message_read_validation_error_becomes_400(
    client,
    clinic,
    make_user,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        email="read-validation@example.com",
    )

    def fake_mark_message_read(**kwargs):
        raise ValidationError("Invalid message")

    monkeypatch.setattr(
        message_routes,
        "mark_message_read",
        fake_mark_message_read,
    )

    response = client.post(
        "/api/messages/1/read",
        headers=auth_headers(user),
        json={},
    )

    data = assert_error(
        response,
        400,
    )

    assert data["error"] == "Invalid message"


# ============================================================================
# ARCHIVE
# ============================================================================


def test_archive_message_success(
    client,
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic=clinic,
        sender=sender,
        recipient=recipient,
        status=MessageStatus.SENT,
    )

    response = client.post(
        f"/api/messages/{message.id}/archive",
        headers=auth_headers(sender),
    )

    data = assert_success(
        response,
        200,
    )

    item = data["data"]

    assert item["id"] == message.id
    assert item["status"] == "archived"


def test_archive_message_not_found_becomes_404(
    client,
    clinic,
    make_user,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        email="archive-notfound@example.com",
    )

    def fake_archive_message(**kwargs):
        raise NotFoundError("Message not found")

    monkeypatch.setattr(
        message_routes,
        "archive_message",
        fake_archive_message,
    )

    response = client.post(
        "/api/messages/999999/archive",
        headers=auth_headers(user),
    )

    data = assert_error(
        response,
        404,
    )

    assert data["error"] == "Message not found"


def test_archive_message_conflict_becomes_400(
    client,
    clinic,
    make_user,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        email="archive-conflict@example.com",
    )

    def fake_archive_message(**kwargs):
        raise ConflictError("Message cannot be archived")

    monkeypatch.setattr(
        message_routes,
        "archive_message",
        fake_archive_message,
    )

    response = client.post(
        "/api/messages/1/archive",
        headers=auth_headers(user),
    )

    data = assert_error(
        response,
        400,
    )

    assert data["error"] == "Message cannot be archived"


# ============================================================================
# DELETE
# ============================================================================


def test_delete_message_success(
    client,
    db,
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic=clinic,
        sender=sender,
        recipient=recipient,
    )

    response = client.delete(
        f"/api/messages/{message.id}",
        headers=auth_headers(sender),
    )

    data = assert_success(
        response,
        200,
    )

    item = data["data"]

    assert item["id"] == message.id
    assert item["deleted_at"] is not None

    db.session.refresh(message)

    assert message.deleted_at is not None


def test_delete_message_by_outsider_returns_404(
    client,
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    outsider = make_user(
        clinic=clinic,
        email="delete-outsider@example.com",
    )

    message = make_message(
        clinic=clinic,
        sender=sender,
        recipient=recipient,
    )

    response = client.delete(
        f"/api/messages/{message.id}",
        headers=auth_headers(outsider),
    )

    assert_error(
        response,
        404,
    )


def test_delete_message_not_found_becomes_404(
    client,
    clinic,
    make_user,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        email="delete-notfound@example.com",
    )

    def fake_delete_message(**kwargs):
        raise NotFoundError("Message not found")

    monkeypatch.setattr(
        message_routes,
        "delete_message",
        fake_delete_message,
    )

    response = client.delete(
        "/api/messages/999999",
        headers=auth_headers(user),
    )

    data = assert_error(
        response,
        404,
    )

    assert data["error"] == "Message not found"


# ============================================================================
# THREAD
# ============================================================================


def test_get_message_thread_success(
    client,
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    parent = make_message(
        clinic=clinic,
        sender=sender,
        recipient=recipient,
        subject="Parent",
        body="Parent body",
    )

    reply = make_message(
        clinic=clinic,
        sender=recipient,
        recipient=sender,
        subject="Reply",
        body="Reply body",
        parent_message=parent,
    )

    response = client.get(
        f"/api/messages/{parent.id}/thread",
        headers=auth_headers(sender),
    )

    data = assert_success(
        response,
        200,
    )

    ids = [
        item["id"]
        for item in data["data"]
    ]

    assert parent.id in ids
    assert reply.id in ids


def test_get_message_thread_not_found_becomes_404(
    client,
    clinic,
    make_user,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        email="thread-notfound@example.com",
    )

    def fake_get_message_thread(**kwargs):
        raise NotFoundError("Message not found")

    monkeypatch.setattr(
        message_routes,
        "get_message_thread",
        fake_get_message_thread,
    )

    response = client.get(
        "/api/messages/999999/thread",
        headers=auth_headers(user),
    )

    data = assert_error(
        response,
        404,
    )

    assert data["error"] == "Message not found"


def test_get_message_thread_conflict_becomes_400(
    client,
    clinic,
    make_user,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        email="thread-conflict@example.com",
    )

    def fake_get_message_thread(**kwargs):
        raise ConflictError("Message thread contains a cycle")

    monkeypatch.setattr(
        message_routes,
        "get_message_thread",
        fake_get_message_thread,
    )

    response = client.get(
        "/api/messages/1/thread",
        headers=auth_headers(user),
    )

    data = assert_error(
        response,
        400,
    )

    assert data["error"] == "Message thread contains a cycle"


# ============================================================================
# SERIALIZATION
# ============================================================================


def test_message_response_serializes_enums_and_datetimes(
    client,
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    sent_at = datetime.now(timezone.utc)
    read_at = datetime.now(timezone.utc)

    message = make_message(
        clinic=clinic,
        sender=sender,
        recipient=recipient,
        subject="Serialization",
        body="Serialization body",
        message_type=MessageType.CLINICAL,
        status=MessageStatus.SENT,
        priority=MessagePriority.HIGH,
        sent_at=sent_at,
        read_at=read_at,
    )

    response = client.get(
        f"/api/messages/{message.id}",
        headers=auth_headers(sender),
    )

    data = assert_success(
        response,
        200,
    )

    item = data["data"]

    assert isinstance(item["message_type"], str)
    assert item["message_type"] == "clinical"

    assert isinstance(item["status"], str)
    assert item["status"] == "sent"

    assert isinstance(item["priority"], str)
    assert item["priority"] == "high"

    assert isinstance(item["sent_at"], str)
    assert isinstance(item["read_at"], str)
    assert isinstance(item["created_at"], str)
    assert isinstance(item["updated_at"], str)


# ============================================================================
# TENANT ISOLATION
# ============================================================================


def test_message_from_another_clinic_is_not_accessible(
    client,
    make_clinic,
    make_user,
    make_message,
):
    clinic_a = make_clinic(
        name="Message Route Clinic A",
    )

    clinic_b = make_clinic(
        name="Message Route Clinic B",
    )

    sender_a = make_user(
        clinic=clinic_a,
        email="tenant-sender-a@example.com",
    )

    recipient_a = make_user(
        clinic=clinic_a,
        email="tenant-recipient-a@example.com",
    )

    user_b = make_user(
        clinic=clinic_b,
        email="tenant-user-b@example.com",
    )

    message = make_message(
        clinic=clinic_a,
        sender=sender_a,
        recipient=recipient_a,
        subject="Private clinic message",
    )

    response = client.get(
        f"/api/messages/{message.id}",
        headers=auth_headers(user_b),
    )

    assert_error(
        response,
        404,
    )


def test_message_does_not_appear_in_other_clinic_inbox(
    client,
    make_clinic,
    make_user,
    make_message,
):
    clinic_a = make_clinic(
        name="Inbox Tenant A",
    )

    clinic_b = make_clinic(
        name="Inbox Tenant B",
    )

    sender_a = make_user(
        clinic=clinic_a,
        email="inbox-sender-a@example.com",
    )

    recipient_a = make_user(
        clinic=clinic_a,
        email="inbox-recipient-a@example.com",
    )

    recipient_b = make_user(
        clinic=clinic_b,
        email="inbox-recipient-b@example.com",
    )

    make_message(
        clinic=clinic_a,
        sender=sender_a,
        recipient=recipient_a,
        subject="Clinic A only",
    )

    response = client.get(
        "/api/messages/inbox",
        headers=auth_headers(recipient_b),
    )

    data = assert_success(
        response,
        200,
    )

    assert data["data"] == []


# ============================================================================
# AUTHENTICATED USER RESOLUTION
# ============================================================================


def test_inactive_authenticated_user_is_rejected(
    client,
    clinic,
    make_user,
):
    user = make_user(
        clinic=clinic,
        email="inactive-message-user@example.com",
        is_active=False,
    )

    response = client.get(
        "/api/messages/inbox",
        headers=auth_headers(user),
    )

    data = assert_error(
        response,
        400,
    )

    assert data["error"] == "Authenticated user is inactive"


def test_authenticated_user_without_clinic_is_rejected(
    client,
    make_user,
):
    user = make_user(
        clinic=None,
        email="no-clinic-message-user@example.com",
    )

    response = client.get(
        "/api/messages/inbox",
        headers=auth_headers(user),
    )

    data = assert_error(
        response,
        400,
    )

    assert (
        data["error"]
        == "Authenticated user is not assigned to a clinic"
    )


def test_authenticated_user_that_does_not_exist_returns_404(
    client,
):

    with client.application.app_context():
        token = create_access_token(
            identity="999999",
        )

    response = client.get(
        "/api/messages/inbox",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    data = assert_error(
        response,
        404,
    )

    assert data["error"] == "Authenticated user not found"