import pytest

from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.feedback.schemas.feedback_comment_schema import (
    FeedbackCommentCreateSchema,
)
from app.modules.feedback.services import feedback_comment_service


def test_create_feedback_comment_allows_feedback_submitter(
    clinic,
    feedback,
    feedback_submitter,
):
    payload = FeedbackCommentCreateSchema(
        body="This is an authorized comment.",
    )

    comment = feedback_comment_service.create_feedback_comment(
        actor_user_id=feedback_submitter.id,
        feedback_id=feedback.id,
        payload=payload,
        clinic_id=clinic.id,
    )

    assert comment.id is not None
    assert comment.feedback_id == feedback.id
    assert comment.author_user_id == feedback_submitter.id
    assert comment.body == "This is an authorized comment."


def test_create_feedback_comment_allows_active_staff(
    clinic,
    feedback,
    feedback_staff,
):
    payload = FeedbackCommentCreateSchema(
        body="Staff response.",
    )

    comment = feedback_comment_service.create_feedback_comment(
        actor_user_id=feedback_staff.user_id,
        feedback_id=feedback.id,
        payload=payload,
        clinic_id=clinic.id,
    )

    assert comment.id is not None
    assert comment.feedback_id == feedback.id
    assert comment.author_user_id == feedback_staff.user_id


def test_create_feedback_comment_allows_admin(
    clinic,
    feedback,
    feedback_admin,
):
    payload = FeedbackCommentCreateSchema(
        body="Administrative response.",
    )

    comment = feedback_comment_service.create_feedback_comment(
        actor_user_id=feedback_admin.id,
        feedback_id=feedback.id,
        payload=payload,
        clinic_id=clinic.id,
    )

    assert comment.id is not None
    assert comment.author_user_id == feedback_admin.id


def test_create_feedback_comment_rejects_unauthorized_user(
    clinic,
    feedback,
    feedback_other_user,
):
    payload = FeedbackCommentCreateSchema(
        body="Unauthorized comment.",
    )

    with pytest.raises(NotFoundError):
        feedback_comment_service.create_feedback_comment(
            actor_user_id=feedback_other_user.id,
            feedback_id=feedback.id,
            payload=payload,
            clinic_id=clinic.id,
        )


@pytest.mark.parametrize(
    "feedback_fixture",
    [
        "feedback_closed",
        "feedback_rejected",
    ],
)
def test_create_feedback_comment_rejects_closed_or_rejected_feedback(
    request,
    clinic,
    feedback_submitter,
    feedback_fixture,
):
    feedback = request.getfixturevalue(feedback_fixture)

    payload = FeedbackCommentCreateSchema(
        body="This should not be allowed.",
    )

    with pytest.raises(ConflictError):
        feedback_comment_service.create_feedback_comment(
            actor_user_id=feedback_submitter.id,
            feedback_id=feedback.id,
            payload=payload,
            clinic_id=clinic.id,
        )


def test_create_feedback_comment_rejects_cross_clinic_feedback(
    clinic,
    feedback_submitter,
    feedback_other_clinic_item,
):
    payload = FeedbackCommentCreateSchema(
        body="Cross-clinic attempt.",
    )

    with pytest.raises(NotFoundError):
        feedback_comment_service.create_feedback_comment(
            actor_user_id=feedback_submitter.id,
            feedback_id=feedback_other_clinic_item.id,
            payload=payload,
            clinic_id=clinic.id,
        )


def test_get_feedback_comment_allows_author(
    clinic,
    feedback,
    feedback_comment,
):
    comment = feedback_comment_service.get_feedback_comment(
        actor_user_id=feedback_comment.author_user_id,
        comment_id=feedback_comment.id,
        feedback_id=feedback.id,
        clinic_id=clinic.id,
    )

    assert comment.id == feedback_comment.id
    assert comment.feedback_id == feedback.id


def test_get_feedback_comment_allows_admin(
    clinic,
    feedback,
    feedback_comment,
    feedback_admin,
):
    comment = feedback_comment_service.get_feedback_comment(
        actor_user_id=feedback_admin.id,
        comment_id=feedback_comment.id,
        feedback_id=feedback.id,
        clinic_id=clinic.id,
    )

    assert comment.id == feedback_comment.id


def test_get_feedback_comment_rejects_unauthorized_user(
    clinic,
    feedback,
    feedback_comment,
    feedback_other_user,
):
    with pytest.raises(NotFoundError):
        feedback_comment_service.get_feedback_comment(
            actor_user_id=feedback_other_user.id,
            comment_id=feedback_comment.id,
            feedback_id=feedback.id,
            clinic_id=clinic.id,
        )


def test_get_feedback_comment_rejects_cross_clinic_access(
    clinic,
    feedback_submitter,
    feedback_other_clinic_item,
    feedback_other_user,
    make_feedback_comment,
):
    comment = make_feedback_comment(
        feedback=feedback_other_clinic_item,
        author_user=feedback_other_user,
        body="Other clinic comment",
    )

    with pytest.raises(NotFoundError):
        feedback_comment_service.get_feedback_comment(
            actor_user_id=feedback_submitter.id,
            comment_id=comment.id,
            feedback_id=feedback_other_clinic_item.id,
            clinic_id=clinic.id,
        )


