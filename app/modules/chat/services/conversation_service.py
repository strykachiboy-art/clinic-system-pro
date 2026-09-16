from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func

from app.extensions import db
from app.core.audit.services.audit_service import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.chat_enums import (
    ConversationStatus,
    ConversationType,
    ParticipantRole,
    ParticipantStatus,
)
from app.core.enums.appointment_enums import AppointmentStatus
from app.core.enums.consultation_enums import ConsultationStatus
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import transactional

from app.modules.appointment.models.appointment_model import Appointment
from app.modules.clinic.models.clinic_model import Clinic
from app.modules.clinic.services.clinic_service import (
    ensure_clinic_active,
    get_clinic,
)
from app.modules.consultation.models.consultation_model import Consultation
from app.core.auth.user.models.user_model import User
from app.modules.patient.models.patient_model import Patient
from app.modules.staff.models.staff_model import Staff

from app.modules.chat.models.conversation_model import Conversation
from app.modules.chat.models.conversation_participant_model import (
    ConversationParticipant,
)


DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 500
MAX_INITIAL_PARTICIPANTS = 500


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================================
# VALIDATION HELPERS
# ============================================================================


def _validate_positive_id(
    value,
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


def _validate_pagination(
    page,
    per_page,
):
    if (
        isinstance(page, bool)
        or not isinstance(page, int)
        or page <= 0
    ):
        raise ValidationError(
            "Page must be a positive integer"
        )

    if (
        isinstance(per_page, bool)
        or not isinstance(per_page, int)
        or per_page <= 0
    ):
        raise ValidationError(
            "Per-page must be a positive integer"
        )

    if per_page > MAX_PER_PAGE:
        raise ValidationError(
            f"Per-page cannot exceed {MAX_PER_PAGE}"
        )

    return page, per_page


def _normalize_enum(
    value,
    enum_class,
    field_name: str,
):
    if isinstance(value, enum_class):
        return value

    try:
        return enum_class(value)
    except (TypeError, ValueError):
        raise ValidationError(
            f"Invalid {field_name}"
        )


def _normalize_optional_text(
    value,
    field_name: str,
    max_length: int,
):
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValidationError(
            f"{field_name} must be a string"
        )

    value = value.strip()

    if not value:
        return None

    if len(value) > max_length:
        raise ValidationError(
            f"{field_name} cannot exceed "
            f"{max_length} characters"
        )

    return value


def _get_user(
    user_id: int,
    *,
    clinic_id: int | None = None,
    active_only: bool = False,
) -> User:
    _validate_positive_id(
        user_id,
        "User ID",
    )

    query = db.select(User).where(
        User.id == user_id
    )

    if clinic_id is not None:
        query = query.where(
            User.clinic_id == clinic_id
        )

    if active_only:
        query = query.where(
            User.is_active.is_(True)
        )

    user = db.session.execute(query).scalar_one_or_none()

    if user is None:
        raise NotFoundError(
            f"User {user_id} not found"
        )

    return user


def _get_patient(
    patient_id: int,
    clinic_id: int,
    *,
    active_only: bool = False,
) -> Patient:
    _validate_positive_id(
        patient_id,
        "Patient ID",
    )

    query = db.select(Patient).where(
        Patient.id == patient_id,
        Patient.clinic_id == clinic_id,
    )

    if active_only:
        query = query.where(
            Patient.is_active.is_(True)
        )

    patient = db.session.execute(query).scalar_one_or_none()

    if patient is None:
        raise NotFoundError(
            f"Patient {patient_id} not found"
        )

    return patient


def _get_appointment(
    appointment_id: int,
    clinic_id: int,
) -> Appointment:
    _validate_positive_id(
        appointment_id,
        "Appointment ID",
    )

    appointment = db.session.execute(
        db.select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.clinic_id == clinic_id,
        )
    ).scalar_one_or_none()

    if appointment is None:
        raise NotFoundError(
            f"Appointment {appointment_id} not found"
        )

    return appointment


def _get_consultation(
    consultation_id: int,
    clinic_id: int,
) -> Consultation:
    _validate_positive_id(
        consultation_id,
        "Consultation ID",
    )

    consultation = db.session.execute(
        db.select(Consultation).where(
            Consultation.id == consultation_id,
            Consultation.clinic_id == clinic_id,
        )
    ).scalar_one_or_none()

    if consultation is None:
        raise NotFoundError(
            f"Consultation {consultation_id} not found"
        )

    return consultation


