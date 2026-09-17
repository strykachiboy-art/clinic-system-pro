from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.core.enums.chat_enums import (
    ConversationType,
    MessageStatus,
    MessageType,
    ParticipantStatus,
)
from app.core.exceptions import (
    NotFoundError,
    ValidationError,
)
from app.modules.chat.services.conversation_service import (
    create_conversation,
    list_participants,
    update_participant,
)
from app.modules.chat.services.message_search_service import (
    search_messages,
)
from app.modules.chat.services.message_service import (
    create_message,
)


def _create_group_conversation(
    clinic,
    user,
    make_user,
    no_audit,
):
    other_user = make_user(
        clinic=clinic,
    )

    conversation = create_conversation(
        clinic_id=clinic.id,
        created_by_id=user.id,
        conversation_type=ConversationType.GROUP,
        participant_user_ids=[
            other_user.id,
        ],
    )

    return conversation, other_user


def _accept_participant(
    conversation,
    clinic_id,
    user_id,
):
    result = list_participants(
        conversation_id=conversation.id,
        clinic_id=clinic_id,
        status=ParticipantStatus.PENDING,
    )

    participant = next(
        item
        for item in result["items"]
        if item.user_id == user_id
    )

    return update_participant(
        participant_id=participant.id,
        clinic_id=clinic_id,
        status=ParticipantStatus.ACCEPTED,
    )


def test_search_messages_finds_matching_content(
    clinic,
    user,
    make_user,
    no_audit,
):
    conversation, _ = _create_group_conversation(
        clinic,
        user,
        make_user,
        no_audit,
    )

    matching = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Patient discharge planning",
    )

    create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Medication reminder",
    )

    result = search_messages(
        clinic_id=clinic.id,
        user_id=user.id,
        query="discharge",
    )

    assert result["total"] == 1
    assert result["items"][0].id == matching.id
    assert result["page"] == 1
    assert result["per_page"] == 50
    assert result["pages"] == 1
    assert result["has_next"] is False
    assert result["has_previous"] is False


def test_search_messages_is_case_insensitive(
    clinic,
    user,
    make_user,
    no_audit,
):
    conversation, _ = _create_group_conversation(
        clinic,
        user,
        make_user,
        no_audit,
    )

    message = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Emergency Department Review",
    )

    result = search_messages(
        clinic_id=clinic.id,
        user_id=user.id,
        query="eMeRgEnCy",
    )

    assert result["total"] == 1
    assert result["items"][0].id == message.id


def test_search_messages_returns_results_newest_first(
    clinic,
    user,
    make_user,
    no_audit,
):
    conversation, _ = _create_group_conversation(
        clinic,
        user,
        make_user,
        no_audit,
    )

    first = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Clinical follow-up first",
    )

    second = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Clinical follow-up second",
    )

    result = search_messages(
        clinic_id=clinic.id,
        user_id=user.id,
        query="clinical follow-up",
    )

    assert result["items"][0].id == second.id
    assert result["items"][1].id == first.id


def test_search_messages_filters_by_conversation(
    clinic,
    user,
    make_user,
    no_audit,
):
    first_conversation, _ = _create_group_conversation(
        clinic,
        user,
        make_user,
        no_audit,
    )

    second_conversation, _ = _create_group_conversation(
        clinic,
        user,
        make_user,
        no_audit,
    )

    first_message = create_message(
        clinic_id=clinic.id,
        conversation_id=first_conversation.id,
        sender_id=user.id,
        content="Shared clinical keyword",
    )

    second_message = create_message(
        clinic_id=clinic.id,
        conversation_id=second_conversation.id,
        sender_id=user.id,
        content="Shared clinical keyword",
    )

    result = search_messages(
        clinic_id=clinic.id,
        user_id=user.id,
        query="clinical keyword",
        conversation_id=first_conversation.id,
    )

    assert result["total"] == 1
    assert result["items"][0].id == first_message.id
    assert result["items"][0].id != second_message.id


def test_search_messages_filters_by_sender(
    clinic,
    user,
    make_user,
    no_audit,
):
    conversation, other_user = _create_group_conversation(
        clinic,
        user,
        make_user,
        no_audit,
    )

    _accept_participant(
        conversation,
        clinic.id,
        other_user.id,
    )

    first = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Clinical coordination",
    )

    second = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=other_user.id,
        content="Clinical coordination",
    )

    result = search_messages(
        clinic_id=clinic.id,
        user_id=user.id,
        query="clinical coordination",
        sender_id=other_user.id,
    )

    assert result["total"] == 1
    assert result["items"][0].id == second.id
    assert result["items"][0].id != first.id


