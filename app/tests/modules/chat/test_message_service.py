from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.core.enums.chat_enums import (
    ConversationType,
    MessagePriority,
    MessageStatus,
    MessageType,
    ParticipantStatus,
)
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.chat.models.message_model import Message
from app.modules.chat.models.message_revision_model import MessageRevision
from app.modules.chat.services.conversation_service import (
    create_conversation,
    list_participants,
    update_participant,
)
from app.modules.chat.services.message_service import (
    create_message,
    delete_message,
    edit_message,
    get_message,
    list_messages,
)
from app.modules.settings.models.clinic_settings import (
    ClinicSettings,
)


def _create_group_conversation(
    clinic,
    user,
    make_user,
    no_audit,
):
    other_user = make_user(clinic=clinic)

    conversation = create_conversation(
        clinic_id=clinic.id,
        created_by_id=user.id,
        conversation_type=ConversationType.GROUP,
        participant_user_ids=[other_user.id],
    )

    return conversation, other_user


def _get_or_create_settings(
    clinic,
):
    settings = db.session.execute(
        db.select(ClinicSettings).where(
            ClinicSettings.clinic_id == clinic.id,
        )
    ).scalar_one_or_none()

    if settings is None:
        settings = ClinicSettings(
            clinic_id=clinic.id,
        )
        db.session.add(settings)
        db.session.flush()

    return settings


def _update_chat_security_preference(
    clinic,
    key: str,
    value,
):
    settings = _get_or_create_settings(
        clinic,
    )

    current_security_preferences = (
        settings.security_preferences
        if isinstance(
            settings.security_preferences,
            dict,
        )
        else {}
    )

    current_chat_preferences = (
        current_security_preferences.get(
            "chat",
        )
        if isinstance(
            current_security_preferences.get("chat"),
            dict,
        )
        else {}
    )

    updated_chat_preferences = {
        **current_chat_preferences,
        key: value,
    }

    settings.security_preferences = {
        **current_security_preferences,
        "chat": updated_chat_preferences,
    }

    db.session.flush()


def test_create_message(
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
        content="Hello clinical team",
    )

    assert message.id is not None
    assert message.clinic_id == clinic.id
    assert message.conversation_id == conversation.id
    assert message.sender_id == user.id
    assert message.message_type == MessageType.TEXT
    assert message.content == "Hello clinical team"
    assert message.status == MessageStatus.PENDING
    assert message.priority == MessagePriority.NORMAL
    assert message.reply_to_message_id is None


def test_create_message_normalizes_content(
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
        content="   Hello team   ",
    )

    assert message.content == "Hello team"


