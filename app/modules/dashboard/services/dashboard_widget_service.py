from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.extensions import db

from app.core.audit.models.audit_model import AuditLog
from app.core.auth.user.models.user_model import User
from app.core.enums.ai_enums import (
    AIApprovalStatus,
    AIRiskLevel,
)
from app.core.enums.chat_enums import (
    ConversationStatus,
    MessagePriority,
    MessageStatus,
    ParticipantStatus,
    ReadReceiptStatus,
)
from app.core.enums.role_enums import Role

from app.modules.ai.models.ai_model import AILog

from app.modules.chat.models.conversation_model import (
    Conversation,
)
from app.modules.chat.models.conversation_participant_model import (
    ConversationParticipant,
)
from app.modules.chat.models.message_mention_model import (
    MessageMention,
)
from app.modules.chat.models.message_model import (
    Message,
)
from app.modules.chat.models.message_read_receipt_model import (
    MessageReadReceipt,
)

from app.modules.dashboard.schemas.dashboard_schema import (
    DashboardActivitySchema,
    DashboardChatSummarySchema,
    DashboardContextSchema,
    DashboardMetricSchema,
    DashboardPeriodSchema,
    DashboardQuerySchema,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _validate_positive_id(
    value: Any,
    field_name: str,
) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ValueError(
            f"{field_name} must be a positive integer"
        )


def resolve_dashboard_period(
    query: DashboardQuerySchema | None,
) -> DashboardPeriodSchema:
    today = _utcnow().date()

    if query is None:
        return DashboardPeriodSchema(
            date_from=today,
            date_to=today,
        )

    date_from = query.date_from or query.date_to or today
    date_to = query.date_to or query.date_from or today

    return DashboardPeriodSchema(
        date_from=date_from,
        date_to=date_to,
    )


def period_bounds(
    period: DashboardPeriodSchema,
) -> tuple[datetime, datetime]:
    start = datetime.combine(
        period.date_from,
        time.min,
        tzinfo=timezone.utc,
    )

    end = datetime.combine(
        period.date_to + timedelta(days=1),
        time.min,
        tzinfo=timezone.utc,
    )

    return start, end


def build_dashboard_context(
    *,
    role: Role,
    scope: str,
    clinic_id: int | None,
) -> DashboardContextSchema:
    return DashboardContextSchema(
        role=role,
        scope=scope,
        clinic_id=clinic_id,
        generated_at=_utcnow(),
    )


def count_scalar(
    statement,
) -> int:
    value = db.session.execute(
        statement,
    ).scalar_one()

    return int(value or 0)


def decimal_scalar(
    statement,
) -> Decimal:
    value = db.session.execute(
        statement,
    ).scalar_one()

    if value is None:
        return Decimal("0")

    if isinstance(value, Decimal):
        return value

    return Decimal(
        str(value)
    )


def build_metric(
    *,
    key: str,
    label: str,
    value: int | float | Decimal,
    unit: str | None = None,
) -> DashboardMetricSchema:
    return DashboardMetricSchema(
        key=key,
        label=label,
        value=value,
        unit=unit,
    )


def build_recent_activity(
    *,
    clinic_id: int | None,
    limit: int = 10,
) -> list[DashboardActivitySchema]:
    statement = (
        db.select(AuditLog)
        .order_by(
            AuditLog.created_at.desc(),
            AuditLog.id.desc(),
        )
        .limit(limit)
    )

    if clinic_id is not None:
        statement = (
            statement
            .join(
                User,
                AuditLog.user_id == User.id,
            )
            .where(
                User.clinic_id == clinic_id,
            )
        )

    logs = db.session.execute(
        statement,
    ).scalars().all()

    return [
        DashboardActivitySchema(
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            action=log.action.value,
            occurred_at=log.created_at,
        )
        for log in logs
        if log.entity_id > 0
    ]


def build_chat_summary(
    *,
    user_id: int,
    clinic_id: int,
    period: DashboardPeriodSchema,
) -> DashboardChatSummarySchema:
    _validate_positive_id(
        user_id,
        "User ID",
    )

    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    start, end = period_bounds(
        period,
    )

    participant_conversations = (
        db.select(
            ConversationParticipant.conversation_id,
        )
        .where(
            ConversationParticipant.user_id == user_id,
            ConversationParticipant.clinic_id == clinic_id,
            ConversationParticipant.status
            == ParticipantStatus.ACCEPTED,
        )
    )

    active_conversations = (
        db.select(
            Conversation.id,
        )
        .where(
            Conversation.id.in_(
                participant_conversations,
            ),
            Conversation.clinic_id == clinic_id,
            Conversation.status
            == ConversationStatus.ACTIVE,
        )
    )

    unread_messages = count_scalar(
        db.select(
            db.func.count(
                MessageReadReceipt.id,
            ),
        )
        .join(
            Message,
            Message.id == MessageReadReceipt.message_id,
        )
        .where(
            MessageReadReceipt.user_id == user_id,
            MessageReadReceipt.clinic_id == clinic_id,
            MessageReadReceipt.status
            == ReadReceiptStatus.DELIVERED,
            Message.sender_id != user_id,
            Message.status.in_(
                [
                    MessageStatus.SENT,
                    MessageStatus.EDITED,
                ]
            ),
            Message.conversation_id.in_(
                active_conversations,
            ),
            Message.created_at >= start,
            Message.created_at < end,
        )
    )

    unread_conversations = count_scalar(
        db.select(
            db.func.count(
                db.func.distinct(
                    Message.conversation_id,
                )
            )
        )
        .join(
            Message,
            Message.id == MessageReadReceipt.message_id,
        )
        .where(
            MessageReadReceipt.user_id == user_id,
            MessageReadReceipt.clinic_id == clinic_id,
            MessageReadReceipt.status
            == ReadReceiptStatus.DELIVERED,
            Message.sender_id != user_id,
            Message.status.in_(
                [
                    MessageStatus.SENT,
                    MessageStatus.EDITED,
                ]
            ),
            Message.conversation_id.in_(
                active_conversations,
            ),
            Message.created_at >= start,
            Message.created_at < end,
        )
    )

    mentions = count_scalar(
        db.select(
            db.func.count(
                MessageMention.id,
            ),
        )
        .join(
            Message,
            Message.id == MessageMention.message_id,
        )
        .where(
            MessageMention.clinic_id == clinic_id,
            MessageMention.mentioned_user_id == user_id,
            Message.status.in_(
                [
                    MessageStatus.SENT,
                    MessageStatus.EDITED,
                ]
            ),
            Message.conversation_id.in_(
                active_conversations,
            ),
            Message.created_at >= start,
            Message.created_at < end,
        )
    )

    priority_messages = count_scalar(
        db.select(
            db.func.count(
                Message.id,
            ),
        )
        .where(
            Message.clinic_id == clinic_id,
            Message.sender_id != user_id,
            Message.status.in_(
                [
                    MessageStatus.SENT,
                    MessageStatus.EDITED,
                ]
            ),
            Message.priority.in_(
                [
                    MessagePriority.URGENT,
                    MessagePriority.STAT,
                ]
            ),
            Message.conversation_id.in_(
                active_conversations,
            ),
            Message.created_at >= start,
            Message.created_at < end,
        )
    )

    recent_messages = count_scalar(
        db.select(
            db.func.count(
                Message.id,
            ),
        )
        .where(
            Message.clinic_id == clinic_id,
            Message.status.in_(
                [
                    MessageStatus.SENT,
                    MessageStatus.EDITED,
                ]
            ),
            Message.conversation_id.in_(
                active_conversations,
            ),
            Message.created_at >= start,
            Message.created_at < end,
        )
    )

    return DashboardChatSummarySchema(
        unread_messages=unread_messages,
        unread_conversations=unread_conversations,
        mentions=mentions,
        priority_messages=priority_messages,
        recent_messages=recent_messages,
    )


def build_ai_aggregates(
    *,
    period: DashboardPeriodSchema,
    clinic_id: int | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    start, end = period_bounds(
        period,
    )

    filters = [
        AILog.created_at >= start,
        AILog.created_at < end,
    ]

    if clinic_id is not None:
        _validate_positive_id(
            clinic_id,
            "Clinic ID",
        )

        filters.append(
            AILog.clinic_id == clinic_id,
        )

    if user_id is not None:
        _validate_positive_id(
            user_id,
            "User ID",
        )

        filters.append(
            AILog.user_id == user_id,
        )

    total_ai_requests = count_scalar(
        db.select(
            db.func.count(
                AILog.id,
            )
        ).where(
            *filters,
        )
    )

    total_credits_used = count_scalar(
        db.select(
            db.func.coalesce(
                db.func.sum(
                    AILog.credits_used,
                ),
                0,
            )
        ).where(
            *filters,
        )
    )

    total_input_tokens = count_scalar(
        db.select(
            db.func.coalesce(
                db.func.sum(
                    AILog.input_tokens,
                ),
                0,
            )
        ).where(
            *filters,
        )
    )

    total_output_tokens = count_scalar(
        db.select(
            db.func.coalesce(
                db.func.sum(
                    AILog.output_tokens,
                ),
                0,
            )
        ).where(
            *filters,
        )
    )

    total_tokens = count_scalar(
        db.select(
            db.func.coalesce(
                db.func.sum(
                    AILog.total_tokens,
                ),
                0,
            )
        ).where(
            *filters,
        )
    )

    estimated_cost = decimal_scalar(
        db.select(
            db.func.coalesce(
                db.func.sum(
                    AILog.estimated_cost,
                ),
                0,
            )
        ).where(
            *filters,
        )
    )

    pending_reviews = count_scalar(
        db.select(
            db.func.count(
                AILog.id,
            )
        ).where(
            *filters,
            AILog.approval_status
            == AIApprovalStatus.PENDING,
        )
    )

    approved_reviews = count_scalar(
        db.select(
            db.func.count(
                AILog.id,
            )
        ).where(
            *filters,
            AILog.approval_status
            == AIApprovalStatus.APPROVED,
        )
    )

    rejected_reviews = count_scalar(
        db.select(
            db.func.count(
                AILog.id,
            )
        ).where(
            *filters,
            AILog.approval_status
            == AIApprovalStatus.REJECTED,
        )
    )

    low_risk_results = count_scalar(
        db.select(
            db.func.count(
                AILog.id,
            )
        ).where(
            *filters,
            AILog.risk_level == AIRiskLevel.LOW,
        )
    )

    medium_risk_results = count_scalar(
        db.select(
            db.func.count(
                AILog.id,
            )
        ).where(
            *filters,
            AILog.risk_level == AIRiskLevel.MEDIUM,
        )
    )

    high_risk_results = count_scalar(
        db.select(
            db.func.count(
                AILog.id,
            )
        ).where(
            *filters,
            AILog.risk_level == AIRiskLevel.HIGH,
        )
    )

    critical_risk_results = count_scalar(
        db.select(
            db.func.count(
                AILog.id,
            )
        ).where(
            *filters,
            AILog.risk_level == AIRiskLevel.CRITICAL,
        )
    )

    feature_rows = db.session.execute(
        db.select(
            AILog.feature_used,
            db.func.count(
                AILog.id,
            ),
            db.func.coalesce(
                db.func.sum(
                    AILog.credits_used,
                ),
                0,
            ),
            db.func.coalesce(
                db.func.sum(
                    AILog.estimated_cost,
                ),
                0,
            ),
        )
        .where(
            *filters,
        )
        .group_by(
            AILog.feature_used,
        )
    ).all()

    feature_usage = [
        {
            "feature": row[0],
            "request_count": int(
                row[1] or 0
            ),
            "credits_used": int(
                row[2] or 0
            ),
            "estimated_cost": (
                row[3]
                if isinstance(
                    row[3],
                    Decimal,
                )
                else Decimal(
                    str(
                        row[3] or 0
                    )
                )
            ),
        }
        for row in sorted(
            feature_rows,
            key=lambda row: row[0].value,
        )
    ]

    risk_rows = db.session.execute(
        db.select(
            AILog.risk_level,
            db.func.count(
                AILog.id,
            ),
        )
        .where(
            *filters,
        )
        .group_by(
            AILog.risk_level,
        )
    ).all()

    risk_summary = [
        {
            "risk_level": row[0],
            "count": int(
                row[1] or 0
            ),
        }
        for row in sorted(
            risk_rows,
            key=lambda row: row[0].value,
        )
    ]

    approval_rows = db.session.execute(
        db.select(
            AILog.approval_status,
            db.func.count(
                AILog.id,
            ),
        )
        .where(
            *filters,
        )
        .group_by(
            AILog.approval_status,
        )
    ).all()

    approval_summary = [
        {
            "approval_status": row[0],
            "count": int(
                row[1] or 0
            ),
        }
        for row in sorted(
            approval_rows,
            key=lambda row: row[0].value,
        )
    ]

    return {
        "total_ai_requests": total_ai_requests,
        "total_credits_used": total_credits_used,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost": estimated_cost,
        "pending_reviews": pending_reviews,
        "approved_reviews": approved_reviews,
        "rejected_reviews": rejected_reviews,
        "low_risk_results": low_risk_results,
        "medium_risk_results": medium_risk_results,
        "high_risk_results": high_risk_results,
        "critical_risk_results": critical_risk_results,
        "feature_usage": feature_usage,
        "risk_summary": risk_summary,
        "approval_summary": approval_summary,
    }