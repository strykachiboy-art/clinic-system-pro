from unittest.mock import Mock

import pytest

from app.core.enums.feedback_enums import (
    FeedbackCategory,
    FeedbackPriority,
    FeedbackStatus,
    FeedbackType,
)
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)


BASE_URL = "/api/v1/feedback"


@pytest.fixture()
def feedback_routes():
    import app.modules.feedback.routes.feedback_routes as routes

    return routes


def _auth_headers(auth_headers_for, user):
    return auth_headers_for(user)


def _feedback_payload():
    return {
        "feedback_type": FeedbackType.BUG_REPORT.value,
        "category": FeedbackCategory.USABILITY.value,
        "subject": "Route test feedback",
        "message": "The feedback route should work correctly.",
    }


def test_create_feedback_success(
    client,
    feedback_submitter,
    auth_headers_for,
    feedback_routes,
    feedback,
    monkeypatch,
):
    service = Mock(return_value=feedback)

    monkeypatch.setattr(
        feedback_routes,
        "create_feedback",
        service,
    )

    response = client.post(
        BASE_URL,
        json=_feedback_payload(),
        headers=_auth_headers(
            auth_headers_for,
            feedback_submitter,
        ),
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == feedback.id

    assert service.call_args.kwargs["actor_user_id"] == (
        feedback_submitter.id
    )

    assert "clinic_id" not in service.call_args.kwargs


def test_create_feedback_does_not_accept_client_actor_or_clinic(
    client,
    feedback_submitter,
    auth_headers_for,
    feedback_routes,
    feedback,
    monkeypatch,
):
    service = Mock(return_value=feedback)

    monkeypatch.setattr(
        feedback_routes,
        "create_feedback",
        service,
    )

    payload = _feedback_payload()
    payload["clinic_id"] = 999999
    payload["submitted_by_user_id"] = 999999

    response = client.post(
        BASE_URL,
        json=payload,
        headers=_auth_headers(
            auth_headers_for,
            feedback_submitter,
        ),
    )

    assert response.status_code == 422

    service.assert_not_called()


def test_create_feedback_requires_authentication(
    client,
):
    response = client.post(
        BASE_URL,
        json=_feedback_payload(),
    )

    assert response.status_code == 401


def test_create_feedback_invalid_payload_returns_422(
    client,
    feedback_submitter,
    auth_headers_for,
):
    response = client.post(
        BASE_URL,
        json={
            "feedback_type": "invalid",
            "category": "invalid",
            "subject": "",
            "message": "",
        },
        headers=_auth_headers(
            auth_headers_for,
            feedback_submitter,
        ),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Validation failed"
    assert body["details"]


def test_list_feedback_success(
    client,
    feedback_submitter,
    auth_headers_for,
    feedback_routes,
    feedback,
    monkeypatch,
):
    service = Mock(
        return_value={
            "items": [feedback],
            "total": 1,
            "page": 1,
            "per_page": 50,
            "pages": 1,
            "has_next": False,
            "has_previous": False,
        }
    )

    monkeypatch.setattr(
        feedback_routes,
        "list_feedback",
        service,
    )

    response = client.get(
        BASE_URL,
        headers=_auth_headers(
            auth_headers_for,
            feedback_submitter,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["id"] == feedback.id

    assert service.call_args.kwargs["actor_user_id"] == (
        feedback_submitter.id
    )

    assert service.call_args.kwargs["clinic_id"] is None


def test_list_feedback_forwards_pagination(
    client,
    feedback_submitter,
    auth_headers_for,
    feedback_routes,
    feedback,
    monkeypatch,
):
    service = Mock(
        return_value={
            "items": [feedback],
            "total": 1,
            "page": 2,
            "per_page": 10,
            "pages": 1,
            "has_next": False,
            "has_previous": True,
        }
    )

    monkeypatch.setattr(
        feedback_routes,
        "list_feedback",
        service,
    )

    response = client.get(
        f"{BASE_URL}?page=2&per_page=10",
        headers=_auth_headers(
            auth_headers_for,
            feedback_submitter,
        ),
    )

    assert response.status_code == 200

    query = service.call_args.kwargs["query"]

    assert query.page == 2
    assert query.per_page == 10


def test_list_feedback_rejects_unknown_query_parameter(
    client,
    feedback_submitter,
    auth_headers_for,
):
    response = client.get(
        f"{BASE_URL}?unknown=value",
        headers=_auth_headers(
            auth_headers_for,
            feedback_submitter,
        ),
    )

    assert response.status_code == 422


def test_list_feedback_requires_authentication(
    client,
):
    response = client.get(BASE_URL)

    assert response.status_code == 401


def test_get_feedback_success(
    client,
    feedback,
    feedback_submitter,
    auth_headers_for,
    feedback_routes,
    monkeypatch,
):
    service = Mock(return_value=feedback)

    monkeypatch.setattr(
        feedback_routes,
        "get_feedback_for_actor",
        service,
    )

    response = client.get(
        f"{BASE_URL}/{feedback.id}",
        headers=_auth_headers(
            auth_headers_for,
            feedback_submitter,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == feedback.id

    assert service.call_args.kwargs["actor_user_id"] == (
        feedback_submitter.id
    )

    assert service.call_args.kwargs["feedback_id"] == feedback.id


def test_get_feedback_requires_authentication(
    client,
    feedback,
):
    response = client.get(
        f"{BASE_URL}/{feedback.id}",
    )

    assert response.status_code == 401


def test_get_feedback_rejects_client_supplied_cross_clinic_access(
    client,
    feedback,
    feedback_submitter,
    auth_headers_for,
    feedback_routes,
    monkeypatch,
):
    monkeypatch.setattr(
        feedback_routes,
        "get_feedback_for_actor",
        Mock(
            side_effect=NotFoundError(
                "Feedback 1 not found"
            )
        ),
    )

    response = client.get(
        f"{BASE_URL}/{feedback.id}?clinic_id=999999",
        headers=_auth_headers(
            auth_headers_for,
            feedback_submitter,
        ),
    )

    assert response.status_code == 404


def test_manage_feedback_is_admin_only(
    client,
    feedback,
    feedback_submitter,
    auth_headers_for,
):
    response = client.patch(
        f"{BASE_URL}/{feedback.id}",
        json={
            "status": FeedbackStatus.TRIAGED.value,
        },
        headers=_auth_headers(
            auth_headers_for,
            feedback_submitter,
        ),
    )

    assert response.status_code == 403


def test_manage_feedback_success(
    client,
    feedback,
    feedback_admin,
    auth_headers_for,
    feedback_routes,
    monkeypatch,
):
    feedback.status = FeedbackStatus.TRIAGED
    feedback.priority = FeedbackPriority.HIGH

    service = Mock(return_value=feedback)

    monkeypatch.setattr(
        feedback_routes,
        "manage_feedback",
        service,
    )

    response = client.patch(
        f"{BASE_URL}/{feedback.id}",
        json={
            "status": FeedbackStatus.TRIAGED.value,
            "priority": FeedbackPriority.HIGH.value,
        },
        headers=_auth_headers(
            auth_headers_for,
            feedback_admin,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["status"] == (
        FeedbackStatus.TRIAGED.value
    )
    assert body["data"]["priority"] == (
        FeedbackPriority.HIGH.value
    )

    assert service.call_args.kwargs["actor_user_id"] == (
        feedback_admin.id
    )

    assert service.call_args.kwargs["feedback_id"] == (
        feedback.id
    )


def test_manage_feedback_invalid_payload_returns_422(
    client,
    feedback,
    feedback_admin,
    auth_headers_for,
):
    response = client.patch(
        f"{BASE_URL}/{feedback.id}",
        json={
            "status": "invalid-status",
        },
        headers=_auth_headers(
            auth_headers_for,
            feedback_admin,
        ),
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("route_suffix", "service_name", "message"),
    [
        (
            "resolve",
            "resolve_feedback",
            "Feedback resolved successfully",
        ),
        (
            "reopen",
            "reopen_feedback",
            "Feedback reopened successfully",
        ),
        (
            "close",
            "close_feedback",
            "Feedback closed successfully",
        ),
        (
            "reject",
            "reject_feedback",
            "Feedback rejected successfully",
        ),
    ],
)
def test_feedback_lifecycle_routes(
    client,
    feedback,
    feedback_admin,
    auth_headers_for,
    feedback_routes,
    route_suffix,
    service_name,
    message,
    monkeypatch,
):
    service = Mock(return_value=feedback)

    monkeypatch.setattr(
        feedback_routes,
        service_name,
        service,
    )

    response = client.post(
        (
            f"{BASE_URL}/{feedback.id}"
            f"/{route_suffix}"
        ),
        headers=_auth_headers(
            auth_headers_for,
            feedback_admin,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["message"] == message

    assert service.call_args.kwargs["actor_user_id"] == (
        feedback_admin.id
    )

    assert service.call_args.kwargs["feedback_id"] == (
        feedback.id
    )


@pytest.mark.parametrize(
    "route_suffix",
    [
        "resolve",
        "reopen",
        "close",
        "reject",
    ],
)
def test_feedback_lifecycle_routes_are_admin_only(
    client,
    feedback,
    feedback_submitter,
    auth_headers_for,
    route_suffix,
):
    response = client.post(
        (
            f"{BASE_URL}/{feedback.id}"
            f"/{route_suffix}"
        ),
        headers=_auth_headers(
            auth_headers_for,
            feedback_submitter,
        ),
    )

    assert response.status_code == 403


def test_create_feedback_comment_success(
    client,
    feedback,
    feedback_submitter,
    auth_headers_for,
    feedback_routes,
    feedback_comment,
    monkeypatch,
):
    service = Mock(return_value=feedback_comment)

    monkeypatch.setattr(
        feedback_routes,
        "create_feedback_comment",
        service,
    )

    response = client.post(
        f"{BASE_URL}/{feedback.id}/comments",
        json={
            "body": "A route-created comment",
        },
        headers=_auth_headers(
            auth_headers_for,
            feedback_submitter,
        ),
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == feedback_comment.id

    assert service.call_args.kwargs["actor_user_id"] == (
        feedback_submitter.id
    )

    assert service.call_args.kwargs["feedback_id"] == (
        feedback.id
    )

    payload = service.call_args.kwargs["payload"]

    assert payload.body == "A route-created comment"


def test_create_feedback_comment_requires_authentication(
    client,
    feedback,
):
    response = client.post(
        f"{BASE_URL}/{feedback.id}/comments",
        json={
            "body": "Unauthorized",
        },
    )

    assert response.status_code == 401


def test_create_feedback_comment_invalid_payload_returns_422(
    client,
    feedback,
    feedback_submitter,
    auth_headers_for,
):
    response = client.post(
        f"{BASE_URL}/{feedback.id}/comments",
        json={
            "body": "",
        },
        headers=_auth_headers(
            auth_headers_for,
            feedback_submitter,
        ),
    )

    assert response.status_code == 422


def test_list_feedback_comments_success(
    client,
    feedback,
    feedback_submitter,
    auth_headers_for,
    feedback_routes,
    feedback_comment,
    monkeypatch,
):
    service = Mock(
        return_value={
            "items": [feedback_comment],
            "total": 1,
            "page": 1,
            "per_page": 50,
            "pages": 1,
            "has_next": False,
            "has_previous": False,
        }
    )

    monkeypatch.setattr(
        feedback_routes,
        "list_feedback_comments",
        service,
    )

    response = client.get(
        f"{BASE_URL}/{feedback.id}/comments",
        headers=_auth_headers(
            auth_headers_for,
            feedback_submitter,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["items"][0]["id"] == (
        feedback_comment.id
    )


def test_list_feedback_comments_forwards_pagination(
    client,
    feedback,
    feedback_submitter,
    auth_headers_for,
    feedback_routes,
    feedback_comment,
    monkeypatch,
):
    service = Mock(
        return_value={
            "items": [feedback_comment],
            "total": 1,
            "page": 2,
            "per_page": 10,
            "pages": 2,
            "has_next": False,
            "has_previous": True,
        }
    )

    monkeypatch.setattr(
        feedback_routes,
        "list_feedback_comments",
        service,
    )

    response = client.get(
        (
            f"{BASE_URL}/{feedback.id}/comments"
            "?page=2&per_page=10"
        ),
        headers=_auth_headers(
            auth_headers_for,
            feedback_submitter,
        ),
    )

    assert response.status_code == 200

    assert service.call_args.kwargs["page"] == 2
    assert service.call_args.kwargs["per_page"] == 10


def test_list_feedback_comments_rejects_invalid_pagination(
    client,
    feedback,
    feedback_submitter,
    auth_headers_for,
):
    response = client.get(
        (
            f"{BASE_URL}/{feedback.id}/comments"
            "?page=abc&per_page=xyz"
        ),
        headers=_auth_headers(
            auth_headers_for,
            feedback_submitter,
        ),
    )

    assert response.status_code == 422


def test_get_feedback_comment_success(
    client,
    feedback,
    feedback_submitter,
    feedback_comment,
    auth_headers_for,
    feedback_routes,
    monkeypatch,
):
    service = Mock(return_value=feedback_comment)

    monkeypatch.setattr(
        feedback_routes,
        "get_feedback_comment",
        service,
    )

    response = client.get(
        (
            f"{BASE_URL}/{feedback.id}"
            f"/comments/{feedback_comment.id}"
        ),
        headers=_auth_headers(
            auth_headers_for,
            feedback_submitter,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == feedback_comment.id

    assert service.call_args.kwargs["actor_user_id"] == (
        feedback_submitter.id
    )

    assert service.call_args.kwargs["feedback_id"] == (
        feedback.id
    )

    assert service.call_args.kwargs["comment_id"] == (
        feedback_comment.id
    )


def test_update_feedback_comment_success(
    client,
    feedback,
    feedback_submitter,
    feedback_comment,
    auth_headers_for,
    feedback_routes,
    monkeypatch,
):
    service = Mock(return_value=feedback_comment)

    monkeypatch.setattr(
        feedback_routes,
        "update_feedback_comment",
        service,
    )

    response = client.patch(
        (
            f"{BASE_URL}/{feedback.id}"
            f"/comments/{feedback_comment.id}"
        ),
        json={
            "body": "Updated comment",
        },
        headers=_auth_headers(
            auth_headers_for,
            feedback_submitter,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == feedback_comment.id

    assert service.call_args.kwargs["actor_user_id"] == (
        feedback_submitter.id
    )

    assert service.call_args.kwargs["feedback_id"] == (
        feedback.id
    )

    assert service.call_args.kwargs["comment_id"] == (
        feedback_comment.id
    )

    assert service.call_args.kwargs["body"] == (
        "Updated comment"
    )


def test_update_feedback_comment_rejects_invalid_body(
    client,
    feedback,
    feedback_submitter,
    feedback_comment,
    auth_headers_for,
):
    response = client.patch(
        (
            f"{BASE_URL}/{feedback.id}"
            f"/comments/{feedback_comment.id}"
        ),
        json={
            "body": "   ",
        },
        headers=_auth_headers(
            auth_headers_for,
            feedback_submitter,
        ),
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("exception", "status_code"),
    [
        (NotFoundError("Feedback not found"), 404),
        (ConflictError("Feedback conflict"), 409),
        (ValidationError("Invalid feedback"), 422),
    ],
)
def test_feedback_route_maps_domain_errors(
    client,
    feedback,
    feedback_submitter,
    auth_headers_for,
    feedback_routes,
    exception,
    status_code,
    monkeypatch,
):
    monkeypatch.setattr(
        feedback_routes,
        "get_feedback_for_actor",
        Mock(side_effect=exception),
    )

    response = client.get(
        f"{BASE_URL}/{feedback.id}",
        headers=_auth_headers(
            auth_headers_for,
            feedback_submitter,
        ),
    )

    assert response.status_code == status_code

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == str(exception)


def test_feedback_route_hides_unexpected_exception(
    client,
    feedback,
    feedback_submitter,
    auth_headers_for,
    feedback_routes,
    monkeypatch,
):
    monkeypatch.setattr(
        feedback_routes,
        "get_feedback_for_actor",
        Mock(
            side_effect=RuntimeError(
                "SECRET INTERNAL DETAIL"
            )
        ),
    )

    response = client.get(
        f"{BASE_URL}/{feedback.id}",
        headers=_auth_headers(
            auth_headers_for,
            feedback_submitter,
        ),
    )

    assert response.status_code == 400

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "An unexpected error occurred"
    )

    assert "SECRET INTERNAL DETAIL" not in response.text

@pytest.mark.parametrize(
    "user_fixture",
    [
        "feedback_submitter",
        "feedback_admin",
    ],
)
def test_normal_users_cannot_supply_feedback_clinic_id(
    request,
    client,
    feedback,
    auth_headers_for,
    feedback_routes,
    user_fixture,
    monkeypatch,
):
    user = request.getfixturevalue(user_fixture)

    service = Mock(
        return_value={
            "items": [feedback],
            "total": 1,
            "page": 1,
            "per_page": 50,
            "pages": 1,
            "has_next": False,
            "has_previous": False,
        }
    )

    monkeypatch.setattr(
        feedback_routes,
        "list_feedback",
        service,
    )

    response = client.get(
        f"{BASE_URL}?clinic_id={feedback.clinic_id}",
        headers=_auth_headers(
            auth_headers_for,
            user,
        ),
    )

    assert response.status_code == 404
    service.assert_not_called()


def test_super_admin_can_supply_feedback_clinic_id(
    client,
    feedback,
    feedback_super_admin,
    auth_headers_for,
    feedback_routes,
    monkeypatch,
):
    service = Mock(
        return_value={
            "items": [feedback],
            "total": 1,
            "page": 1,
            "per_page": 50,
            "pages": 1,
            "has_next": False,
            "has_previous": False,
        }
    )

    monkeypatch.setattr(
        feedback_routes,
        "list_feedback",
        service,
    )

    response = client.get(
        f"{BASE_URL}?clinic_id={feedback.clinic_id}",
        headers=_auth_headers(
            auth_headers_for,
            feedback_super_admin,
        ),
    )

    assert response.status_code == 200

    assert service.call_args.kwargs["clinic_id"] == (
        feedback.clinic_id
    )