def _get_conversation(
    conversation_id: int,
    *,
    clinic_id: int | None = None,
    lock: bool = False,
) -> Conversation:
    _validate_positive_id(
        conversation_id,
        "Conversation ID",
    )

    query = db.select(Conversation).where(
        Conversation.id == conversation_id
    )

    if clinic_id is not None:
        query = query.where(
            Conversation.clinic_id == clinic_id
        )

    if lock:
        query = query.with_for_update()

    conversation = db.session.execute(
        query
    ).scalar_one_or_none()

    if conversation is None:
        raise NotFoundError(
            f"Conversation {conversation_id} not found"
        )

    return conversation


def _get_participant(
    participant_id: int,
    *,
    clinic_id: int | None = None,
    conversation_id: int | None = None,
    lock: bool = False,
) -> ConversationParticipant:
    _validate_positive_id(
        participant_id,
        "Participant ID",
    )

    query = db.select(
        ConversationParticipant
    ).where(
        ConversationParticipant.id == participant_id
    )

    if clinic_id is not None:
        query = query.where(
            ConversationParticipant.clinic_id == clinic_id
        )

    if conversation_id is not None:
        query = query.where(
            ConversationParticipant.conversation_id
            == conversation_id
        )

    if lock:
        query = query.with_for_update()

    participant = db.session.execute(
        query
    ).scalar_one_or_none()

    if participant is None:
        raise NotFoundError(
            f"Conversation participant "
            f"{participant_id} not found"
        )

    return participant


def _validate_conversation_participant(
    conversation: Conversation,
    user_id: int,
) -> User:
    user = _get_user(
        user_id,
        clinic_id=conversation.clinic_id,
        active_only=True,
    )

    return user


def _get_active_staff_for_user(
    user_id: int,
    clinic_id: int,
) -> Staff | None:
    """
    Return the active staff record linked to a user, if one exists.

    A user without an active staff record is not treated as staff for the
    patient-conversation access rule. This preserves patient-user and other
    non-staff account flows while applying the restriction to staff accounts.
    """
    staff = db.session.execute(
        db.select(Staff).where(
            Staff.user_id == user_id,
            Staff.clinic_id == clinic_id,
            Staff.status == StaffStatus.ACTIVE,
        )
    ).scalar_one_or_none()

    return staff


def _staff_has_patient_relationship(
    *,
    staff_id: int,
    clinic_id: int,
    patient_id: int,
) -> bool:
    """
    Determine whether a staff member has an established relationship with
    a patient through the clinic's existing care records.

    An assigned appointment or consultation is sufficient. Cancelled
    appointments/consultations do not establish access. Historical completed
    records remain valid evidence of an established relationship.
    """
    appointment_exists = db.session.scalar(
        db.select(Appointment.id).where(
            Appointment.clinic_id == clinic_id,
            Appointment.patient_id == patient_id,
            Appointment.staff_id == staff_id,
            Appointment.status != AppointmentStatus.CANCELLED,
        ).limit(1)
    )

    if appointment_exists is not None:
        return True

    consultation_exists = db.session.scalar(
        db.select(Consultation.id).where(
            Consultation.clinic_id == clinic_id,
            Consultation.patient_id == patient_id,
            Consultation.staff_id == staff_id,
            Consultation.status != ConsultationStatus.CANCELLED,
        ).limit(1)
    )

    return consultation_exists is not None


def _validate_staff_patient_relationship(
    *,
    user_id: int,
    clinic_id: int,
    patient_id: int,
) -> None:
    """
    Enforce the patient-conversation access boundary for staff users.

    Staff cannot create or be added to a patient-context conversation merely
    because both accounts belong to the same clinic. A legitimate clinic
    relationship must already exist through an appointment or consultation.
    """
    staff = _get_active_staff_for_user(
        user_id,
        clinic_id,
    )

    if staff is None:
        return

    if not _staff_has_patient_relationship(
        staff_id=staff.id,
        clinic_id=clinic_id,
        patient_id=patient_id,
    ):
        raise ValidationError(
            "Staff member is not authorized to open or join a conversation "
            "for this patient because no valid appointment or consultation "
            "relationship exists"
        )


