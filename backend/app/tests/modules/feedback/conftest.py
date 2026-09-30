from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.enums.feedback_enums import (
    FeedbackCategory,
    FeedbackPriority,
    FeedbackSource,
    FeedbackStatus,
    FeedbackType,
)
from app.core.enums.feedback_reaction_enums import (
    FeedbackReactionType,
)
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus
from app.modules.feedback.models.feedback_comment_model import (
    FeedbackComment,
)
from app.modules.feedback.models.feedback_model import Feedback
from app.modules.feedback.models.feedback_reaction_model import (
    FeedbackReaction,
)


@pytest.fixture()
def feedback_admin(make_user, clinic):
    return make_user(
        clinic,
        role=Role.ADMIN,
        email="feedback.admin@test.com",
    )


@pytest.fixture()
def feedback_super_admin(make_user):
    return make_user(
        clinic=None,
        role=Role.SUPER_ADMIN,
        email="feedback.superadmin@test.com",
    )


@pytest.fixture()
def feedback_submitter(make_user, clinic):
    return make_user(
        clinic,
        role=Role.PATIENT,
        email="feedback.submitter@test.com",
    )


@pytest.fixture()
def feedback_staff(make_staff, clinic):
    return make_staff(
        clinic,
        role=Role.DOCTOR,
        status=StaffStatus.ACTIVE,
        user_overrides={
            "email": "feedback.staff@test.com",
        },
    )


@pytest.fixture()
def feedback_other_clinic(make_clinic):
    return make_clinic(
        name="Feedback Other Clinic",
    )


@pytest.fixture()
def feedback_other_user(
    make_user,
    feedback_other_clinic,
):
    return make_user(
        feedback_other_clinic,
        role=Role.PATIENT,
        email="feedback.other.user@test.com",
    )


@pytest.fixture()
def feedback_other_admin(
    make_user,
    feedback_other_clinic,
):
    return make_user(
        feedback_other_clinic,
        role=Role.ADMIN,
        email="feedback.other.admin@test.com",
    )


@pytest.fixture()
def make_feedback(db_session):
    counter = {"n": 0}

    def _make(
        *,
        clinic,
        submitted_by_user=None,
        feedback_type=FeedbackType.BUG_REPORT,
        category=FeedbackCategory.USABILITY,
        subject=None,
        message="Test feedback message.",
        status=FeedbackStatus.OPEN,
        priority=FeedbackPriority.NORMAL,
        source=FeedbackSource.API,
        target_module=None,
        target_resource_type=None,
        target_resource_id=None,
        assigned_to_user_id=None,
        resolution_note=None,
        created_at=None,
        updated_at=None,
        resolved_at=None,
        closed_at=None,
        **overrides,
    ):
        counter["n"] += 1

        if subject is None:
            subject = (
                f"Test Feedback {counter['n']}"
            )

        feedback = Feedback(
            clinic_id=clinic.id,
            submitted_by_user_id=(
                submitted_by_user.id
                if submitted_by_user is not None
                else None
            ),
            feedback_type=feedback_type,
            category=category,
            subject=subject,
            message=message,
            status=status,
            priority=priority,
            source=source,
            target_module=target_module,
            target_resource_type=target_resource_type,
            target_resource_id=target_resource_id,
            assigned_to_user_id=assigned_to_user_id,
            resolution_note=resolution_note,
            **overrides,
        )

        if created_at is not None:
            feedback.created_at = created_at

        if updated_at is not None:
            feedback.updated_at = updated_at

        if resolved_at is not None:
            feedback.resolved_at = resolved_at

        if closed_at is not None:
            feedback.closed_at = closed_at

        db_session.add(feedback)
        db_session.flush()

        return feedback

    return _make


@pytest.fixture()
def feedback(
    make_feedback,
    clinic,
    feedback_submitter,
):
    return make_feedback(
        clinic=clinic,
        submitted_by_user=feedback_submitter,
    )


@pytest.fixture()
def feedback_triaged(
    make_feedback,
    clinic,
    feedback_submitter,
):
    return make_feedback(
        clinic=clinic,
        submitted_by_user=feedback_submitter,
        status=FeedbackStatus.TRIAGED,
    )


@pytest.fixture()
def feedback_in_progress(
    make_feedback,
    clinic,
    feedback_submitter,
):
    return make_feedback(
        clinic=clinic,
        submitted_by_user=feedback_submitter,
        status=FeedbackStatus.IN_PROGRESS,
    )