def test_search_messages_filters_by_message_type(
    clinic,
    user,
    make_user,
    no_audit,
):
    conversation, _ = _create_group_conversation(
        clinic,
        user,
        make_user,
        no_audit,
    )

    text_message = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Clinical image",
        message_type=MessageType.TEXT,
    )

    image_message = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Clinical image",
        message_type=MessageType.IMAGE,
    )

    result = search_messages(
        clinic_id=clinic.id,
        user_id=user.id,
        query="Clinical image",
        message_type=MessageType.IMAGE,
    )

    assert result["total"] == 1
    assert result["items"][0].id == image_message.id
    assert result["items"][0].id != text_message.id


def test_search_messages_filters_by_status(
    clinic,
    user,
    make_user,
    no_audit,
):
    conversation, _ = _create_group_conversation(
        clinic,
        user,
        make_user,
        no_audit,
    )

    pending_message = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Status search message",
    )

    sent_message = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Status search message",
    )

    sent_message.status = MessageStatus.SENT
    db.session.flush()

    result = search_messages(
        clinic_id=clinic.id,
        user_id=user.id,
        query="Status search message",
        status=MessageStatus.SENT,
    )

    assert result["total"] == 1
    assert result["items"][0].id == sent_message.id
    assert result["items"][0].id != pending_message.id


def test_search_messages_excludes_deleted_messages(
    clinic,
    user,
    make_user,
    no_audit,
):
    conversation, _ = _create_group_conversation(
        clinic,
        user,
        make_user,
        no_audit,
    )

    message = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Deleted searchable message",
    )

    message.status = MessageStatus.DELETED
    db.session.flush()

    result = search_messages(
        clinic_id=clinic.id,
        user_id=user.id,
        query="Deleted searchable message",
    )

    assert result["total"] == 0
    assert result["items"] == []


def test_search_messages_cannot_return_deleted_messages_with_deleted_status_filter(
    clinic,
    user,
    make_user,
    no_audit,
):
    conversation, _ = _create_group_conversation(
        clinic,
        user,
        make_user,
        no_audit,
    )

    message = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Deleted status search",
    )

    message.status = MessageStatus.DELETED
    db.session.flush()

    result = search_messages(
        clinic_id=clinic.id,
        user_id=user.id,
        query="Deleted status search",
        status=MessageStatus.DELETED,
    )

    assert result["total"] == 0
    assert result["items"] == []


def test_search_messages_filters_by_start_date(
    clinic,
    user,
    make_user,
    no_audit,
):
    conversation, _ = _create_group_conversation(
        clinic,
        user,
        make_user,
        no_audit,
    )

    old_message = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Date range clinical message",
    )

    new_message = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Date range clinical message",
    )

    old_message.created_at = (
        datetime.now(timezone.utc)
        - timedelta(days=2)
    )

    new_message.created_at = (
        datetime.now(timezone.utc)
        - timedelta(hours=1)
    )

    db.session.flush()

    result = search_messages(
        clinic_id=clinic.id,
        user_id=user.id,
        query="Date range clinical message",
        start_at=(
            datetime.now(timezone.utc)
            - timedelta(days=1)
        ),
    )

    assert result["total"] == 1
    assert result["items"][0].id == new_message.id
    assert result["items"][0].id != old_message.id


def test_search_messages_filters_by_end_date(
    clinic,
    user,
    make_user,
    no_audit,
):
    conversation, _ = _create_group_conversation(
        clinic,
        user,
        make_user,
        no_audit,
    )

    old_message = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="End date clinical message",
    )

    new_message = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="End date clinical message",
    )

    old_message.created_at = (
        datetime.now(timezone.utc)
        - timedelta(days=2)
    )

    new_message.created_at = (
        datetime.now(timezone.utc)
        - timedelta(hours=1)
    )

    db.session.flush()

    result = search_messages(
        clinic_id=clinic.id,
        user_id=user.id,
        query="End date clinical message",
        end_at=(
            datetime.now(timezone.utc)
            - timedelta(days=1)
        ),
    )

    assert result["total"] == 1
    assert result["items"][0].id == old_message.id
    assert result["items"][0].id != new_message.id


def test_search_messages_rejects_empty_query(
    clinic,
    user,
    no_audit,
):
    with pytest.raises(ValidationError):
        search_messages(
            clinic_id=clinic.id,
            user_id=user.id,
            query="   ",
        )


def test_search_messages_rejects_non_string_query(
    clinic,
    user,
    no_audit,
):
    with pytest.raises(ValidationError):
        search_messages(
            clinic_id=clinic.id,
            user_id=user.id,
            query=123,
        )


def test_search_messages_rejects_long_query(
    clinic,
    user,
    no_audit,
):
    with pytest.raises(ValidationError):
        search_messages(
            clinic_id=clinic.id,
            user_id=user.id,
            query="x" * 201,
        )


