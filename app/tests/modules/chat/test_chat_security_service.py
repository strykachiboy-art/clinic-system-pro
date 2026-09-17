import pytest

from app.core.enums.chat_enums import ParticipantStatus

from app.extensions import db

from app.core.exceptions import (
    NotFoundError,
    ValidationError,
)

from app.modules.chat.models.conversation_model import (
    Conversation,
)
from app.modules.chat.models.conversation_participant_model import (
    ConversationParticipant,
)
from app.modules.chat.models.message_model import (
    Message,
)
from app.modules.chat.services.chat_security_service import (
    ChatSecurityService,
)



def _active_participant_status():
    return ParticipantStatus.ACCEPTED


def make_conversation(
    clinic,
    user,
    conversation_type,
):
    conversation = Conversation(
        clinic_id=clinic.id,
        conversation_type=conversation_type,
        created_by_id=user.id,
    )

    db.session.add(conversation)
    db.session.flush()

    return conversation


def make_participant(
    clinic,
    conversation,
    user,
):
    participant = ConversationParticipant(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        user_id=user.id,
        status=_active_participant_status(),
    )

    db.session.add(participant)
    db.session.flush()

    return participant


def make_message(
    clinic,
    conversation,
    user,
):
    message = Message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Test message",
    )

    db.session.add(message)
    db.session.flush()

    return message


def test_get_active_user_returns_active_user(
    db,
    make_user,
):
    user = make_user()

    result = ChatSecurityService.get_active_user(
        user.id
    )

    assert result.id == user.id


def test_get_active_user_rejects_missing_user(
    db,
):
    with pytest.raises(
        NotFoundError,
        match="User not found",
    ):
        ChatSecurityService.get_active_user(
            999999
        )


def test_get_active_user_rejects_invalid_id(
    db,
):
    with pytest.raises(
        ValidationError,
        match="User ID must be a positive integer",
    ):
        ChatSecurityService.get_active_user(
            0
        )


def test_ensure_same_clinic_allows_matching_clinic(
    db,
    make_user,
    make_clinic,
):
    clinic = make_clinic()
    user = make_user(
        clinic=clinic,
    )

    ChatSecurityService.ensure_same_clinic(
        user,
        clinic.id,
    )


def test_ensure_same_clinic_rejects_cross_clinic_access(
    db,
    make_user,
    make_clinic,
):
    clinic_one = make_clinic()
    clinic_two = make_clinic()

    user = make_user(
        clinic=clinic_one,
    )

    with pytest.raises(
        NotFoundError,
        match="Resource not found",
    ):
        ChatSecurityService.ensure_same_clinic(
            user,
            clinic_two.id,
        )


def test_get_conversation_returns_existing_conversation(
    db,
    make_user,
    make_clinic,
):
    clinic = make_clinic()
    user = make_user(
        clinic=clinic,
    )

    conversation = Conversation(
        clinic_id=clinic.id,
        created_by_id=user.id,
    )

    db.session.add(conversation)
    db.session.flush()

    result = ChatSecurityService.get_conversation(
        conversation.id
    )

    assert result.id == conversation.id


def test_get_conversation_rejects_missing_conversation(
    db,
):
    with pytest.raises(
        NotFoundError,
        match="Conversation not found",
    ):
        ChatSecurityService.get_conversation(
            999999
        )


def test_user_can_access_own_conversation(
    db,
    make_user,
    make_clinic,
):
    clinic = make_clinic()
    user = make_user(
        clinic=clinic,
    )

    conversation = Conversation(
        clinic_id=clinic.id,
        created_by_id=user.id,
    )

    db.session.add(conversation)
    db.session.flush()

    make_participant(
        clinic,
        conversation,
        user,
    )

    result = (
        ChatSecurityService
        .ensure_user_can_access_conversation(
            user.id,
            conversation.id,
        )
    )

    assert result.id == conversation.id


def test_user_cannot_access_conversation_without_participation(
    db,
    make_user,
    make_clinic,
):
    clinic = make_clinic()

    user = make_user(
        clinic=clinic,
    )

    other_user = make_user(
        clinic=clinic,
    )

    conversation = Conversation(
        clinic_id=clinic.id,
        created_by_id=other_user.id,
    )

    db.session.add(conversation)
    db.session.flush()

    make_participant(
        clinic,
        conversation,
        other_user,
    )

    with pytest.raises(
        NotFoundError,
        match="Conversation participant not found",
    ):
        ChatSecurityService.ensure_user_can_access_conversation(
            user.id,
            conversation.id,
        )


