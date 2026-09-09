from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask_jwt_extended import create_access_token

from app.core.enums.notification_enums import (
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)


# ============================================================================
# ROUTE MODULE
# ============================================================================

ROUTES_MODULE = "app.core.notifications.routes.notification_route"


@pytest.fixture()
def notification_routes():
    import importlib

    return importlib.import_module(ROUTES_MODULE)


# ============================================================================
# HELPERS
# ============================================================================


def utcnow():
    return datetime.now(timezone.utc)


def notification_obj(
    *,
    id=1,
    clinic_id=1,
    user_id=1,
    title="Test Notification",
    message="This is a test notification.",
    notification_type=NotificationType.SYSTEM,
    priority=NotificationPriority.NORMAL,
    channel=NotificationChannel.IN_APP,
    status=NotificationStatus.PENDING,
    reference_type=None,
    reference_id=None,
    is_read=False,
    read_at=None,
    sent_at=None,
    delivered_at=None,
    failed_at=None,
    error_message=None,
    retry_count=0,
    created_at=None,
    updated_at=None,
):
    """
    Lightweight notification object used to test route
    serialization without invoking the database/service layer.
    """

    now = utcnow()

    return SimpleNamespace(
        id=id,
        clinic_id=clinic_id,
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        priority=priority,
        channel=channel,
        status=status,
        reference_type=reference_type,
        reference_id=reference_id,
        is_read=is_read,
        read_at=read_at,
        sent_at=sent_at,
        delivered_at=delivered_at,
        failed_at=failed_at,
        error_message=error_message,
        retry_count=retry_count,
        created_at=(
            created_at
            if created_at is not None
            else now
        ),
        updated_at=(
            updated_at
            if updated_at is not None
            else now
        ),
    )


def valid_create_payload(user_id):
    return {
        "user_id": user_id,
        "title": "Appointment Reminder",
        "message": (
            "Your appointment is scheduled for tomorrow."
        ),
        "notification_type": NotificationType.SYSTEM.value,
        "priority": NotificationPriority.NORMAL.value,
        "channel": NotificationChannel.IN_APP.value,
        "reference_type": "Appointment",
        "reference_id": 123,
    }


def paginated_result(
    items,
    *,
    page=1,
    per_page=50,
    total=None,
    pages=None,
    has_next=False,
    has_prev=False,
):
    """
    Build the exact service-layer pagination contract expected
    by the notification route.
    """

    if total is None:
        total = len(items)

    if pages is None:
        pages = (
            (total + per_page - 1) // per_page
            if total
            else 0
        )

    return {
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "has_next": has_next,
        "has_prev": has_prev,
    }


def assert_success_response(response, status_code):
    body = response.get_json()

    assert response.status_code == status_code, body
    assert body["success"] is True
    assert "data" in body

    return body


def assert_error_response(response, status_code):
    body = response.get_json()

    assert response.status_code == status_code, body
    assert body["success"] is False
    assert "error" in body

    return body


# ============================================================================
# CREATE NOTIFICATION
# ============================================================================