def test_create_message_requires_content_for_text(
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

    with pytest.raises(ValidationError):
        create_message(
            clinic_id=clinic.id,
            conversation_id=conversation.id,
            sender_id=user.id,
            content="   ",
            message_type=MessageType.TEXT,
        )


def test_create_message_rejects_invalid_sender(
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

    with pytest.raises(NotFoundError):
        create_message(
            clinic_id=clinic.id,
            conversation_id=conversation.id,
            sender_id=999999,
            content="Hello",
        )


def test_create_message_rejects_non_participant(
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

    outsider = make_user(clinic=clinic)

    with pytest.raises(NotFoundError):
        create_message(
            clinic_id=clinic.id,
            conversation_id=conversation.id,
            sender_id=outsider.id,
            content="Unauthorized message",
        )


def test_create_message_rejects_wrong_clinic(
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

    with pytest.raises(NotFoundError):
        create_message(
            clinic_id=999999,
            conversation_id=conversation.id,
            sender_id=user.id,
            content="Hello",
        )


def test_create_message_updates_conversation_last_message_at(
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

    assert conversation.last_message_at is None

    message = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="New clinical message",
    )

    db.session.refresh(
        conversation,
    )

    assert conversation.last_message_at is not None
    assert conversation.last_message_at >= message.created_at


def test_create_message_supports_priority(
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
        content="Urgent clinical message",
        priority=MessagePriority.URGENT,
    )

    assert message.priority == MessagePriority.URGENT


def test_create_message_rejects_system_message(
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

    with pytest.raises(ValidationError):
        create_message(
            clinic_id=clinic.id,
            conversation_id=conversation.id,
            sender_id=user.id,
            content="System event",
            message_type=MessageType.SYSTEM,
        )


def test_create_message_supports_reply(
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
        content="Original message",
    )

    reply = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Reply message",
        reply_to_message_id=first.id,
    )

    assert reply.reply_to_message_id == first.id
    assert reply.reply_to is not None
    assert reply.reply_to.id == first.id


def test_create_message_rejects_reply_from_other_conversation(
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

    other_user = make_user(
        clinic=clinic,
    )

    second_conversation = create_conversation(
        clinic_id=clinic.id,
        created_by_id=user.id,
        conversation_type=ConversationType.GROUP,
        participant_user_ids=[other_user.id],
    )

    original = create_message(
        clinic_id=clinic.id,
        conversation_id=second_conversation.id,
        sender_id=user.id,
        content="Message in another conversation",
    )

    with pytest.raises(NotFoundError):
        create_message(
            clinic_id=clinic.id,
            conversation_id=first_conversation.id,
            sender_id=user.id,
            content="Invalid reply",
            reply_to_message_id=original.id,
        )


def test_create_message_rejects_missing_reply_message(
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

    with pytest.raises(NotFoundError):
        create_message(
            clinic_id=clinic.id,
            conversation_id=conversation.id,
            sender_id=user.id,
            content="Invalid reply",
            reply_to_message_id=999999,
        )


def test_get_message(
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
        content="Readable message",
    )

    result = get_message(
        message_id=message.id,
        clinic_id=clinic.id,
        user_id=user.id,
    )

    assert result.id == message.id
    assert result.content == "Readable message"


def test_get_message_rejects_wrong_clinic(
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
        content="Clinical message",
    )

    with pytest.raises(NotFoundError):
        get_message(
            message_id=message.id,
            clinic_id=999999,
            user_id=user.id,
        )


def test_get_message_rejects_non_participant(
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
        content="Private clinical message",
    )

    outsider = make_user(
        clinic=clinic,
    )

    with pytest.raises(NotFoundError):
        get_message(
            message_id=message.id,
            clinic_id=clinic.id,
            user_id=outsider.id,
        )


def test_get_message_rejects_missing_message(
    clinic,
    user,
    no_audit,
):
    with pytest.raises(NotFoundError):
        get_message(
            message_id=999999,
            clinic_id=clinic.id,
            user_id=user.id,
        )


def test_list_messages(
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
        content="First message",
    )

    second = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Second message",
    )

    result = list_messages(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        user_id=user.id,
    )

    assert result["total"] == 2
    assert len(result["items"]) == 2
    assert result["page"] == 1
    assert result["per_page"] == 50
    assert result["pages"] == 1
    assert result["has_next"] is False
    assert result["has_previous"] is False

    assert result["items"][0].id == second.id
    assert result["items"][1].id == first.id


def test_list_messages_filters_by_status(
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
        content="Pending message",
    )

    sent_message = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Sent message",
    )

    sent_message.status = MessageStatus.SENT
    db.session.flush()

    result = list_messages(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        user_id=user.id,
        status=MessageStatus.SENT,
    )

    assert result["total"] == 1
    assert result["items"][0].id == sent_message.id
    assert result["items"][0].id != pending_message.id


def test_list_messages_filters_by_type(
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
        content="Text message",
        message_type=MessageType.TEXT,
    )

    image_message = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Image placeholder",
        message_type=MessageType.IMAGE,
    )

    result = list_messages(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        user_id=user.id,
        message_type=MessageType.IMAGE,
    )

    assert result["total"] == 1
    assert result["items"][0].id == image_message.id
    assert result["items"][0].id != text_message.id


def test_list_messages_search(
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

    result = list_messages(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        user_id=user.id,
        search="discharge",
    )

    assert result["total"] == 1
    assert result["items"][0].id == matching.id


def test_list_messages_rejects_non_participant(
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

    outsider = make_user(
        clinic=clinic,
    )

    with pytest.raises(NotFoundError):
        list_messages(
            clinic_id=clinic.id,
            conversation_id=conversation.id,
            user_id=outsider.id,
        )


def test_list_messages_pagination_validation(
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

    with pytest.raises(ValidationError):
        list_messages(
            clinic_id=clinic.id,
            conversation_id=conversation.id,
            user_id=user.id,
            page=0,
        )

    with pytest.raises(ValidationError):
        list_messages(
            clinic_id=clinic.id,
            conversation_id=conversation.id,
            user_id=user.id,
            per_page=0,
        )

    with pytest.raises(ValidationError):
        list_messages(
            clinic_id=clinic.id,
            conversation_id=conversation.id,
            user_id=user.id,
            per_page=501,
        )


def test_edit_message(
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
        content="Original content",
    )

    updated = edit_message(
        message_id=message.id,
        clinic_id=clinic.id,
        user_id=user.id,
        content="Updated content",
    )

    assert updated.id == message.id
    assert updated.content == "Updated content"
    assert updated.status == MessageStatus.EDITED
    assert updated.edited_at is not None


def test_edit_message_creates_revision(
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
        content="Original content",
    )

    edit_message(
        message_id=message.id,
        clinic_id=clinic.id,
        user_id=user.id,
        content="Updated content",
    )

    revisions = db.session.execute(
        db.select(MessageRevision)
        .where(
            MessageRevision.message_id == message.id,
        )
        .order_by(
            MessageRevision.revision_number.asc(),
        )
    ).scalars().all()

    assert len(revisions) == 1
    assert revisions[0].revision_number == 1
    assert revisions[0].previous_content == "Original content"
    assert revisions[0].previous_message_type == "text"
    assert revisions[0].edited_by_id == user.id


def test_multiple_edits_increment_revision_number(
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
        content="Version one",
    )

    edit_message(
        message_id=message.id,
        clinic_id=clinic.id,
        user_id=user.id,
        content="Version two",
    )

    edit_message(
        message_id=message.id,
        clinic_id=clinic.id,
        user_id=user.id,
        content="Version three",
    )

    revisions = db.session.execute(
        db.select(MessageRevision)
        .where(
            MessageRevision.message_id == message.id,
        )
        .order_by(
            MessageRevision.revision_number.asc(),
        )
    ).scalars().all()

    assert len(revisions) == 2
    assert revisions[0].revision_number == 1
    assert revisions[0].previous_content == "Version one"
    assert revisions[1].revision_number == 2
    assert revisions[1].previous_content == "Version two"


def test_edit_message_rejects_empty_content(
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
        content="Original",
    )

    with pytest.raises(ValidationError):
        edit_message(
            message_id=message.id,
            clinic_id=clinic.id,
            user_id=user.id,
            content="   ",
        )


def test_edit_message_rejects_non_owner(
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

    message = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Owner only message",
    )

    pending = list_participants(
        conversation_id=conversation.id,
        clinic_id=clinic.id,
        status=ParticipantStatus.PENDING,
    )["items"][0]

    update_participant(
        participant_id=pending.id,
        clinic_id=clinic.id,
        status=ParticipantStatus.ACCEPTED,
    )

    with pytest.raises(ValidationError):
        edit_message(
            message_id=message.id,
            clinic_id=clinic.id,
            user_id=other_user.id,
            content="Unauthorized edit",
        )


def test_edit_message_rejects_deleted_message(
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
        content="Message to delete",
    )

    delete_message(
        message_id=message.id,
        clinic_id=clinic.id,
        user_id=user.id,
    )

    with pytest.raises(ConflictError):
        edit_message(
            message_id=message.id,
            clinic_id=clinic.id,
            user_id=user.id,
            content="Attempted edit",
        )


def test_edit_message_rejects_expired_edit_window(
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

    old_time = (
        datetime.now(
            timezone.utc,
        )
        - timedelta(minutes=16)
    )

    message = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Old message",
    )

    message.created_at = old_time
    db.session.flush()

    with pytest.raises(ValidationError):
        edit_message(
            message_id=message.id,
            clinic_id=clinic.id,
            user_id=user.id,
            content="Too late",
        )


def test_delete_message(
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
        content="Message to delete",
    )

    deleted = delete_message(
        message_id=message.id,
        clinic_id=clinic.id,
        user_id=user.id,
    )

    assert deleted.id == message.id
    assert deleted.status == MessageStatus.DELETED
    assert deleted.deleted_at is not None


def test_delete_message_is_soft_delete(
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
        content="Persistent message",
    )

    original_id = message.id

    delete_message(
        message_id=message.id,
        clinic_id=clinic.id,
        user_id=user.id,
    )

    db.session.expire_all()

    stored = db.session.get(
        Message,
        original_id,
    )

    assert stored is not None
    assert stored.status == MessageStatus.DELETED
    assert stored.deleted_at is not None


def test_delete_message_rejects_non_owner(
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

    pending = list_participants(
        conversation_id=conversation.id,
        clinic_id=clinic.id,
        status=ParticipantStatus.PENDING,
    )["items"][0]

    update_participant(
        participant_id=pending.id,
        clinic_id=clinic.id,
        status=ParticipantStatus.ACCEPTED,
    )

    message = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Owner only deletion",
    )

    with pytest.raises(ValidationError):
        delete_message(
            message_id=message.id,
            clinic_id=clinic.id,
            user_id=other_user.id,
        )


def test_delete_message_rejects_deleted_message(
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
        content="Delete once",
    )

    delete_message(
        message_id=message.id,
        clinic_id=clinic.id,
        user_id=user.id,
    )

    with pytest.raises(ConflictError):
        delete_message(
            message_id=message.id,
            clinic_id=clinic.id,
            user_id=user.id,
        )


def test_delete_message_rejects_expired_delete_window(
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

    old_time = (
        datetime.now(
            timezone.utc,
        )
        - timedelta(minutes=16)
    )

    message = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Expired deletion message",
    )

    message.created_at = old_time
    db.session.flush()

    with pytest.raises(ValidationError):
        delete_message(
            message_id=message.id,
            clinic_id=clinic.id,
            user_id=user.id,
        )


def test_edit_message_same_content_does_not_create_revision(
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
        content="Same content",
    )

    updated = edit_message(
        message_id=message.id,
        clinic_id=clinic.id,
        user_id=user.id,
        content="Same content",
    )

    revisions = db.session.execute(
        db.select(MessageRevision)
        .where(
            MessageRevision.message_id == message.id,
        )
    ).scalars().all()

    assert updated.content == "Same content"
    assert updated.status == MessageStatus.PENDING
    assert updated.edited_at is None
    assert revisions == []


def test_message_search_rejects_long_search_term(
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

    with pytest.raises(ValidationError):
        list_messages(
            clinic_id=clinic.id,
            conversation_id=conversation.id,
            user_id=user.id,
            search="x" * 201,
        )


def test_message_content_length_is_checked_by_policy(
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

    content = "x" * 10001

    with pytest.raises(ValidationError):
        create_message(
            clinic_id=clinic.id,
            conversation_id=conversation.id,
            sender_id=user.id,
            content=content,
        )


def test_message_edit_content_length_is_checked_by_policy(
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
        content="Original",
    )

    with pytest.raises(ValidationError):
        edit_message(
            message_id=message.id,
            clinic_id=clinic.id,
            user_id=user.id,
            content="x" * 10001,
        )


def test_create_message_blocks_hard_explicit_content(
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

    with pytest.raises(ValidationError):
        create_message(
            clinic_id=clinic.id,
            conversation_id=conversation.id,
            sender_id=user.id,
            content="send me your nudes",
        )

    stored_messages = db.session.execute(
        db.select(Message).where(
            Message.clinic_id == clinic.id,
            Message.conversation_id == conversation.id,
        )
    ).scalars().all()

    assert stored_messages == []


def test_create_message_allows_clinical_sensitive_content(
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
        content="Patient reports vaginal bleeding.",
    )

    assert message.content == "Patient reports vaginal bleeding."


def test_create_message_respects_clinic_content_setting(
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

    _update_chat_security_preference(
        clinic,
        "external_links_allowed",
        False,
    )

    with pytest.raises(ValidationError):
        create_message(
            clinic_id=clinic.id,
            conversation_id=conversation.id,
            sender_id=user.id,
            content="Review this: https://example.com",
        )

    stored_messages = db.session.execute(
        db.select(Message).where(
            Message.clinic_id == clinic.id,
            Message.conversation_id == conversation.id,
        )
    ).scalars().all()

    assert stored_messages == []


def test_edit_message_blocks_hard_explicit_content(
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
        content="Original safe content",
    )

    with pytest.raises(ValidationError):
        edit_message(
            message_id=message.id,
            clinic_id=clinic.id,
            user_id=user.id,
            content="send me your nudes",
        )

    db.session.expire_all()

    stored = db.session.get(
        Message,
        message.id,
    )

    assert stored is not None
    assert stored.content == "Original safe content"
    assert stored.status == MessageStatus.PENDING

    revisions = db.session.execute(
        db.select(MessageRevision).where(
            MessageRevision.message_id == message.id,
        )
    ).scalars().all()

    assert revisions == []


def test_edit_message_allows_clinical_sensitive_content(
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
        content="Initial clinical note",
    )

    updated = edit_message(
        message_id=message.id,
        clinic_id=clinic.id,
        user_id=user.id,
        content="Patient reports vaginal bleeding.",
    )

    assert updated.content == (
        "Patient reports vaginal bleeding."
    )
    assert updated.status == MessageStatus.EDITED