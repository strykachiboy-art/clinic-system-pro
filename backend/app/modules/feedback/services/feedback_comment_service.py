from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func

from app.core.auth.user.models.user_model import User
from app.core.audit.services.audit_service import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import transactional
from app.extensions import db
from app.modules.feedback.models.feedback_comment_model import (
    FeedbackComment,
)
from app.modules.feedback.models.feedback_model import Feedback
from app.modules.feedback.schemas.feedback_comment_schema import (
    FeedbackCommentCreateSchema,
)
from app.modules.feedback.services.feedback_service import (
    get_feedback_for_actor,
)
from app.modules.staff.models.staff_model import Staff


DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 500


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _validate_positive_id(
    value: Any,
    field_name: str,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ValidationError(
            f"{field_name} must be a positive integer"
        )

    return value


def _validate_pagination(
    page: int,
    per_page: int,
) -> tuple[int, int]:
    page = _validate_positive_id(
        page,
        "Page",
    )

    per_page = _validate_positive_id(
        per_page,
        "Per-page",
    )

    if per_page > MAX_PER_PAGE:
        raise ValidationError(
            f"Per-page cannot exceed {MAX_PER_PAGE}"
        )

    return page, per_page


def _get_actor(
    actor_user_id: int,
) -> User:
    actor_user_id = _validate_positive_id(
        actor_user_id,
        "Actor user ID",
    )

    actor = db.session.get(
        User,
        actor_user_id,
    )

    if actor is None:
        raise NotFoundError(
            f"User {actor_user_id} not found"
        )

    if not actor.is_active:
        raise ValidationError(
            "Authenticated user is inactive"
        )

    return actor


def _get_role(
    actor: User,
) -> Role:
    try:
        if isinstance(actor.role, Role):
            return actor.role

        return Role(actor.role)

    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Authenticated user has an invalid role"
        ) from exc


def _is_active_staff(
    actor: User,
    clinic_id: int,
) -> bool:
    statement = db.select(
        Staff.id
    ).where(
        Staff.user_id == actor.id,
        Staff.clinic_id == clinic_id,
        Staff.status == StaffStatus.ACTIVE,
    )

    staff = db.session.execute(
        statement
    ).scalar_one_or_none()

    if staff is None:
        return False

    return True


def _can_update_comment(
    actor: User,
    comment: FeedbackComment,
) -> bool:
    role = _get_role(actor)

    if role in {
        Role.ADMIN,
        Role.SUPER_ADMIN,
    }:
        return True

    return comment.author_user_id == actor.id


def _get_comment(
    comment_id: int,
    *,
    feedback_id: int | None = None,
    clinic_id: int | None = None,
    lock: bool = False,
) -> FeedbackComment:
    comment_id = _validate_positive_id(
        comment_id,
        "Comment ID",
    )

    statement = (
        db.select(FeedbackComment)
        .join(
            Feedback,
            Feedback.id
            == FeedbackComment.feedback_id,
        )
        .where(
            FeedbackComment.id == comment_id,
        )
    )

    if feedback_id is not None:
        feedback_id = _validate_positive_id(
            feedback_id,
            "Feedback ID",
        )

        statement = statement.where(
            FeedbackComment.feedback_id
            == feedback_id,
        )

    if clinic_id is not None:
        clinic_id = _validate_positive_id(
            clinic_id,
            "Clinic ID",
        )

        statement = statement.where(
            Feedback.clinic_id == clinic_id,
        )

    if lock:
        statement = statement.with_for_update()

    comment = db.session.execute(
        statement
    ).scalar_one_or_none()

    if comment is None:
        raise NotFoundError(
            f"Feedback comment {comment_id} not found"
        )

    return comment


def _validate_comment_access(
    *,
    actor: User,
    feedback: Feedback,
) -> None:
    role = _get_role(actor)

    if role == Role.SUPER_ADMIN:
        return

    if actor.clinic_id != feedback.clinic_id:
        raise NotFoundError(
            f"Feedback {feedback.id} not found"
        )

    if role in {
        Role.ADMIN,
    }:
        return

    if feedback.submitted_by_user_id == actor.id:
        return

    if _is_active_staff(
        actor,
        feedback.clinic_id,
    ):
        return

    raise NotFoundError(
        f"Feedback {feedback.id} not found"
    )