def test_user_cannot_access_cross_clinic_conversation(
    db,
    make_user,
    make_clinic,
):
    clinic_one = make_clinic()
    clinic_two = make_clinic()

    user_one = make_user(
        clinic=clinic_one,
    )

    user_two = make_user(
        clinic=clinic_two,
    )

    conversation = Conversation(
        clinic_id=clinic_two.id,
        created_by_id=user_two.id,
    )

    db.session.add(conversation)
    db.session.flush()

    make_participant(
        clinic_two,
        conversation,
        user_two,
    )

    with pytest.raises(
        NotFoundError,
        match="Resource not found",
    ):
        ChatSecurityService.ensure_user_can_access_conversation(
            user_one.id,
            conversation.id,
        )


def test_user_can_access_message_in_own_conversation(
    db,
    make_user,
    make_clinic,
):
    clinic = make_clinic()

    user = make_user(
        clinic=clinic,
    )

    conversation = Conversation(
        clinic_id=clinic.id,
        created_by_id=user.id,
    )

    db.session.add(conversation)
    db.session.flush()

    make_participant(
        clinic,
        conversation,
        user,
    )

    message = make_message(
        clinic,
        conversation,
        user,
    )

    result = (
        ChatSecurityService
        .ensure_user_can_access_message(
            user.id,
            message.id,
        )
    )

    assert result.id == message.id


def test_user_cannot_access_message_from_other_clinic(
    db,
    make_user,
    make_clinic,
):
    clinic_one = make_clinic()
    clinic_two = make_clinic()

    user_one = make_user(
        clinic=clinic_one,
    )

    user_two = make_user(
        clinic=clinic_two,
    )

    conversation = Conversation(
        clinic_id=clinic_two.id,
        created_by_id=user_two.id,
    )

    db.session.add(conversation)
    db.session.flush()

    make_participant(
        clinic_two,
        conversation,
        user_two,
    )

    message = make_message(
        clinic_two,
        conversation,
        user_two,
    )

    with pytest.raises(
        NotFoundError,
        match="Resource not found",
    ):
        ChatSecurityService.ensure_user_can_access_message(
            user_one.id,
            message.id,
        )


def test_user_can_edit_own_message(
    db,
    make_user,
    make_clinic,
):
    clinic = make_clinic()

    user = make_user(
        clinic=clinic,
    )

    conversation = Conversation(
        clinic_id=clinic.id,
        created_by_id=user.id,
    )

    db.session.add(conversation)
    db.session.flush()

    make_participant(
        clinic,
        conversation,
        user,
    )

    message = make_message(
        clinic,
        conversation,
        user,
    )

    result = (
        ChatSecurityService
        .ensure_user_can_edit_message(
            user.id,
            message.id,
        )
    )

    assert result.id == message.id


def test_user_cannot_edit_another_users_message(
    db,
    make_user,
    make_clinic,
):
    clinic = make_clinic()

    owner = make_user(
        clinic=clinic,
    )

    other_user = make_user(
        clinic=clinic,
    )

    conversation = Conversation(
        clinic_id=clinic.id,
        created_by_id=owner.id,
    )

    db.session.add(conversation)
    db.session.flush()

    make_participant(
        clinic,
        conversation,
        owner,
    )

    make_participant(
        clinic,
        conversation,
        other_user,
    )

    message = make_message(
        clinic,
        conversation,
        owner,
    )

    with pytest.raises(
        ValidationError,
        match="You can only modify your own message",
    ):
        ChatSecurityService.ensure_user_can_edit_message(
            other_user.id,
            message.id,
        )


def test_user_cannot_delete_another_users_message(
    db,
    make_user,
    make_clinic,
):
    clinic = make_clinic()

    owner = make_user(
        clinic=clinic,
    )

    other_user = make_user(
        clinic=clinic,
    )

    conversation = Conversation(
        clinic_id=clinic.id,
        created_by_id=owner.id,
    )

    db.session.add(conversation)
    db.session.flush()

    make_participant(
        clinic,
        conversation,
        owner,
    )

    make_participant(
        clinic,
        conversation,
        other_user,
    )

    message = make_message(
        clinic,
        conversation,
        owner,
    )

    with pytest.raises(
        ValidationError,
        match="You can only modify your own message",
    ):
        ChatSecurityService.ensure_user_can_delete_message(
            other_user.id,
            message.id,
        )


def test_participant_must_belong_to_conversation(
    db,
    make_user,
    make_clinic,
):
    clinic = make_clinic()

    user_one = make_user(
        clinic=clinic,
    )

    user_two = make_user(
        clinic=clinic,
    )

    conversation_one = Conversation(
        clinic_id=clinic.id,
        created_by_id=user_one.id,
    )

    conversation_two = Conversation(
        clinic_id=clinic.id,
        created_by_id=user_two.id,
    )

    db.session.add_all(
        [
            conversation_one,
            conversation_two,
        ]
    )
    db.session.flush()

    participant = make_participant(
        clinic,
        conversation_one,
        user_one,
    )

    with pytest.raises(
        NotFoundError,
        match="Conversation participant not found",
    ):
        ChatSecurityService.ensure_participant_belongs_to_conversation(
            participant,
            conversation_two,
        )