def _validate_context_links(
    conversation_clinic_id: int,
    patient_id: int | None = None,
    appointment_id: int | None = None,
    consultation_id: int | None = None,
):
    if patient_id is not None:
        patient = _get_patient(
            patient_id,
            conversation_clinic_id,
            active_only=True,
        )
    else:
        patient = None

    appointment = None
    consultation = None

    if appointment_id is not None:
        appointment = _get_appointment(
            appointment_id,
            conversation_clinic_id,
        )

    if consultation_id is not None:
        consultation = _get_consultation(
            consultation_id,
            conversation_clinic_id,
        )

    if appointment is not None and (
        patient is not None
        and appointment.patient_id != patient.id
    ):
        raise ValidationError(
            "Appointment does not belong to the selected patient"
        )

    if consultation is not None and (
        patient is not None
        and consultation.patient_id != patient.id
    ):
        raise ValidationError(
            "Consultation does not belong to the selected patient"
        )

    if (
        appointment is not None
        and consultation is not None
        and consultation.appointment_id is not None
        and consultation.appointment_id != appointment.id
    ):
        raise ValidationError(
            "Appointment and consultation do not match"
        )

    return patient, appointment, consultation


def _active_participant_count(
    conversation_id: int,
) -> int:
    return db.session.execute(
        db.select(
            func.count(ConversationParticipant.id)
        ).where(
            ConversationParticipant.conversation_id
            == conversation_id,
            ConversationParticipant.status.in_(
                (
                    ParticipantStatus.PENDING,
                    ParticipantStatus.ACCEPTED,
                )
            ),
        )
    ).scalar_one()


# ============================================================================
# CONVERSATION CREATION
# ============================================================================


@transactional
def create_conversation(
    clinic_id: int,
    created_by_id: int,
    conversation_type: ConversationType = ConversationType.DIRECT,
    title: str | None = None,
    description: str | None = None,
    patient_id: int | None = None,
    appointment_id: int | None = None,
    consultation_id: int | None = None,
    participant_user_ids: list[int] | None = None,
) -> Conversation:
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    _validate_positive_id(
        created_by_id,
        "Creator user ID",
    )

    ensure_clinic_active(clinic_id)

    conversation_type = _normalize_enum(
        conversation_type,
        ConversationType,
        "conversation type",
    )

    title = _normalize_optional_text(
        title,
        "Conversation title",
        200,
    )

    description = _normalize_optional_text(
        description,
        "Conversation description",
        1000,
    )

    creator = _get_user(
        created_by_id,
        clinic_id=clinic_id,
        active_only=True,
    )

    participant_user_ids = list(
        participant_user_ids or []
    )

    if len(participant_user_ids) > MAX_INITIAL_PARTICIPANTS:
        raise ValidationError(
            "Too many initial participants"
        )

    if len(participant_user_ids) != len(
        set(participant_user_ids)
    ):
        raise ValidationError(
            "Duplicate participant user IDs are not allowed"
        )

    for user_id in participant_user_ids:
        _validate_positive_id(
            user_id,
            "Participant user ID",
        )

    _validate_context_links(
        clinic_id,
        patient_id=patient_id,
        appointment_id=appointment_id,
        consultation_id=consultation_id,
    )

    if patient_id is not None:
        _validate_staff_patient_relationship(
            user_id=creator.id,
            clinic_id=clinic_id,
            patient_id=patient_id,
        )

    participant_ids = set(participant_user_ids)
    participant_ids.add(creator.id)

    if conversation_type == ConversationType.DIRECT:
        if len(participant_ids) != 2:
            raise ValidationError(
                "A direct conversation must contain exactly two users"
            )

        other_user_id = next(
            user_id
            for user_id in participant_ids
            if user_id != creator.id
        )

        existing = (
            db.session.execute(
                db.select(Conversation)
                .join(
                    ConversationParticipant,
                    ConversationParticipant.conversation_id
                    == Conversation.id,
                )
                .where(
                    Conversation.clinic_id == clinic_id,
                    Conversation.conversation_type
                    == ConversationType.DIRECT,
                    Conversation.status
                    != ConversationStatus.CLOSED,
                    ConversationParticipant.user_id.in_(
                        (creator.id, other_user_id)
                    ),
                    ConversationParticipant.status.in_(
                        (
                            ParticipantStatus.PENDING,
                            ParticipantStatus.ACCEPTED,
                        )
                    ),
                    db.select(func.count(ConversationParticipant.id))
                    .where(
                        ConversationParticipant.conversation_id
                        == Conversation.id,
                        ConversationParticipant.status.in_(
                            (
                                ParticipantStatus.PENDING,
                                ParticipantStatus.ACCEPTED,
                            )
                        ),
                    )
                    .correlate(Conversation)
                    .scalar_subquery() == 2,
                )
                .group_by(Conversation.id)
                .having(
                    func.count(
                        func.distinct(
                            ConversationParticipant.user_id
                        )
                    )
                    == 2
                )
                .order_by(
                    Conversation.id.asc()
                )
            )
            .scalars()
            .first()
        )

        if existing is not None:
            return existing

    conversation = Conversation(
        clinic_id=clinic_id,
        conversation_type=conversation_type,
        status=ConversationStatus.ACTIVE,
        title=title,
        description=description,
        created_by_id=creator.id,
        patient_id=patient_id,
        appointment_id=appointment_id,
        consultation_id=consultation_id,
    )

    db.session.add(conversation)
    db.session.flush()

    for user_id in sorted(participant_ids):
        _validate_conversation_participant(
            conversation,
            user_id,
        )

        participant = ConversationParticipant(
            clinic_id=clinic_id,
            conversation_id=conversation.id,
            user_id=user_id,
            role=(
                ParticipantRole.ADMIN
                if user_id == creator.id
                else ParticipantRole.MEMBER
            ),
            status=(
                ParticipantStatus.ACCEPTED
                if user_id == creator.id
                else ParticipantStatus.PENDING
            ),
            joined_at=(
                _utcnow()
                if user_id == creator.id
                else None
            ),
        )

        db.session.add(participant)

    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Conversation",
        entity_id=conversation.id,
        description=(
            f"Conversation {conversation.id} created"
        ),
        new_value={
            "conversation_type": conversation.conversation_type.value,
            "created_by_id": conversation.created_by_id,
            "participant_count": len(participant_ids),
            "patient_id": conversation.patient_id,
            "appointment_id": conversation.appointment_id,
            "consultation_id": conversation.consultation_id,
        },
    )

    return conversation