def test_search_messages_rejects_invalid_conversation_id(
    clinic,
    user,
    no_audit,
):
    with pytest.raises(ValidationError):
        search_messages(
            clinic_id=clinic.id,
            user_id=user.id,
            query="clinical",
            conversation_id=0,
        )


def test_search_messages_rejects_invalid_sender_id(
    clinic,
    user,
    no_audit,
):
    with pytest.raises(ValidationError):
        search_messages(
            clinic_id=clinic.id,
            user_id=user.id,
            query="clinical",
            sender_id=0,
        )


def test_search_messages_rejects_invalid_pagination(
    clinic,
    user,
    no_audit,
):
    with pytest.raises(ValidationError):
        search_messages(
            clinic_id=clinic.id,
            user_id=user.id,
            query="clinical",
            page=0,
        )

    with pytest.raises(ValidationError):
        search_messages(
            clinic_id=clinic.id,
            user_id=user.id,
            query="clinical",
            per_page=0,
        )

    with pytest.raises(ValidationError):
        search_messages(
            clinic_id=clinic.id,
            user_id=user.id,
            query="clinical",
            per_page=501,
        )


def test_search_messages_rejects_invalid_date_range(
    clinic,
    user,
    no_audit,
):
    start_at = datetime.now(timezone.utc)
    end_at = start_at - timedelta(minutes=1)

    with pytest.raises(ValidationError):
        search_messages(
            clinic_id=clinic.id,
            user_id=user.id,
            query="clinical",
            start_at=start_at,
            end_at=end_at,
        )


def test_search_messages_rejects_invalid_start_date_type(
    clinic,
    user,
    no_audit,
):
    with pytest.raises(ValidationError):
        search_messages(
            clinic_id=clinic.id,
            user_id=user.id,
            query="clinical",
            start_at="2026-09-17",
        )


def test_search_messages_rejects_invalid_end_date_type(
    clinic,
    user,
    no_audit,
):
    with pytest.raises(ValidationError):
        search_messages(
            clinic_id=clinic.id,
            user_id=user.id,
            query="clinical",
            end_at="2026-09-17",
        )


def test_search_messages_rejects_wrong_clinic(
    clinic,
    user,
    no_audit,
):
    with pytest.raises(NotFoundError):
        search_messages(
            clinic_id=999999,
            user_id=user.id,
            query="clinical",
        )


def test_search_messages_excludes_outsider_results(
    clinic,
    user,
    make_user,
    no_audit,
):
    conversation, _ = _create_group_conversation(
        clinic,
        user,
        make_user,
        no_audit,
    )

    message = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Restricted clinical message",
    )

    outsider = make_user(
        clinic=clinic,
    )

    result = search_messages(
        clinic_id=clinic.id,
        user_id=outsider.id,
        query="Restricted clinical message",
    )

    assert result["total"] == 0
    assert result["items"] == []
    assert message.id is not None


def test_search_messages_rejects_conversation_user_without_access(
    clinic,
    user,
    make_user,
    no_audit,
):
    conversation, _ = _create_group_conversation(
        clinic,
        user,
        make_user,
        no_audit,
    )

    inaccessible_conversation, _ = _create_group_conversation(
        clinic,
        user,
        make_user,
        no_audit,
    )

    result = search_messages(
        clinic_id=clinic.id,
        user_id=user.id,
        query="anything",
        conversation_id=inaccessible_conversation.id,
    )

    assert result["total"] == 0
    assert result["items"] == []

    assert conversation.id != inaccessible_conversation.id


def test_search_messages_paginates_results(
    clinic,
    user,
    make_user,
    no_audit,
):
    conversation, _ = _create_group_conversation(
        clinic,
        user,
        make_user,
        no_audit,
    )

    for index in range(5):
        create_message(
            clinic_id=clinic.id,
            conversation_id=conversation.id,
            sender_id=user.id,
            content=f"Pagination clinical message {index}",
        )

    first_page = search_messages(
        clinic_id=clinic.id,
        user_id=user.id,
        query="Pagination clinical message",
        page=1,
        per_page=2,
    )

    second_page = search_messages(
        clinic_id=clinic.id,
        user_id=user.id,
        query="Pagination clinical message",
        page=2,
        per_page=2,
    )

    assert first_page["total"] == 5
    assert first_page["pages"] == 3
    assert first_page["has_next"] is True
    assert first_page["has_previous"] is False

    assert second_page["page"] == 2
    assert second_page["per_page"] == 2
    assert second_page["has_next"] is True
    assert second_page["has_previous"] is True

    first_ids = {
        message.id
        for message in first_page["items"]
    }

    second_ids = {
        message.id
        for message in second_page["items"]
    }

    assert first_ids.isdisjoint(second_ids)