from __future__ import annotations

import argparse
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import event

from app import create_app
from app.extensions import db
from app.core.enums.chat_enums import (
    ConversationStatus,
    MessagePriority,
    MessageStatus,
    MessageType,
)
from app.core.audit.services.audit_service import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.chat.models.message_model import Message
from app.modules.chat.services.chat_content_validation_service import (
    ChatContentValidationService,
)
from app.modules.chat.services.chat_policy_service import (
    ChatPolicyService,
)
from app.modules.chat.services.chat_security_service import (
    ChatSecurityService,
)
from app.modules.chat.workers.chat_outbox_worker import (
    create_outbox_event,
)
from app.modules.clinic.services.clinic_service import (
    ensure_clinic_active,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_CLINIC_ID = 2
DEFAULT_USER_ID = 5037
DEFAULT_CONVERSATION_ID = 51
DEFAULT_CONTENT = "Profiler test message"
DEFAULT_RUNS = 1


@dataclass
class StageResult:
    name: str
    elapsed_ms: float


class SQLProfiler:
    def __init__(self) -> None:
        self.query_count = 0
        self.db_time_ms = 0.0

    def before_cursor_execute(
        self,
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        conn.info.setdefault(
            "chat_profile_query_start",
            [],
        ).append(time.perf_counter())

    def after_cursor_execute(
        self,
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        starts = conn.info.get(
            "chat_profile_query_start",
        )

        if not starts:
            return

        started = starts.pop()

        self.query_count += 1
        self.db_time_ms += (
            time.perf_counter() - started
        ) * 1000.0


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def validate_positive_id(
    value: Any,
    field_name: str,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ValidationError(
            f"Invalid {field_name}"
        )

    return value


def normalize_content(
    content: str | None,
) -> str | None:
    if content is None:
        return None

    if not isinstance(content, str):
        raise ValidationError(
            "Message content must be a string"
        )

    content = content.strip()

    if not content:
        return None

    return content


def validate_reply_message(
    conversation: Any,
    reply_to_message_id: int | None,
) -> Message | None:
    if reply_to_message_id is None:
        return None

    reply_to_message_id = validate_positive_id(
        reply_to_message_id,
        "Reply message ID",
    )

    reply_to = db.session.execute(
        db.select(Message).where(
            Message.id == reply_to_message_id,
            Message.clinic_id == conversation.clinic_id,
            Message.conversation_id == conversation.id,
        )
    ).scalar_one_or_none()

    if reply_to is None:
        raise NotFoundError(
            f"Reply message {reply_to_message_id} not found"
        )

    return reply_to


def ensure_message_can_be_sent(
    conversation: Any,
) -> None:
    if conversation.status != ConversationStatus.ACTIVE:
        raise ConflictError(
            "Messages cannot be sent to an inactive conversation"
        )


def normalize_enum(
    value: Any,
    enum_class: Any,
    field_name: str,
) -> Any:
    if isinstance(value, enum_class):
        return value

    try:
        return enum_class(value)
    except (TypeError, ValueError):
        raise ValidationError(
            f"Invalid {field_name}"
        )


def run_once(
    app: Any,
    clinic_id: int,
    user_id: int,
    conversation_id: int,
    content: str,
) -> tuple[list[StageResult], float, SQLProfiler, int]:
    stages: list[StageResult] = []
    sql_profiler = SQLProfiler()

    total_start = time.perf_counter()

    with app.app_context():
        engine = db.engine

        event.listen(
            engine,
            "before_cursor_execute",
            sql_profiler.before_cursor_execute,
        )

        event.listen(
            engine,
            "after_cursor_execute",
            sql_profiler.after_cursor_execute,
        )

        try:
            db.session.rollback()

            def stage(
                name: str,
                function: Any,
            ) -> Any:
                started = time.perf_counter()

                result = function()

                elapsed_ms = (
                    time.perf_counter() - started
                ) * 1000.0

                stages.append(
                    StageResult(
                        name=name,
                        elapsed_ms=elapsed_ms,
                    )
                )

                return result

            validate_positive_id(
                clinic_id,
                "Clinic ID",
            )

            validate_positive_id(
                conversation_id,
                "Conversation ID",
            )

            validate_positive_id(
                user_id,
                "Sender ID",
            )

            clinic = stage(
                "ensure_clinic_active",
                lambda: ensure_clinic_active(
                    clinic_id,
                ),
            )

            chat_settings = stage(
                "ChatPolicyService.get_settings",
                lambda: ChatPolicyService.get_settings(
                    clinic_id,
                ),
            )

            stage(
                "ChatPolicyService.ensure_chat_enabled",
                lambda: ChatPolicyService.ensure_chat_enabled(
                    clinic_id,
                    settings=chat_settings,
                ),
            )

            conversation = stage(
                "ChatSecurityService.ensure_user_can_send_message",
                lambda: ChatSecurityService.ensure_user_can_send_message(
                    user_id,
                    conversation_id,
                ),
            )

            stage(
                "conversation clinic validation",
                lambda: (
                    None
                    if conversation.clinic_id == clinic_id
                    else (_ for _ in ()).throw(
                        NotFoundError(
                            "Conversation not found"
                        )
                    )
                ),
            )

            stage(
                "_ensure_message_can_be_sent",
                lambda: ensure_message_can_be_sent(
                    conversation,
                ),
            )

            message_type = stage(
                "_normalize_enum(message_type)",
                lambda: normalize_enum(
                    MessageType.TEXT,
                    MessageType,
                    "message type",
                ),
            )

            priority = stage(
                "_normalize_enum(priority)",
                lambda: normalize_enum(
                    MessagePriority.NORMAL,
                    MessagePriority,
                    "message priority",
                ),
            )

            normalized_content = stage(
                "_normalize_content",
                lambda: normalize_content(
                    content,
                ),
            )

            validated_content = normalized_content

            if normalized_content is not None:
                validated_content = stage(
                    "ChatContentValidationService.ensure_text_allowed",
                    lambda: ChatContentValidationService.ensure_text_allowed(
                        clinic_id,
                        normalized_content,
                        settings=chat_settings,
                    ),
                )

            if (
                message_type == MessageType.TEXT
                and validated_content is None
            ):
                raise ValidationError(
                    "Text messages require content"
                )

            reply_to = stage(
                "_validate_reply_message",
                lambda: validate_reply_message(
                    conversation,
                    None,
                ),
            )

            message = stage(
                "Message construction",
                lambda: Message(
                    clinic_id=clinic_id,
                    conversation_id=conversation.id,
                    sender_id=user_id,
                    message_type=message_type,
                    content=validated_content,
                    reply_to_message_id=(
                        reply_to.id
                        if reply_to is not None
                        else None
                    ),
                    status=MessageStatus.PENDING,
                    priority=priority,
                ),
            )

            stage(
                "db.session.add(message)",
                lambda: db.session.add(
                    message,
                ),
            )

            stage(
                "db.session.flush(message)",
                lambda: db.session.flush(),
            )

            stage(
                "create_outbox_event",
                lambda: create_outbox_event(
                    clinic_id=clinic_id,
                    event_type="message.created",
                    payload={
                        "conversation_id": conversation.id,
                        "message_id": message.id,
                        "sender_id": user_id,
                        "message_type": message.message_type.value,
                        "priority": message.priority.value,
                        "reply_to_message_id": (
                            message.reply_to_message_id
                        ),
                    },
                    message_id=message.id,
                    clinic_obj=clinic,
                    message_obj=message,
                ),
            )

            now = utcnow()

            stage(
                "conversation timestamp updates",
                lambda: (
                    setattr(
                        conversation,
                        "last_message_at",
                        now,
                    ),
                    setattr(
                        conversation,
                        "updated_at",
                        now,
                    ),
                ),
            )

            stage(
                "create_audit_log",
                lambda: create_audit_log(
                    action=AuditAction.CREATE,
                    entity_type="Message",
                    entity_id=message.id,
                    description=(
                        f"Message {message.id} created "
                        f"in conversation {conversation.id}"
                    ),
                    new_value={
                        "conversation_id": conversation.id,
                        "sender_id": user_id,
                        "message_type": message.message_type.value,
                        "priority": message.priority.value,
                        "reply_to_message_id": (
                            message.reply_to_message_id
                        ),
                    },
                ),
            )

            message_id = message.id

            commit_start = time.perf_counter()

            db.session.commit()

            commit_elapsed_ms = (
                time.perf_counter() - commit_start
            ) * 1000.0

            stages.append(
                StageResult(
                    name="db.session.commit",
                    elapsed_ms=commit_elapsed_ms,
                )
            )

        finally:
            try:
                db.session.rollback()
            except Exception:
                pass

            event.remove(
                engine,
                "before_cursor_execute",
                sql_profiler.before_cursor_execute,
            )

            event.remove(
                engine,
                "after_cursor_execute",
                sql_profiler.after_cursor_execute,
            )

    total_elapsed_ms = (
        time.perf_counter() - total_start
    ) * 1000.0

    return (
        stages,
        total_elapsed_ms,
        sql_profiler,
        message_id,
    )


def print_report(
    stages: list[StageResult],
    total_ms: float,
    sql_profiler: SQLProfiler,
    message_id: int,
) -> None:
    print()
    print("=" * 110)
    print("CHAT CREATE_MESSAGE — STAGE-BY-STAGE APPLICATION PROFILE")
    print("=" * 110)
    print(f"Message ID:              {message_id}")
    print(f"Total service time:      {total_ms:,.3f} ms")
    print(f"SQL queries:             {sql_profiler.query_count}")
    print(
        f"SQL execution time:     "
        f"{sql_profiler.db_time_ms:,.3f} ms"
    )
    print(
        f"Measured stage time:    "
        f"{sum(stage.elapsed_ms for stage in stages):,.3f} ms"
    )
    print(
        f"Uninstrumented overhead: "
        f"{max(0.0, total_ms - sum(stage.elapsed_ms for stage in stages)):,.3f} ms"
    )
    print("=" * 110)

    print()
    print(
        f"{'#':>3}  "
        f"{'Stage':<58} "
        f"{'Time (ms)':>14} "
        f"{'% Total':>10}"
    )
    print("-" * 110)

    sorted_stages = sorted(
        stages,
        key=lambda item: item.elapsed_ms,
        reverse=True,
    )

    for index, stage in enumerate(
        sorted_stages,
        start=1,
    ):
        percentage = (
            stage.elapsed_ms / total_ms * 100.0
            if total_ms > 0
            else 0.0
        )

        print(
            f"{index:>3}  "
            f"{stage.name:<58} "
            f"{stage.elapsed_ms:>14,.3f} "
            f"{percentage:>9.2f}%"
        )

    print("-" * 110)

    print()
    print("EXECUTION ORDER")
    print("-" * 110)

    for index, stage in enumerate(
        stages,
        start=1,
    ):
        print(
            f"[{index:02d}] "
            f"{stage.name:<58} "
            f"{stage.elapsed_ms:>12,.3f} ms"
        )

    print()
    print("=" * 110)

    application_overhead = max(
        0.0,
        total_ms - sql_profiler.db_time_ms,
    )

    print(
        f"Application overhead:   "
        f"{application_overhead:,.3f} ms"
    )

    if total_ms > 0:
        print(
            f"DB share:               "
            f"{sql_profiler.db_time_ms / total_ms * 100.0:.2f}%"
        )
        print(
            f"Application share:      "
            f"{application_overhead / total_ms * 100.0:.2f}%"
        )

    print("=" * 110)
    print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Stage-by-stage profiler for "
            "Clinic System Pro chat create_message."
        )
    )

    parser.add_argument(
        "--clinic-id",
        type=int,
        default=DEFAULT_CLINIC_ID,
    )

    parser.add_argument(
        "--user-id",
        type=int,
        default=DEFAULT_USER_ID,
    )

    parser.add_argument(
        "--conversation-id",
        type=int,
        default=DEFAULT_CONVERSATION_ID,
    )

    parser.add_argument(
        "--content",
        type=str,
        default=DEFAULT_CONTENT,
    )

    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_RUNS,
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.runs <= 0:
        raise SystemExit(
            "--runs must be a positive integer"
        )

    app = create_app("development")

    results: list[
        tuple[
            list[StageResult],
            float,
            SQLProfiler,
            int,
        ]
    ] = []

    print()
    print("=" * 110)
    print("CLINIC SYSTEM PRO v5")
    print("CHAT CREATE_MESSAGE — APPLICATION STAGE PROFILER")
    print("=" * 110)
    print(f"Clinic:                  {args.clinic_id}")
    print(f"User:                    {args.user_id}")
    print(f"Conversation:            {args.conversation_id}")
    print(f"Runs:                    {args.runs}")
    print("=" * 110)

    for run_number in range(
        1,
        args.runs + 1,
    ):
        print(
            f"\nRunning profile "
            f"{run_number}/{args.runs}..."
        )

        try:
            result = run_once(
                app=app,
                clinic_id=args.clinic_id,
                user_id=args.user_id,
                conversation_id=args.conversation_id,
                content=args.content,
            )

            results.append(result)

        except Exception as exc:
            print()
            print(
                f"PROFILE FAILED: "
                f"{type(exc).__name__}: {exc}"
            )
            raise

    if not results:
        raise SystemExit(
            "No profiling results were produced."
        )

    if args.runs == 1:
        stages, total_ms, sql_profiler, message_id = (
            results[0]
        )

        print_report(
            stages=stages,
            total_ms=total_ms,
            sql_profiler=sql_profiler,
            message_id=message_id,
        )
        return

    stage_names = [
        stage.name
        for stage in results[0][0]
    ]

    stage_values: dict[str, list[float]] = {
        name: []
        for name in stage_names
    }

    totals: list[float] = []
    sql_times: list[float] = []
    query_counts: list[int] = []

    for stages, total_ms, sql_profiler, _ in results:
        totals.append(total_ms)
        sql_times.append(
            sql_profiler.db_time_ms,
        )
        query_counts.append(
            sql_profiler.query_count,
        )

        for stage in stages:
            stage_values.setdefault(
                stage.name,
                [],
            ).append(
                stage.elapsed_ms,
            )

    print()
    print("=" * 110)
    print(
        f"CHAT CREATE_MESSAGE — "
        f"{args.runs}-RUN SUMMARY"
    )
    print("=" * 110)

    print(
        f"Total time mean:        "
        f"{statistics.mean(totals):,.3f} ms"
    )
    print(
        f"Total time median:      "
        f"{statistics.median(totals):,.3f} ms"
    )
    print(
        f"Total time min:         "
        f"{min(totals):,.3f} ms"
    )
    print(
        f"Total time max:         "
        f"{max(totals):,.3f} ms"
    )
    print(
        f"SQL time mean:          "
        f"{statistics.mean(sql_times):,.3f} ms"
    )
    print(
        f"SQL queries mean:       "
        f"{statistics.mean(query_counts):,.2f}"
    )

    print("=" * 110)

    print()
    print(
        f"{'Stage':<58} "
        f"{'Mean':>12} "
        f"{'Median':>12} "
        f"{'Min':>12} "
        f"{'Max':>12}"
    )
    print("-" * 110)

    for name in sorted(
        stage_values,
        key=lambda stage_name: statistics.mean(
            stage_values[stage_name],
        ),
        reverse=True,
    ):
        values = stage_values[name]

        print(
            f"{name:<58} "
            f"{statistics.mean(values):>12,.3f} "
            f"{statistics.median(values):>12,.3f} "
            f"{min(values):>12,.3f} "
            f"{max(values):>12,.3f}"
        )

    print("=" * 110)
    print()


if __name__ == "__main__":
    main()