@pytest.fixture()
def feedback_resolved(
    make_feedback,
    clinic,
    feedback_submitter,
):
    now = datetime.now(timezone.utc)

    return make_feedback(
        clinic=clinic,
        submitted_by_user=feedback_submitter,
        status=FeedbackStatus.RESOLVED,
        resolution_note="Issue has been resolved.",
        resolved_at=now,
    )


@pytest.fixture()
def feedback_closed(
    make_feedback,
    clinic,
    feedback_submitter,
):
    now = datetime.now(timezone.utc)

    return make_feedback(
        clinic=clinic,
        submitted_by_user=feedback_submitter,
        status=FeedbackStatus.CLOSED,
        resolution_note="Issue has been resolved.",
        resolved_at=now - timedelta(minutes=5),
        closed_at=now,
    )


@pytest.fixture()
def feedback_rejected(
    make_feedback,
    clinic,
    feedback_submitter,
):
    return make_feedback(
        clinic=clinic,
        submitted_by_user=feedback_submitter,
        status=FeedbackStatus.REJECTED,
        resolution_note="Not reproducible.",
    )


@pytest.fixture()
def feedback_other_clinic_item(
    make_feedback,
    feedback_other_clinic,
    feedback_other_user,
):
    return make_feedback(
        clinic=feedback_other_clinic,
        submitted_by_user=feedback_other_user,
        subject="Other clinic feedback",
    )


@pytest.fixture()
def make_feedback_comment(db_session):
    def _make(
        *,
        feedback,
        author_user,
        body="Test feedback comment.",
        created_at=None,
        updated_at=None,
        **overrides,
    ):
        comment = FeedbackComment(
            feedback_id=feedback.id,
            author_user_id=author_user.id,
            body=body,
            **overrides,
        )

        if created_at is not None:
            comment.created_at = created_at

        if updated_at is not None:
            comment.updated_at = updated_at

        db_session.add(comment)
        db_session.flush()

        return comment

    return _make


@pytest.fixture()
def feedback_comment(
    make_feedback_comment,
    feedback,
    feedback_submitter,
):
    return make_feedback_comment(
        feedback=feedback,
        author_user=feedback_submitter,
    )


@pytest.fixture()
def feedback_admin_comment(
    make_feedback_comment,
    feedback,
    feedback_admin,
):
    return make_feedback_comment(
        feedback=feedback,
        author_user=feedback_admin,
        body="Admin feedback comment.",
    )


@pytest.fixture()
def feedback_old_comment(
    make_feedback_comment,
    feedback,
    feedback_submitter,
):
    created_at = (
        datetime.now(timezone.utc)
        - timedelta(hours=1)
    )

    return make_feedback_comment(
        feedback=feedback,
        author_user=feedback_submitter,
        created_at=created_at,
        updated_at=created_at,
        body="Older feedback comment.",
    )


@pytest.fixture()
def make_feedback_reaction(db_session):
    def _make(
        *,
        feedback,
        user,
        reaction_type=FeedbackReactionType.HELPFUL,
        created_at=None,
        updated_at=None,
        **overrides,
    ):
        reaction = FeedbackReaction(
            feedback_id=feedback.id,
            user_id=user.id,
            reaction_type=reaction_type,
            **overrides,
        )

        if created_at is not None:
            reaction.created_at = created_at

        if updated_at is not None:
            reaction.updated_at = updated_at

        db_session.add(reaction)
        db_session.flush()

        return reaction

    return _make


@pytest.fixture()
def feedback_reaction(
    make_feedback_reaction,
    feedback,
    feedback_submitter,
):
    return make_feedback_reaction(
        feedback=feedback,
        user=feedback_submitter,
        reaction_type=FeedbackReactionType.HELPFUL,
    )


@pytest.fixture()
def feedback_reaction_appreciated(
    make_feedback_reaction,
    feedback,
    feedback_admin,
):
    return make_feedback_reaction(
        feedback=feedback,
        user=feedback_admin,
        reaction_type=FeedbackReactionType.APPRECIATED,
    )


@pytest.fixture()
def feedback_reaction_not_helpful(
    make_feedback_reaction,
    feedback,
    feedback_staff,
):
    return make_feedback_reaction(
        feedback=feedback,
        user=feedback_staff.user,
        reaction_type=FeedbackReactionType.NOT_HELPFUL,
    )