@transactional
def create_feedback_comment(
    *,
    actor_user_id: int,
    feedback_id: int,
    payload: FeedbackCommentCreateSchema,
    clinic_id: int | None = None,
) -> FeedbackComment:
    actor = _get_actor(
        actor_user_id,
    )

    feedback = get_feedback_for_actor(
        actor_user_id=actor.id,
        feedback_id=feedback_id,
        clinic_id=clinic_id,
    )

    _validate_comment_access(
        actor=actor,
        feedback=feedback,
    )

    if feedback.status.value in {
        "closed",
        "rejected",
    }:
        raise ConflictError(
            "Comments cannot be added to closed or rejected feedback"
        )

    comment = FeedbackComment(
        feedback_id=feedback.id,
        author_user_id=actor.id,
        body=payload.body,
    )

    db.session.add(comment)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="FeedbackComment",
        entity_id=comment.id,
        description=(
            f"Comment {comment.id} added to "
            f"feedback {feedback.id}"
        ),
        new_value={
            "feedback_id": feedback.id,
            "author_user_id": actor.id,
        },
        user_id=actor.id,
    )

    return comment


def get_feedback_comment(
    *,
    actor_user_id: int,
    comment_id: int,
    feedback_id: int | None = None,
    clinic_id: int | None = None,
) -> FeedbackComment:
    actor = _get_actor(
        actor_user_id,
    )

    comment = _get_comment(
        comment_id,
        feedback_id=feedback_id,
        clinic_id=clinic_id,
    )

    feedback = get_feedback_for_actor(
        actor_user_id=actor.id,
        feedback_id=comment.feedback_id,
        clinic_id=clinic_id,
    )

    _validate_comment_access(
        actor=actor,
        feedback=feedback,
    )

    return comment


def list_feedback_comments(
    *,
    actor_user_id: int,
    feedback_id: int,
    page: int = DEFAULT_PAGE,
    per_page: int = DEFAULT_PER_PAGE,
    clinic_id: int | None = None,
) -> dict[str, Any]:
    actor = _get_actor(
        actor_user_id,
    )

    feedback = get_feedback_for_actor(
        actor_user_id=actor.id,
        feedback_id=feedback_id,
        clinic_id=clinic_id,
    )

    _validate_comment_access(
        actor=actor,
        feedback=feedback,
    )

    page, per_page = _validate_pagination(
        page,
        per_page,
    )

    count_statement = (
        db.select(
            func.count(
                FeedbackComment.id
            )
        )
        .where(
            FeedbackComment.feedback_id
            == feedback.id,
        )
    )

    total = db.session.execute(
        count_statement
    ).scalar_one()

    statement = (
        db.select(FeedbackComment)
        .where(
            FeedbackComment.feedback_id
            == feedback.id,
        )
        .order_by(
            FeedbackComment.created_at.asc(),
            FeedbackComment.id.asc(),
        )
        .offset(
            (page - 1) * per_page
        )
        .limit(per_page)
    )

    items = db.session.execute(
        statement
    ).scalars().all()

    pages = (
        (total + per_page - 1) // per_page
        if total
        else 0
    )

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "has_next": page < pages,
        "has_previous": (
            page > 1 and total > 0
        ),
    }


@transactional
def update_feedback_comment(
    *,
    actor_user_id: int,
    comment_id: int,
    body: str,
    feedback_id: int | None = None,
    clinic_id: int | None = None,
) -> FeedbackComment:
    actor = _get_actor(
        actor_user_id,
    )

    if not isinstance(body, str):
        raise ValidationError(
            "Comment body must be a string"
        )

    body = body.strip()

    if not body:
        raise ValidationError(
            "Comment body cannot be empty"
        )

    if len(body) > 10000:
        raise ValidationError(
            "Comment body cannot exceed 10000 characters"
        )

    comment = _get_comment(
        comment_id,
        feedback_id=feedback_id,
        clinic_id=clinic_id,
        lock=True,
    )

    feedback = get_feedback_for_actor(
        actor_user_id=actor.id,
        feedback_id=comment.feedback_id,
        clinic_id=clinic_id,
    )

    _validate_comment_access(
        actor=actor,
        feedback=feedback,
    )

    if not _can_update_comment(
        actor,
        comment,
    ):
        raise NotFoundError(
            f"Feedback comment {comment.id} not found"
        )

    if feedback.status.value in {
        "closed",
        "rejected",
    }:
        raise ConflictError(
            "Comments cannot be edited after feedback is closed or rejected"
        )

    old_body = comment.body

    if old_body == body:
        return comment

    comment.body = body
    comment.updated_at = _utcnow()

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="FeedbackComment",
        entity_id=comment.id,
        description=(
            f"Comment {comment.id} updated"
        ),
        old_value={
            "body": old_body,
        },
        new_value={
            "body": body,
        },
        user_id=actor.id,
    )

    return comment