def test_list_feedback_comments_returns_deterministic_order(
    clinic,
    feedback,
    feedback_submitter,
    make_feedback_comment,
):
    first = make_feedback_comment(
        feedback=feedback,
        author_user=feedback_submitter,
        body="First comment",
    )

    second = make_feedback_comment(
        feedback=feedback,
        author_user=feedback_submitter,
        body="Second comment",
    )

    third = make_feedback_comment(
        feedback=feedback,
        author_user=feedback_submitter,
        body="Third comment",
    )

    result = feedback_comment_service.list_feedback_comments(
        actor_user_id=feedback_submitter.id,
        feedback_id=feedback.id,
        page=1,
        per_page=50,
        clinic_id=clinic.id,
    )

    ids = [comment.id for comment in result["items"]]

    assert ids == sorted(
        [first.id, second.id, third.id]
    )


def test_list_feedback_comments_supports_pagination(
    clinic,
    feedback,
    feedback_submitter,
    make_feedback_comment,
):
    for index in range(5):
        make_feedback_comment(
            feedback=feedback,
            author_user=feedback_submitter,
            body=f"Comment {index}",
        )

    result = feedback_comment_service.list_feedback_comments(
        actor_user_id=feedback_submitter.id,
        feedback_id=feedback.id,
        page=1,
        per_page=2,
        clinic_id=clinic.id,
    )

    assert len(result["items"]) == 2
    assert result["page"] == 1
    assert result["per_page"] == 2
    assert result["total"] == 5
    assert result["pages"] == 3
    assert result["has_next"] is True
    assert result["has_previous"] is False


def test_list_feedback_comments_rejects_unauthorized_user(
    clinic,
    feedback,
    feedback_other_user,
):
    with pytest.raises(NotFoundError):
        feedback_comment_service.list_feedback_comments(
            actor_user_id=feedback_other_user.id,
            feedback_id=feedback.id,
            page=1,
            per_page=50,
            clinic_id=clinic.id,
        )


def test_update_feedback_comment_allows_author(
    clinic,
    feedback,
    feedback_comment,
):
    comment = feedback_comment_service.update_feedback_comment(
        actor_user_id=feedback_comment.author_user_id,
        comment_id=feedback_comment.id,
        body="Updated by author.",
        feedback_id=feedback.id,
        clinic_id=clinic.id,
    )

    assert comment.id == feedback_comment.id
    assert comment.body == "Updated by author."


def test_update_feedback_comment_allows_admin(
    clinic,
    feedback,
    feedback_comment,
    feedback_admin,
):
    comment = feedback_comment_service.update_feedback_comment(
        actor_user_id=feedback_admin.id,
        comment_id=feedback_comment.id,
        body="Updated by admin.",
        feedback_id=feedback.id,
        clinic_id=clinic.id,
    )

    assert comment.id == feedback_comment.id
    assert comment.body == "Updated by admin."


def test_update_feedback_comment_rejects_other_user(
    clinic,
    feedback,
    feedback_comment,
    feedback_other_user,
):
    with pytest.raises(NotFoundError):
        feedback_comment_service.update_feedback_comment(
            actor_user_id=feedback_other_user.id,
            comment_id=feedback_comment.id,
            body="Unauthorized edit.",
            feedback_id=feedback.id,
            clinic_id=clinic.id,
        )


@pytest.mark.parametrize(
    "feedback_fixture",
    [
        "feedback_closed",
        "feedback_rejected",
    ],
)
def test_update_feedback_comment_rejects_closed_or_rejected_feedback(
    request,
    clinic,
    feedback_submitter,
    make_feedback_comment,
    feedback_fixture,
):
    feedback = request.getfixturevalue(feedback_fixture)

    comment = make_feedback_comment(
        feedback=feedback,
        author_user=feedback_submitter,
        body="Original comment",
    )

    with pytest.raises(ConflictError):
        feedback_comment_service.update_feedback_comment(
            actor_user_id=feedback_submitter.id,
            comment_id=comment.id,
            body="Attempted update.",
            feedback_id=feedback.id,
            clinic_id=clinic.id,
        )


@pytest.mark.parametrize(
    "body",
    [
        "",
        "   ",
        None,
        123,
        [],
        {},
    ],
)
def test_update_feedback_comment_rejects_invalid_body(
    clinic,
    feedback,
    feedback_comment,
    feedback_submitter,
    body,
):
    with pytest.raises(ValidationError):
        feedback_comment_service.update_feedback_comment(
            actor_user_id=feedback_submitter.id,
            comment_id=feedback_comment.id,
            body=body,
            feedback_id=feedback.id,
            clinic_id=clinic.id,
        )


def test_update_feedback_comment_rejects_cross_clinic_access(
    clinic,
    feedback_submitter,
    feedback_other_clinic_item,
    feedback_other_user,
    make_feedback_comment,
):
    comment = make_feedback_comment(
        feedback=feedback_other_clinic_item,
        author_user=feedback_other_user,
        body="Other clinic comment",
    )

    with pytest.raises(NotFoundError):
        feedback_comment_service.update_feedback_comment(
            actor_user_id=feedback_submitter.id,
            comment_id=comment.id,
            body="Cross-clinic edit.",
            feedback_id=feedback_other_clinic_item.id,
            clinic_id=clinic.id,
        )

@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (StaffStatus.ACTIVE, True),
        (StaffStatus.ON_LEAVE, False),
        (StaffStatus.SUSPENDED, False),
        (StaffStatus.TERMINATED, False),
    ],
)
def test_is_active_staff_requires_active_staff_status(
    clinic,
    make_staff,
    status,
    expected,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
        status=status,
    )

    result = feedback_comment_service._is_active_staff(
        actor=staff.user,
        clinic_id=clinic.id,
    )

    assert result is expected