def test_create_notification_success(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    created = notification_obj(
        id=42,
        clinic_id=user.clinic_id,
        user_id=user.id,
        title="Appointment Reminder",
        message=(
            "Your appointment is scheduled for tomorrow."
        ),
        notification_type=NotificationType.SYSTEM,
        priority=NotificationPriority.NORMAL,
        channel=NotificationChannel.IN_APP,
        status=NotificationStatus.PENDING,
        reference_type="Appointment",
        reference_id=123,
    )

    service = Mock(return_value=created)

    monkeypatch.setattr(
        notification_routes,
        "create_notification",
        service,
    )

    response = client.post(
        "/api/notifications/",
        json=valid_create_payload(user.id),
        headers=auth_headers_for(user),
    )

    body = assert_success_response(response, 201)

    data = body["data"]

    assert data["id"] == 42
    assert data["clinic_id"] == user.clinic_id
    assert data["user_id"] == user.id
    assert data["title"] == "Appointment Reminder"
    assert data["message"] == (
        "Your appointment is scheduled for tomorrow."
    )
    assert data["notification_type"] == (
        NotificationType.SYSTEM.value
    )
    assert data["priority"] == (
        NotificationPriority.NORMAL.value
    )
    assert data["channel"] == (
        NotificationChannel.IN_APP.value
    )
    assert data["status"] == (
        NotificationStatus.PENDING.value
    )
    assert data["reference_type"] == "Appointment"
    assert data["reference_id"] == 123
    assert data["is_read"] is False
    assert data["retry_count"] == 0

    service.assert_called_once_with(
        clinic_id=user.clinic_id,
        user_id=user.id,
        title="Appointment Reminder",
        message=(
            "Your appointment is scheduled for tomorrow."
        ),
        notification_type=NotificationType.SYSTEM.value,
        priority=NotificationPriority.NORMAL.value,
        channel=NotificationChannel.IN_APP.value,
        reference_type="Appointment",
        reference_id=123,
    )


def test_create_notification_uses_authenticated_clinic(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    created = notification_obj(
        clinic_id=user.clinic_id,
        user_id=user.id,
    )

    service = Mock(return_value=created)

    monkeypatch.setattr(
        notification_routes,
        "create_notification",
        service,
    )

    response = client.post(
        "/api/notifications/",
        json=valid_create_payload(user.id),
        headers=auth_headers_for(user),
    )

    assert response.status_code == 201

    assert (
        service.call_args.kwargs["clinic_id"]
        == user.clinic_id
    )


def test_create_notification_rejects_client_clinic_id(
    client,
    user,
    auth_headers_for,
):
    payload = valid_create_payload(user.id)
    payload["clinic_id"] = user.clinic_id + 999

    response = client.post(
        "/api/notifications/",
        json=payload,
        headers=auth_headers_for(user),
    )

    body = assert_error_response(response, 422)

    assert body["success"] is False
    assert "error" in body


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", NotificationStatus.DELIVERED.value),
        ("is_read", True),
        ("retry_count", 99),
        ("sent_at", "2026-01-01T00:00:00Z"),
        ("delivered_at", "2026-01-01T00:00:00Z"),
        ("failed_at", "2026-01-01T00:00:00Z"),
        ("error_message", "fake provider error"),
    ],
)
def test_create_notification_rejects_protected_fields(
    client,
    user,
    auth_headers_for,
    field,
    value,
):
    payload = valid_create_payload(user.id)
    payload[field] = value

    response = client.post(
        "/api/notifications/",
        json=payload,
        headers=auth_headers_for(user),
    )

    body = assert_error_response(response, 422)

    assert body["success"] is False
    assert "error" in body


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {
            "user_id": 1,
        },
        {
            "user_id": 1,
            "title": "",
            "message": "Message",
            "notification_type": (
                NotificationType.SYSTEM.value
            ),
        },
        {
            "user_id": 1,
            "title": "Title",
            "message": "",
            "notification_type": (
                NotificationType.SYSTEM.value
            ),
        },
        {
            "user_id": 0,
            "title": "Title",
            "message": "Message",
            "notification_type": (
                NotificationType.SYSTEM.value
            ),
        },
        {
            "user_id": -1,
            "title": "Title",
            "message": "Message",
            "notification_type": (
                NotificationType.SYSTEM.value
            ),
        },
        {
            "user_id": 1,
            "title": "Title",
            "message": "Message",
            "notification_type": "invalid-type",
        },
        {
            "user_id": 1,
            "title": "Title",
            "message": "Message",
            "notification_type": (
                NotificationType.SYSTEM.value
            ),
            "priority": "invalid-priority",
        },
        {
            "user_id": 1,
            "title": "Title",
            "message": "Message",
            "notification_type": (
                NotificationType.SYSTEM.value
            ),
            "channel": "invalid-channel",
        },
    ],
)
def test_create_notification_rejects_invalid_payload(
    client,
    user,
    auth_headers_for,
    payload,
):
    response = client.post(
        "/api/notifications/",
        json=payload,
        headers=auth_headers_for(user),
    )

    body = assert_error_response(response, 422)

    assert body["success"] is False
    assert "error" in body