# ============================================================================
# GET / LIST CONVERSATIONS
# ============================================================================


def get_conversation(
    conversation_id: int,
    clinic_id: int | None = None,
) -> Conversation:
    return _get_conversation(
        conversation_id,
        clinic_id=clinic_id,
    )


def list_conversations(
    clinic_id: int,
    page: int = DEFAULT_PAGE,
    per_page: int = DEFAULT_PER_PAGE,
    status: ConversationStatus | None = None,
    conversation_type: ConversationType | None = None,
    patient_id: int | None = None,
    search: str | None = None,
):
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    page, per_page = _validate_pagination(
        page,
        per_page,
    )

    status = (
        _normalize_enum(
            status,
            ConversationStatus,
            "conversation status",
        )
        if status is not None
        else None
    )

    conversation_type = (
        _normalize_enum(
            conversation_type,
            ConversationType,
            "conversation type",
        )
        if conversation_type is not None
        else None
    )

    if patient_id is not None:
        _validate_positive_id(
            patient_id,
            "Patient ID",
        )

    search = _normalize_optional_text(
        search,
        "Conversation search",
        200,
    )

    query = db.select(Conversation).where(
        Conversation.clinic_id == clinic_id
    )

    count_query = db.select(
        func.count(Conversation.id)
    ).where(
        Conversation.clinic_id == clinic_id
    )

    if status is not None:
        query = query.where(
            Conversation.status == status
        )
        count_query = count_query.where(
            Conversation.status == status
        )

    if conversation_type is not None:
        query = query.where(
            Conversation.conversation_type
            == conversation_type
        )
        count_query = count_query.where(
            Conversation.conversation_type
            == conversation_type
        )

    if patient_id is not None:
        query = query.where(
            Conversation.patient_id == patient_id
        )
        count_query = count_query.where(
            Conversation.patient_id == patient_id
        )

    if search is not None:
        like = f"%{search}%"

        search_condition = db.or_(
            Conversation.title.ilike(like),
            Conversation.description.ilike(like),
        )

        query = query.where(search_condition)
        count_query = count_query.where(
            search_condition
        )

    total = db.session.execute(
        count_query
    ).scalar_one()

    offset = (page - 1) * per_page

    items = db.session.execute(
        query
        .order_by(
            Conversation.updated_at.desc(),
            Conversation.id.desc(),
        )
        .offset(offset)
        .limit(per_page)
    ).scalars().all()

    pages = (
        (total + per_page - 1) // per_page
        if total
        else 0
    )

    return {
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "has_next": page < pages,
        "has_previous": page > 1 and total > 0,
    }


