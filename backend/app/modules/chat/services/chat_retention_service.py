from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db
from app.modules.chat.models.message_model import Message
from app.modules.chat.services.chat_policy_service import ChatPolicyService


class ChatRetentionService:
    DEFAULT_BATCH_SIZE = 500
    MAX_BATCH_SIZE = 5000

    @classmethod
    def get_cutoff(
        cls,
        clinic_id: int,
        *,
        now: datetime | None = None,
    ) -> datetime:
        if now is None:
            now = datetime.now(timezone.utc)

        return ChatPolicyService.get_retention_cutoff(
            clinic_id=clinic_id,
            now=now,
        )

    @classmethod
    def get_expired_message_ids(
        cls,
        clinic_id: int,
        *,
        now: datetime | None = None,
        limit: int = DEFAULT_BATCH_SIZE,
    ) -> list[int]:
        if clinic_id <= 0:
            return []

        if limit <= 0:
            return []

        limit = min(limit, cls.MAX_BATCH_SIZE)

        cutoff = cls.get_cutoff(
            clinic_id=clinic_id,
            now=now,
        )

        statement = (
            db.select(Message.id)
            .where(
                Message.clinic_id == clinic_id,
                Message.created_at < cutoff,
            )
            .order_by(
                Message.created_at.asc(),
                Message.id.asc(),
            )
            .limit(limit)
        )

        return list(
            db.session.execute(statement).scalars().all()
        )

    @classmethod
    def delete_expired_messages(
        cls,
        clinic_id: int,
        *,
        now: datetime | None = None,
        limit: int = DEFAULT_BATCH_SIZE,
    ) -> int:
        try:
            message_ids = cls.get_expired_message_ids(
                clinic_id=clinic_id,
                now=now,
                limit=limit,
            )

            if not message_ids:
                return 0

            statement = db.delete(Message).where(
                Message.clinic_id == clinic_id,
                Message.id.in_(message_ids),
            )

            result = db.session.execute(statement)
            deleted_count = int(result.rowcount or 0)

            db.session.commit()

            return deleted_count

        except Exception:
            db.session.rollback()
            raise