def test_create_notification_not_found(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    service = Mock(
        side_effect=NotFoundError(
            "Target user not found"
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "create_notification",
        service,
    )

    response = client.post(
        "/api/notifications/",
        json=valid_create_payload(user.id),
        headers=auth_headers_for(user),
    )

    body = assert_error_response(response, 404)

    assert body["error"] == "Target user not found"


@pytest.mark.parametrize(
    "exception",
    [
        ValidationError("Invalid notification"),
        ConflictError("Notification conflict"),
    ],
)
def test_create_notification_domain_error(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
    exception,
):
    service = Mock(side_effect=exception)

    monkeypatch.setattr(
        notification_routes,
        "create_notification",
        service,
    )

    response = client.post(
        "/api/notifications/",
        json=valid_create_payload(user.id),
        headers=auth_headers_for(user),
    )

    body = assert_error_response(response, 400)

    assert body["error"] == str(exception)


# ============================================================================
# LIST NOTIFICATIONS
# ============================================================================


def test_list_notifications_success(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    notifications = [
        notification_obj(
            id=2,
            clinic_id=user.clinic_id,
            user_id=user.id,
            title="Second",
        ),
        notification_obj(
            id=1,
            clinic_id=user.clinic_id,
            user_id=user.id,
            title="First",
        ),
    ]

    service = Mock(
        return_value=paginated_result(
            notifications,
            page=1,
            per_page=50,
            total=2,
            pages=1,
            has_next=False,
            has_prev=False,
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "get_user_notifications",
        service,
    )

    response = client.get(
        "/api/notifications/",
        headers=auth_headers_for(user),
    )

    body = assert_success_response(response, 200)

    data = body["data"]

    assert len(data["items"]) == 2
    assert data["items"][0]["id"] == 2
    assert data["items"][1]["id"] == 1

    assert data["page"] == 1
    assert data["per_page"] == 50
    assert data["total"] == 2
    assert data["pages"] == 1
    assert data["has_next"] is False
    assert data["has_prev"] is False

    service.assert_called_once_with(
        user_id=user.id,
        clinic_id=user.clinic_id,
        unread_only=False,
        page=1,
        per_page=50,
    )


def test_list_notifications_custom_pagination(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    notifications = [
        notification_obj(
            id=4,
            clinic_id=user.clinic_id,
            user_id=user.id,
        ),
        notification_obj(
            id=3,
            clinic_id=user.clinic_id,
            user_id=user.id,
        ),
    ]

    service = Mock(
        return_value=paginated_result(
            notifications,
            page=2,
            per_page=2,
            total=5,
            pages=3,
            has_next=True,
            has_prev=True,
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "get_user_notifications",
        service,
    )

    response = client.get(
        "/api/notifications/?page=2&per_page=2",
        headers=auth_headers_for(user),
    )

    body = assert_success_response(response, 200)

    data = body["data"]

    assert data["page"] == 2
    assert data["per_page"] == 2
    assert data["total"] == 5
    assert data["pages"] == 3
    assert data["has_next"] is True
    assert data["has_prev"] is True

    assert [
        item["id"]
        for item in data["items"]
    ] == [4, 3]

    service.assert_called_once_with(
        user_id=user.id,
        clinic_id=user.clinic_id,
        unread_only=False,
        page=2,
        per_page=2,
    )


def test_list_notifications_first_page(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    notifications = [
        notification_obj(id=5),
        notification_obj(id=4),
    ]

    service = Mock(
        return_value=paginated_result(
            notifications,
            page=1,
            per_page=2,
            total=5,
            pages=3,
            has_next=True,
            has_prev=False,
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "get_user_notifications",
        service,
    )

    response = client.get(
        "/api/notifications/?page=1&per_page=2",
        headers=auth_headers_for(user),
    )

    data = response.get_json()["data"]

    assert data["page"] == 1
    assert data["has_next"] is True
    assert data["has_prev"] is False
    assert len(data["items"]) == 2

    service.assert_called_once_with(
        user_id=user.id,
        clinic_id=user.clinic_id,
        unread_only=False,
        page=1,
        per_page=2,
    )


def test_list_notifications_middle_page(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    notifications = [
        notification_obj(id=3),
        notification_obj(id=2),
    ]

    service = Mock(
        return_value=paginated_result(
            notifications,
            page=2,
            per_page=2,
            total=5,
            pages=3,
            has_next=True,
            has_prev=True,
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "get_user_notifications",
        service,
    )

    response = client.get(
        "/api/notifications/?page=2&per_page=2",
        headers=auth_headers_for(user),
    )

    data = response.get_json()["data"]

    assert data["page"] == 2
    assert data["has_next"] is True
    assert data["has_prev"] is True

    assert [
        item["id"]
        for item in data["items"]
    ] == [3, 2]


def test_list_notifications_last_page(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    notification = notification_obj(id=1)

    service = Mock(
        return_value=paginated_result(
            [notification],
            page=3,
            per_page=2,
            total=5,
            pages=3,
            has_next=False,
            has_prev=True,
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "get_user_notifications",
        service,
    )

    response = client.get(
        "/api/notifications/?page=3&per_page=2",
        headers=auth_headers_for(user),
    )

    data = response.get_json()["data"]

    assert data["page"] == 3
    assert data["has_next"] is False
    assert data["has_prev"] is True
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == 1


def test_list_notifications_empty_page(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    service = Mock(
        return_value=paginated_result(
            [],
            page=2,
            per_page=2,
            total=2,
            pages=1,
            has_next=False,
            has_prev=True,
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "get_user_notifications",
        service,
    )

    response = client.get(
        "/api/notifications/?page=2&per_page=2",
        headers=auth_headers_for(user),
    )

    body = assert_success_response(response, 200)

    data = body["data"]

    assert data["items"] == []
    assert data["page"] == 2
    assert data["per_page"] == 2
    assert data["total"] == 2
    assert data["pages"] == 1
    assert data["has_next"] is False
    assert data["has_prev"] is True


def test_list_notifications_empty(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    service = Mock(
        return_value=paginated_result(
            [],
            page=1,
            per_page=50,
            total=0,
            pages=0,
            has_next=False,
            has_prev=False,
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "get_user_notifications",
        service,
    )

    response = client.get(
        "/api/notifications/",
        headers=auth_headers_for(user),
    )

    body = assert_success_response(response, 200)

    data = body["data"]

    assert data["items"] == []
    assert data["page"] == 1
    assert data["per_page"] == 50
    assert data["total"] == 0
    assert data["pages"] == 0
    assert data["has_next"] is False
    assert data["has_prev"] is False

    service.assert_called_once_with(
        user_id=user.id,
        clinic_id=user.clinic_id,
        unread_only=False,
        page=1,
        per_page=50,
    )


def test_list_notifications_not_found(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    service = Mock(
        side_effect=NotFoundError(
            "User not found"
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "get_user_notifications",
        service,
    )

    response = client.get(
        "/api/notifications/",
        headers=auth_headers_for(user),
    )

    body = assert_error_response(response, 404)

    assert body["error"] == "User not found"


def test_list_notifications_domain_error(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    service = Mock(
        side_effect=ValidationError(
            "Invalid notification scope"
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "get_user_notifications",
        service,
    )

    response = client.get(
        "/api/notifications/",
        headers=auth_headers_for(user),
    )

    body = assert_error_response(response, 400)

    assert body["error"] == (
        "Invalid notification scope"
    )


@pytest.mark.parametrize(
    "query",
    [
        "?page=0",
        "?page=-1",
        "?page=abc",
        "?per_page=0",
        "?per_page=-1",
        "?per_page=501",
        "?per_page=abc",
    ],
)
def test_list_notifications_rejects_invalid_pagination(
    client,
    user,
    auth_headers_for,
    query,
):
    response = client.get(
        f"/api/notifications/{query}",
        headers=auth_headers_for(user),
    )

    body = assert_error_response(response, 422)

    assert body["success"] is False


def test_list_notifications_allows_max_per_page(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    service = Mock(
        return_value=paginated_result(
            [],
            page=1,
            per_page=500,
            total=0,
            pages=0,
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "get_user_notifications",
        service,
    )

    response = client.get(
        "/api/notifications/?per_page=500",
        headers=auth_headers_for(user),
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert data["per_page"] == 500

    service.assert_called_once_with(
        user_id=user.id,
        clinic_id=user.clinic_id,
        unread_only=False,
        page=1,
        per_page=500,
    )


# ============================================================================
# LIST UNREAD NOTIFICATIONS
# ============================================================================


def test_list_unread_notifications_success(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    unread = [
        notification_obj(
            id=10,
            clinic_id=user.clinic_id,
            user_id=user.id,
            is_read=False,
            status=NotificationStatus.PENDING,
        ),
    ]

    service = Mock(
        return_value=paginated_result(
            unread,
            page=1,
            per_page=50,
            total=1,
            pages=1,
            has_next=False,
            has_prev=False,
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "get_user_notifications",
        service,
    )

    response = client.get(
        "/api/notifications/unread",
        headers=auth_headers_for(user),
    )

    body = assert_success_response(response, 200)

    data = body["data"]

    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == 10
    assert data["items"][0]["is_read"] is False

    assert data["page"] == 1
    assert data["per_page"] == 50
    assert data["total"] == 1
    assert data["pages"] == 1
    assert data["has_next"] is False
    assert data["has_prev"] is False

    service.assert_called_once_with(
        user_id=user.id,
        clinic_id=user.clinic_id,
        unread_only=True,
        page=1,
        per_page=50,
    )


def test_list_unread_notifications_custom_pagination(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    unread = [
        notification_obj(
            id=8,
            clinic_id=user.clinic_id,
            user_id=user.id,
            is_read=False,
        ),
        notification_obj(
            id=7,
            clinic_id=user.clinic_id,
            user_id=user.id,
            is_read=False,
        ),
    ]

    service = Mock(
        return_value=paginated_result(
            unread,
            page=2,
            per_page=2,
            total=5,
            pages=3,
            has_next=True,
            has_prev=True,
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "get_user_notifications",
        service,
    )

    response = client.get(
        "/api/notifications/unread?page=2&per_page=2",
        headers=auth_headers_for(user),
    )

    body = assert_success_response(response, 200)

    data = body["data"]

    assert data["page"] == 2
    assert data["per_page"] == 2
    assert data["total"] == 5
    assert data["pages"] == 3
    assert data["has_next"] is True
    assert data["has_prev"] is True

    assert [
        item["id"]
        for item in data["items"]
    ] == [8, 7]

    service.assert_called_once_with(
        user_id=user.id,
        clinic_id=user.clinic_id,
        unread_only=True,
        page=2,
        per_page=2,
    )


def test_list_unread_notifications_empty(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    service = Mock(
        return_value=paginated_result(
            [],
            page=1,
            per_page=50,
            total=0,
            pages=0,
            has_next=False,
            has_prev=False,
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "get_user_notifications",
        service,
    )

    response = client.get(
        "/api/notifications/unread",
        headers=auth_headers_for(user),
    )

    body = assert_success_response(response, 200)

    data = body["data"]

    assert data["items"] == []
    assert data["total"] == 0
    assert data["pages"] == 0
    assert data["has_next"] is False
    assert data["has_prev"] is False

    service.assert_called_once_with(
        user_id=user.id,
        clinic_id=user.clinic_id,
        unread_only=True,
        page=1,
        per_page=50,
    )


@pytest.mark.parametrize(
    "query",
    [
        "?page=0",
        "?page=-1",
        "?page=abc",
        "?per_page=0",
        "?per_page=-1",
        "?per_page=501",
        "?per_page=abc",
    ],
)
def test_list_unread_notifications_rejects_invalid_pagination(
    client,
    user,
    auth_headers_for,
    query,
):
    response = client.get(
        f"/api/notifications/unread{query}",
        headers=auth_headers_for(user),
    )

    body = assert_error_response(response, 422)

    assert body["success"] is False


def test_list_unread_notifications_not_found(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    service = Mock(
        side_effect=NotFoundError(
            "User not found"
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "get_user_notifications",
        service,
    )

    response = client.get(
        "/api/notifications/unread",
        headers=auth_headers_for(user),
    )

    body = assert_error_response(response, 404)

    assert body["error"] == "User not found"


def test_list_unread_notifications_domain_error(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    service = Mock(
        side_effect=ValidationError(
            "Invalid user"
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "get_user_notifications",
        service,
    )

    response = client.get(
        "/api/notifications/unread",
        headers=auth_headers_for(user),
    )

    body = assert_error_response(response, 400)

    assert body["error"] == "Invalid user"


# ============================================================================
# GET SINGLE NOTIFICATION
# ============================================================================


def test_get_notification_success(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    notification = notification_obj(
        id=55,
        clinic_id=user.clinic_id,
        user_id=user.id,
        title="Important Notification",
        message="Important message",
    )

    service = Mock(return_value=notification)

    monkeypatch.setattr(
        notification_routes,
        "get_notification_for_user",
        service,
    )

    response = client.get(
        "/api/notifications/55",
        headers=auth_headers_for(user),
    )

    body = assert_success_response(response, 200)

    data = body["data"]

    assert data["id"] == 55
    assert data["clinic_id"] == user.clinic_id
    assert data["user_id"] == user.id
    assert data["title"] == "Important Notification"
    assert data["message"] == "Important message"

    service.assert_called_once_with(
        notification_id=55,
        user_id=user.id,
        clinic_id=user.clinic_id,
    )


def test_get_notification_not_found(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    service = Mock(
        side_effect=NotFoundError(
            "Notification not found"
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "get_notification_for_user",
        service,
    )

    response = client.get(
        "/api/notifications/999999",
        headers=auth_headers_for(user),
    )

    body = assert_error_response(response, 404)

    assert body["error"] == "Notification not found"


def test_get_notification_domain_error(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    service = Mock(
        side_effect=ConflictError(
            "Notification conflict"
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "get_notification_for_user",
        service,
    )

    response = client.get(
        "/api/notifications/10",
        headers=auth_headers_for(user),
    )

    body = assert_error_response(response, 400)

    assert body["error"] == "Notification conflict"


# ============================================================================
# MARK ONE AS READ
# ============================================================================


def test_mark_notification_read_success(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    read_at = utcnow()

    notification = notification_obj(
        id=77,
        clinic_id=user.clinic_id,
        user_id=user.id,
        is_read=True,
        status=NotificationStatus.READ,
        read_at=read_at,
    )

    service = Mock(return_value=notification)

    monkeypatch.setattr(
        notification_routes,
        "mark_notification_read",
        service,
    )

    response = client.post(
        "/api/notifications/77/read",
        json={},
        headers=auth_headers_for(user),
    )

    body = assert_success_response(response, 200)

    data = body["data"]

    assert data["id"] == 77
    assert data["is_read"] is True
    assert data["status"] == NotificationStatus.READ.value
    assert data["read_at"] is not None

    service.assert_called_once_with(
        notification_id=77,
        user_id=user.id,
        clinic_id=user.clinic_id,
    )


def test_mark_notification_read_rejects_extra_fields(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/notifications/77/read",
        json={
            "unexpected": "field",
        },
        headers=auth_headers_for(user),
    )

    body = assert_error_response(response, 422)

    assert body["success"] is False
    assert "error" in body


def test_mark_notification_read_not_found(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    service = Mock(
        side_effect=NotFoundError(
            "Notification not found"
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "mark_notification_read",
        service,
    )

    response = client.post(
        "/api/notifications/77/read",
        json={},
        headers=auth_headers_for(user),
    )

    body = assert_error_response(response, 404)

    assert body["error"] == "Notification not found"


def test_mark_notification_read_domain_error(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    service = Mock(
        side_effect=ConflictError(
            "Notification conflict"
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "mark_notification_read",
        service,
    )

    response = client.post(
        "/api/notifications/77/read",
        json={},
        headers=auth_headers_for(user),
    )

    body = assert_error_response(response, 400)

    assert body["error"] == "Notification conflict"


# ============================================================================
# MARK ALL AS READ
# ============================================================================


def test_mark_all_notifications_read_success(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    service = Mock(return_value=7)

    monkeypatch.setattr(
        notification_routes,
        "mark_all_notifications_read",
        service,
    )

    response = client.post(
        "/api/notifications/read-all",
        json={},
        headers=auth_headers_for(user),
    )

    body = assert_success_response(response, 200)

    assert body["data"]["updated_count"] == 7

    service.assert_called_once_with(
        user_id=user.id,
        clinic_id=user.clinic_id,
    )


def test_mark_all_notifications_read_zero(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    service = Mock(return_value=0)

    monkeypatch.setattr(
        notification_routes,
        "mark_all_notifications_read",
        service,
    )

    response = client.post(
        "/api/notifications/read-all",
        json={},
        headers=auth_headers_for(user),
    )

    body = assert_success_response(response, 200)

    assert body["data"]["updated_count"] == 0

    service.assert_called_once_with(
        user_id=user.id,
        clinic_id=user.clinic_id,
    )


def test_mark_all_notifications_read_rejects_extra_fields(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/notifications/read-all",
        json={
            "unexpected": "field",
        },
        headers=auth_headers_for(user),
    )

    body = assert_error_response(response, 422)

    assert body["success"] is False
    assert "error" in body


def test_mark_all_notifications_read_not_found(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    service = Mock(
        side_effect=NotFoundError(
            "User not found"
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "mark_all_notifications_read",
        service,
    )

    response = client.post(
        "/api/notifications/read-all",
        json={},
        headers=auth_headers_for(user),
    )

    body = assert_error_response(response, 404)

    assert body["error"] == "User not found"


def test_mark_all_notifications_read_domain_error(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    service = Mock(
        side_effect=ValidationError(
            "Invalid user"
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "mark_all_notifications_read",
        service,
    )

    response = client.post(
        "/api/notifications/read-all",
        json={},
        headers=auth_headers_for(user),
    )

    body = assert_error_response(response, 400)

    assert body["error"] == "Invalid user"


# ============================================================================
# AUTHENTICATION
# ============================================================================


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/notifications/"),
        ("get", "/api/notifications/unread"),
        ("get", "/api/notifications/1"),
        ("post", "/api/notifications/"),
        ("post", "/api/notifications/1/read"),
        ("post", "/api/notifications/read-all"),
    ],
)
def test_notification_routes_require_authentication(
    client,
    assert_unauthorized,
    method,
    path,
):
    if method == "post":
        response = client.post(
            path,
            json={},
        )
    else:
        response = client.get(path)

    assert_unauthorized(response)


def test_authenticated_user_must_exist(
    app,
    client,
    assert_domain_error,
):
    with app.test_request_context():
        token = create_access_token(
            identity="999999999",
            additional_claims={
                "role": "admin",
            },
        )

    response = client.get(
        "/api/notifications/",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    body = assert_domain_error(response, 404)

    assert body["error"] == (
        "Authenticated user not found"
    )


def test_authenticated_user_identity_must_be_integer(
    app,
    client,
    assert_domain_error,
):
    with app.test_request_context():
        token = create_access_token(
            identity="not-an-integer",
            additional_claims={
                "role": "admin",
            },
        )

    response = client.get(
        "/api/notifications/",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    body = assert_domain_error(response, 400)

    assert body["error"] == (
        "Invalid authenticated user identity"
    )


def test_inactive_authenticated_user_is_rejected(
    client,
    make_user,
    clinic,
    auth_headers_for,
    assert_domain_error,
):
    inactive_user = make_user(
        clinic,
        is_active=False,
    )

    response = client.get(
        "/api/notifications/",
        headers=auth_headers_for(inactive_user),
    )

    body = assert_domain_error(response, 400)

    assert body["error"] == (
        "Authenticated user is inactive"
    )


def test_authenticated_user_without_clinic_is_rejected(
    client,
    make_user,
    auth_headers_for,
    assert_domain_error,
):
    user_without_clinic = make_user(None)

    response = client.get(
        "/api/notifications/",
        headers=auth_headers_for(
            user_without_clinic
        ),
    )

    body = assert_domain_error(response, 400)

    assert body["error"] == (
        "Authenticated user is not assigned to a clinic"
    )


# ============================================================================
# USER / TENANT ISOLATION
# ============================================================================


def test_create_notification_cannot_override_authenticated_clinic(
    client,
    user,
    auth_headers_for,
):
    payload = valid_create_payload(user.id)
    payload["clinic_id"] = user.clinic_id + 500

    response = client.post(
        "/api/notifications/",
        json=payload,
        headers=auth_headers_for(user),
    )

    body = assert_error_response(response, 422)

    assert body["success"] is False


def test_get_notification_passes_authenticated_user_and_clinic(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    service = Mock(
        return_value=notification_obj(
            id=15,
            clinic_id=user.clinic_id,
            user_id=user.id,
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "get_notification_for_user",
        service,
    )

    response = client.get(
        "/api/notifications/15",
        headers=auth_headers_for(user),
    )

    assert response.status_code == 200

    service.assert_called_once_with(
        notification_id=15,
        user_id=user.id,
        clinic_id=user.clinic_id,
    )


def test_list_notifications_passes_authenticated_user_and_clinic(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    service = Mock(
        return_value=paginated_result(
            [],
            page=1,
            per_page=50,
            total=0,
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "get_user_notifications",
        service,
    )

    response = client.get(
        "/api/notifications/",
        headers=auth_headers_for(user),
    )

    assert response.status_code == 200

    service.assert_called_once_with(
        user_id=user.id,
        clinic_id=user.clinic_id,
        unread_only=False,
        page=1,
        per_page=50,
    )


def test_unread_notifications_pass_authenticated_user_and_clinic(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    service = Mock(
        return_value=paginated_result(
            [],
            page=1,
            per_page=50,
            total=0,
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "get_user_notifications",
        service,
    )

    response = client.get(
        "/api/notifications/unread",
        headers=auth_headers_for(user),
    )

    assert response.status_code == 200

    service.assert_called_once_with(
        user_id=user.id,
        clinic_id=user.clinic_id,
        unread_only=True,
        page=1,
        per_page=50,
    )


def test_mark_notification_read_passes_authenticated_user_and_clinic(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    service = Mock(
        return_value=notification_obj(
            id=15,
            clinic_id=user.clinic_id,
            user_id=user.id,
            is_read=True,
            status=NotificationStatus.READ,
            read_at=utcnow(),
        )
    )

    monkeypatch.setattr(
        notification_routes,
        "mark_notification_read",
        service,
    )

    response = client.post(
        "/api/notifications/15/read",
        json={},
        headers=auth_headers_for(user),
    )

    assert response.status_code == 200

    service.assert_called_once_with(
        notification_id=15,
        user_id=user.id,
        clinic_id=user.clinic_id,
    )


def test_mark_all_passes_authenticated_user_and_clinic(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    service = Mock(return_value=3)

    monkeypatch.setattr(
        notification_routes,
        "mark_all_notifications_read",
        service,
    )

    response = client.post(
        "/api/notifications/read-all",
        json={},
        headers=auth_headers_for(user),
    )

    assert response.status_code == 200

    service.assert_called_once_with(
        user_id=user.id,
        clinic_id=user.clinic_id,
    )


# ============================================================================
# RESPONSE SERIALIZATION
# ============================================================================


def test_notification_response_serializes_optional_fields(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    notification = notification_obj(
        id=88,
        clinic_id=user.clinic_id,
        user_id=user.id,
        title="Minimal",
        message="Minimal notification",
        reference_type=None,
        reference_id=None,
        read_at=None,
        sent_at=None,
        delivered_at=None,
        failed_at=None,
        error_message=None,
    )

    service = Mock(
        return_value=notification
    )

    monkeypatch.setattr(
        notification_routes,
        "get_notification_for_user",
        service,
    )

    response = client.get(
        "/api/notifications/88",
        headers=auth_headers_for(user),
    )

    body = assert_success_response(response, 200)

    data = body["data"]

    assert data["id"] == 88
    assert data["reference_type"] is None
    assert data["reference_id"] is None
    assert data["read_at"] is None
    assert data["sent_at"] is None
    assert data["delivered_at"] is None
    assert data["failed_at"] is None
    assert data["error_message"] is None


def test_notification_response_serializes_all_timestamps(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    created_at = utcnow()
    updated_at = utcnow()
    read_at = utcnow()
    sent_at = utcnow()
    delivered_at = utcnow()

    notification = notification_obj(
        id=91,
        clinic_id=user.clinic_id,
        user_id=user.id,
        is_read=True,
        status=NotificationStatus.READ,
        read_at=read_at,
        sent_at=sent_at,
        delivered_at=delivered_at,
        created_at=created_at,
        updated_at=updated_at,
    )

    service = Mock(
        return_value=notification
    )

    monkeypatch.setattr(
        notification_routes,
        "get_notification_for_user",
        service,
    )

    response = client.get(
        "/api/notifications/91",
        headers=auth_headers_for(user),
    )

    body = assert_success_response(response, 200)

    data = body["data"]

    assert data["read_at"] == read_at.isoformat()
    assert data["sent_at"] == sent_at.isoformat()
    assert data["delivered_at"] == (
        delivered_at.isoformat()
    )
    assert data["created_at"] == (
        created_at.isoformat()
    )
    assert data["updated_at"] == (
        updated_at.isoformat()
    )


def test_notification_response_serializes_failed_notification(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    failed_at = utcnow()

    notification = notification_obj(
        id=89,
        clinic_id=user.clinic_id,
        user_id=user.id,
        status=NotificationStatus.FAILED,
        channel=NotificationChannel.EMAIL,
        error_message="Provider unavailable",
        retry_count=3,
        failed_at=failed_at,
    )

    service = Mock(
        return_value=notification
    )

    monkeypatch.setattr(
        notification_routes,
        "get_notification_for_user",
        service,
    )

    response = client.get(
        "/api/notifications/89",
        headers=auth_headers_for(user),
    )

    body = assert_success_response(response, 200)

    data = body["data"]

    assert data["status"] == (
        NotificationStatus.FAILED.value
    )
    assert data["channel"] == (
        NotificationChannel.EMAIL.value
    )
    assert data["error_message"] == (
        "Provider unavailable"
    )
    assert data["retry_count"] == 3
    assert data["failed_at"] == (
        failed_at.isoformat()
    )


def test_notification_response_serializes_read_notification(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    notification_routes,
):
    read_at = utcnow()

    notification = notification_obj(
        id=90,
        clinic_id=user.clinic_id,
        user_id=user.id,
        is_read=True,
        status=NotificationStatus.READ,
        read_at=read_at,
    )

    service = Mock(
        return_value=notification
    )

    monkeypatch.setattr(
        notification_routes,
        "get_notification_for_user",
        service,
    )

    response = client.get(
        "/api/notifications/90",
        headers=auth_headers_for(user),
    )

    body = assert_success_response(response, 200)

    data = body["data"]

    assert data["is_read"] is True
    assert data["status"] == (
        NotificationStatus.READ.value
    )
    assert data["read_at"] == read_at.isoformat()