# ============================================================================
# CONVERSATION UPDATE
# ============================================================================


@transactional
def update_conversation(
    conversation_id: int,
    clinic_id: int,
    **fields,
) -> Conversation:
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    ensure_clinic_active(clinic_id)

    conversation = _get_conversation(
        conversation_id,
        clinic_id=clinic_id,
        lock=True,
    )

    allowed_fields = {
        "conversation_type",
        "title",
        "description",
    }

    unknown = set(fields) - allowed_fields

    if unknown:
        raise ValidationError(
            "Unknown conversation field(s): "
            + ", ".join(sorted(unknown))
        )

    old_value = {}
    new_value = {}

    if "conversation_type" in fields:
        value = _normalize_enum(
            fields["conversation_type"],
            ConversationType,
            "conversation type",
        )

        if value != conversation.conversation_type:
            old_value["conversation_type"] = (
                conversation.conversation_type.value
            )
            new_value["conversation_type"] = value.value
            conversation.conversation_type = value

    if "title" in fields:
        value = _normalize_optional_text(
            fields["title"],
            "Conversation title",
            200,
        )

        if value != conversation.title:
            old_value["title"] = conversation.title
            new_value["title"] = value
            conversation.title = value

    if "description" in fields:
        value = _normalize_optional_text(
            fields["description"],
            "Conversation description",
            1000,
        )

        if value != conversation.description:
            old_value["description"] = conversation.description
            new_value["description"] = value
            conversation.description = value

    if new_value:
        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="Conversation",
            entity_id=conversation.id,
            description=(
                f"Conversation {conversation.id} updated"
            ),
            old_value=old_value,
            new_value=new_value,
        )

    return conversation


# ============================================================================
# CONVERSATION LIFECYCLE
# ============================================================================


@transactional
def update_conversation_status(
    conversation_id: int,
    clinic_id: int,
    new_status: ConversationStatus,
) -> Conversation:
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    ensure_clinic_active(clinic_id)

    new_status = _normalize_enum(
        new_status,
        ConversationStatus,
        "conversation status",
    )

    conversation = _get_conversation(
        conversation_id,
        clinic_id=clinic_id,
        lock=True,
    )

    current_status = conversation.status

    if current_status == new_status:
        return conversation

    allowed_transitions = {
        ConversationStatus.ACTIVE: {
            ConversationStatus.ARCHIVED,
            ConversationStatus.CLOSED,
        },
        ConversationStatus.ARCHIVED: {
            ConversationStatus.ACTIVE,
            ConversationStatus.CLOSED,
        },
        ConversationStatus.CLOSED: set(),
    }

    if new_status not in allowed_transitions[current_status]:
        raise ConflictError(
            f"Conversation {conversation.id} cannot transition "
            f"from '{current_status.value}' to "
            f"'{new_status.value}'"
        )

    now = _utcnow()

    conversation.status = new_status

    if new_status == ConversationStatus.ARCHIVED:
        conversation.archived_at = now
        conversation.closed_at = None

    elif new_status == ConversationStatus.CLOSED:
        conversation.closed_at = now

    elif new_status == ConversationStatus.ACTIVE:
        conversation.archived_at = None
        conversation.closed_at = None

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Conversation",
        entity_id=conversation.id,
        description=(
            f"Conversation status changed to "
            f"'{new_status.value}'"
        ),
        old_value={
            "status": current_status.value,
        },
        new_value={
            "status": new_status.value,
        },
    )

    return conversation


# ============================================================================
# PARTICIPANTS
# ============================================================================


@transactional
def add_participant(
    conversation_id: int,
    clinic_id: int,
    user_id: int,
    role: ParticipantRole = ParticipantRole.MEMBER,
) -> ConversationParticipant:
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    _validate_positive_id(
        user_id,
        "User ID",
    )

    ensure_clinic_active(clinic_id)

    conversation = _get_conversation(
        conversation_id,
        clinic_id=clinic_id,
        lock=True,
    )

    if conversation.status == ConversationStatus.CLOSED:
        raise ConflictError(
            "Cannot add participants to a closed conversation"
        )

    role = _normalize_enum(
        role,
        ParticipantRole,
        "participant role",
    )

    user = _validate_conversation_participant(
        conversation,
        user_id,
    )

    if conversation.patient_id is not None:
        _validate_staff_patient_relationship(
            user_id=user.id,
            clinic_id=clinic_id,
            patient_id=conversation.patient_id,
        )

    existing = db.session.execute(
        db.select(ConversationParticipant)
        .where(
            ConversationParticipant.conversation_id
            == conversation.id,
            ConversationParticipant.user_id
            == user.id,
        )
        .with_for_update()
    ).scalar_one_or_none()

    if existing is not None:
        if existing.status in (
            ParticipantStatus.ACCEPTED,
            ParticipantStatus.PENDING,
        ):
            raise ConflictError(
                f"User {user.id} is already a participant"
            )

        existing.status = ParticipantStatus.PENDING
        existing.left_at = None
        existing.removed_at = None
        existing.role = role

        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="ConversationParticipant",
            entity_id=existing.id,
            description=(
                f"User {user.id} re-added to "
                f"conversation {conversation.id}"
            ),
            new_value={
                "status": ParticipantStatus.PENDING.value,
                "role": role.value,
            },
        )

        return existing

    participant = ConversationParticipant(
        clinic_id=clinic_id,
        conversation_id=conversation.id,
        user_id=user.id,
        role=role,
        status=ParticipantStatus.PENDING,
    )

    db.session.add(participant)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="ConversationParticipant",
        entity_id=participant.id,
        description=(
            f"User {user.id} added to "
            f"conversation {conversation.id}"
        ),
        new_value={
            "conversation_id": conversation.id,
            "user_id": user.id,
            "role": role.value,
            "status": ParticipantStatus.PENDING.value,
        },
    )

    return participant


def list_participants(
    conversation_id: int,
    clinic_id: int,
    page: int = DEFAULT_PAGE,
    per_page: int = DEFAULT_PER_PAGE,
    status: ParticipantStatus | None = None,
):
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    page, per_page = _validate_pagination(
        page,
        per_page,
    )

    _get_conversation(
        conversation_id,
        clinic_id=clinic_id,
    )

    status = (
        _normalize_enum(
            status,
            ParticipantStatus,
            "participant status",
        )
        if status is not None
        else None
    )

    query = db.select(
        ConversationParticipant
    ).where(
        ConversationParticipant.conversation_id
        == conversation_id,
        ConversationParticipant.clinic_id
        == clinic_id,
    )

    count_query = db.select(
        func.count(ConversationParticipant.id)
    ).where(
        ConversationParticipant.conversation_id
        == conversation_id,
        ConversationParticipant.clinic_id
        == clinic_id,
    )

    if status is not None:
        query = query.where(
            ConversationParticipant.status == status
        )
        count_query = count_query.where(
            ConversationParticipant.status == status
        )

    total = db.session.execute(
        count_query
    ).scalar_one()

    offset = (page - 1) * per_page

    items = db.session.execute(
        query
        .order_by(
            ConversationParticipant.created_at.asc(),
            ConversationParticipant.id.asc(),
        )
        .offset(offset)
        .limit(per_page)
    ).scalars().all()

    pages = (
        (total + per_page - 1) // per_page
        if total
        else 0
    )

    return {
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "has_next": page < pages,
        "has_previous": page > 1 and total > 0,
    }


@transactional
def update_participant(
    participant_id: int,
    conversation_id: int,
    clinic_id: int,
    *,
    role: ParticipantRole | None = None,
    status: ParticipantStatus | None = None,
) -> ConversationParticipant:
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    ensure_clinic_active(clinic_id)

    participant = _get_participant(
        participant_id,
        clinic_id=clinic_id,
        conversation_id=conversation_id,
        lock=True,
    )

    old_value = {}
    new_value = {}

    if role is not None:
        role = _normalize_enum(
            role,
            ParticipantRole,
            "participant role",
        )

        if role != participant.role:
            old_value["role"] = participant.role.value
            new_value["role"] = role.value
            participant.role = role

    if status is not None:
        status = _normalize_enum(
            status,
            ParticipantStatus,
            "participant status",
        )

        if status != participant.status:
            old_value["status"] = participant.status.value
            new_value["status"] = status.value
            participant.status = status

            now = _utcnow()

            if status == ParticipantStatus.ACCEPTED:
                if participant.joined_at is None:
                    participant.joined_at = now

                participant.left_at = None
                participant.removed_at = None

            elif status == ParticipantStatus.LEFT:
                participant.left_at = now

            elif status == ParticipantStatus.REMOVED:
                participant.removed_at = now

    if new_value:
        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="ConversationParticipant",
            entity_id=participant.id,
            description=(
                f"Conversation participant "
                f"{participant.id} updated"
            ),
            old_value=old_value,
            new_value=new_value,
        )

    return participant


@transactional
def leave_conversation(
    conversation_id: int,
    clinic_id: int,
    user_id: int,
) -> ConversationParticipant:
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    _validate_positive_id(
        user_id,
        "User ID",
    )

    ensure_clinic_active(clinic_id)

    participant = db.session.execute(
        db.select(ConversationParticipant)
        .where(
            ConversationParticipant.conversation_id
            == conversation_id,
            ConversationParticipant.clinic_id
            == clinic_id,
            ConversationParticipant.user_id
            == user_id,
            ConversationParticipant.status.in_(
                (
                    ParticipantStatus.PENDING,
                    ParticipantStatus.ACCEPTED,
                )
            ),
        )
        .with_for_update()
    ).scalar_one_or_none()

    if participant is None:
        raise NotFoundError(
            "Active conversation participant not found"
        )

    if participant.role == ParticipantRole.ADMIN:
        active_count = _active_participant_count(
            conversation_id
        )

        if active_count > 1:
            admins = db.session.execute(
                db.select(
                    ConversationParticipant.id
                ).where(
                    ConversationParticipant.conversation_id
                    == conversation_id,
                    ConversationParticipant.role
                    == ParticipantRole.ADMIN,
                    ConversationParticipant.status.in_(
                        (
                            ParticipantStatus.PENDING,
                            ParticipantStatus.ACCEPTED,
                        )
                    ),
                )
                .limit(2)
            ).scalars().all()

            if len(admins) == 1:
                raise ConflictError(
                    "The last conversation admin cannot leave; "
                    "transfer admin role first"
                )

    participant_status_before_leave = participant.status

    participant.status = ParticipantStatus.LEFT
    participant.left_at = _utcnow()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="ConversationParticipant",
        entity_id=participant.id,
        description=(
            f"User {user_id} left "
            f"conversation {conversation_id}"
        ),
        old_value={
            "status": participant_status_before_leave.value,
        },
        new_value={
            "status": ParticipantStatus.LEFT.value,
        },
    )

    return participant


# ============================================================================
# READ STATE
# ============================================================================


@transactional
def update_participant_read_state(
    conversation_id: int,
    clinic_id: int,
    user_id: int,
    last_read_message_id: int,
) -> ConversationParticipant:
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    _validate_positive_id(
        user_id,
        "User ID",
    )

    _validate_positive_id(
        last_read_message_id,
        "Last read message ID",
    )

    ensure_clinic_active(clinic_id)

    participant = db.session.execute(
        db.select(ConversationParticipant)
        .where(
            ConversationParticipant.conversation_id
            == conversation_id,
            ConversationParticipant.clinic_id
            == clinic_id,
            ConversationParticipant.user_id
            == user_id,
            ConversationParticipant.status
            == ParticipantStatus.ACCEPTED,
        )
        .with_for_update()
    ).scalar_one_or_none()

    if participant is None:
        raise NotFoundError(
            "Accepted conversation participant not found"
        )
        
    participant.last_read_message_id = (
        last_read_message_id
    )

    return participant