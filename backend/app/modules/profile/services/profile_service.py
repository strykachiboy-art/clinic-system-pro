from __future__ import annotations

from typing import Any

from app.core.audit.services.audit_service import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.storage.storage_service import profile_image_url
from app.core.utils.decorators import transactional
from app.extensions import db

from app.core.auth.user.models.user_model import User
from app.modules.clinic.models.clinic_model import Clinic
from app.modules.profile.schemas.profile_schema import (
    ProfileImageRemoveResponseSchema,
    ProfileImageUploadResponseSchema,
    ProfileResponseSchema,
    PublicProfileResponseSchema,
    PublicProfileUserSchema,
)
from app.modules.staff.models.staff_model import Staff


_PROFILE_UPDATE_FIELDS = {
    "first_name",
    "last_name",
    "phone",
    "email",
    "specialty",
}

_MAX_PROFILE_IMAGE_STORAGE_KEY_LENGTH = 500


# ============================================================================
# VALIDATION / LOOKUP HELPERS
# ============================================================================


def _validate_user_id(user_id: int) -> None:
    if isinstance(user_id, bool) or not isinstance(user_id, int):
        raise ValidationError("User ID must be an integer")

    if user_id <= 0:
        raise ValidationError(
            "User ID must be greater than 0"
        )


def _get_user(user_id: int) -> User:
    _validate_user_id(user_id)

    user = db.session.get(
        User,
        user_id,
    )

    if user is None:
        raise NotFoundError(
            f"User {user_id} not found"
        )

    if not user.is_active:
        raise ValidationError(
            "Authenticated user is inactive"
        )

    return user


def _get_public_user(user_id: int) -> User:
    _validate_user_id(user_id)

    user = db.session.get(
        User,
        user_id,
    )

    if user is None or not user.is_active:
        raise NotFoundError(
            f"User {user_id} not found"
        )

    return user


def _get_staff_for_user(
    user: User,
) -> Staff | None:
    staff = getattr(
        user,
        "staff",
        None,
    )

    if staff is None:
        return None

    if staff.user_id != user.id:
        raise ConflictError(
            f"Staff record {staff.id} is not correctly linked to user {user.id}"
        )

    return staff


def _get_clinic_for_user(
    user: User,
    staff: Staff | None,
) -> Clinic | None:
    clinic_id = user.clinic_id

    if staff is not None:
        if clinic_id is None:
            clinic_id = staff.clinic_id
        elif staff.clinic_id != clinic_id:
            raise ConflictError(
                "User and Staff records belong to different clinics"
            )

    if clinic_id is None:
        return None

    if clinic_id <= 0:
        raise ValidationError(
            "Invalid clinic ID"
        )

    clinic = db.session.get(
        Clinic,
        clinic_id,
    )

    if clinic is None:
        raise NotFoundError(
            f"Clinic {clinic_id} not found"
        )

    return clinic


def _validate_profile_image_storage_key(
    storage_key: str,
) -> str:
    if not isinstance(
        storage_key,
        str,
    ):
        raise ValidationError(
            "Profile image storage key must be a string"
        )

    storage_key = storage_key.strip()

    if not storage_key:
        raise ValidationError(
            "Profile image storage key cannot be blank"
        )

    if len(storage_key) > _MAX_PROFILE_IMAGE_STORAGE_KEY_LENGTH:
        raise ValidationError(
            "Profile image storage key is too long"
        )

    return storage_key


# ============================================================================
# GENERIC HELPERS
# ============================================================================


def _enum_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value

    return value


def _record_changes(
    *,
    obj: Any,
    entity_type: str,
    entity_id: int,
    fields: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    old_value: dict[str, Any] = {}
    new_value: dict[str, Any] = {}

    for field, new_val in fields.items():
        current_val = getattr(
            obj,
            field,
        )

        if current_val == new_val:
            continue

        old_value[field] = _enum_value(
            current_val
        )
        new_value[field] = _enum_value(
            new_val
        )

        setattr(
            obj,
            field,
            new_val,
        )

    return old_value, new_value


# ============================================================================
# MY PROFILE
# ============================================================================


def get_profile(
    user_id: int,
) -> ProfileResponseSchema:
    user = _get_user(
        user_id
    )

    staff = _get_staff_for_user(
        user
    )

    clinic = _get_clinic_for_user(
        user,
        staff,
    )

    return ProfileResponseSchema(
        user=user,
        staff=staff,
        clinic=clinic,
    )


# ============================================================================
# PUBLIC PROFILE
# ============================================================================


def get_public_profile(
    user_id: int,
) -> PublicProfileResponseSchema:
    user = _get_public_user(
        user_id
    )

    staff = _get_staff_for_user(
        user
    )

    public_user = PublicProfileUserSchema(
        id=user.id,
        profile_image_url=profile_image_url(
            user.profile_image_storage_key
        ),
    )

    return PublicProfileResponseSchema(
        user=public_user,
        staff=staff,
    )


# ============================================================================
# PROFILE UPDATE
# ============================================================================


@transactional
def update_profile(
    user_id: int,
    **fields,
) -> ProfileResponseSchema:
    user = _get_user(
        user_id
    )

    if not fields:
        raise ValidationError(
            "At least one profile field is required"
        )

    unknown = set(fields) - _PROFILE_UPDATE_FIELDS

    if unknown:
        raise ValidationError(
            "Unsupported profile field(s): "
            + ", ".join(sorted(unknown))
        )

    staff = _get_staff_for_user(
        user
    )

    user_fields: dict[str, Any] = {}
    staff_fields: dict[str, Any] = {}

    if "email" in fields:
        user_fields["email"] = fields["email"]

    for field in (
        "first_name",
        "last_name",
        "phone",
        "specialty",
    ):
        if field in fields:
            staff_fields[field] = fields[field]

    if staff_fields and staff is None:
        raise ValidationError(
            "This user is not linked to a staff record"
        )

    if "email" in user_fields:
        email = user_fields["email"]

        if email is None:
            raise ValidationError(
                "Email cannot be null"
            )

        existing_user = (
            db.session.execute(
                db.select(User)
                .where(
                    User.email == email,
                    User.id != user.id,
                )
                .limit(1)
            )
            .scalar_one_or_none()
        )

        if existing_user is not None:
            raise ConflictError(
                f"Email '{email}' is already in use"
            )

    user_old, user_new = _record_changes(
        obj=user,
        entity_type="User",
        entity_id=user.id,
        fields=user_fields,
    )

    if user_new:
        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="User",
            entity_id=user.id,
            description="User profile updated",
            old_value=user_old,
            new_value=user_new,
        )

    if staff is not None:
        staff_old, staff_new = _record_changes(
            obj=staff,
            entity_type="Staff",
            entity_id=staff.id,
            fields=staff_fields,
        )

        if staff_new:
            create_audit_log(
                action=AuditAction.UPDATE,
                entity_type="Staff",
                entity_id=staff.id,
                description=(
                    f"Staff profile for "
                    f"'{staff.first_name} {staff.last_name}' updated"
                ),
                old_value=staff_old,
                new_value=staff_new,
            )

    clinic = _get_clinic_for_user(
        user,
        staff,
    )

    return ProfileResponseSchema(
        user=user,
        staff=staff,
        clinic=clinic,
    )


# ============================================================================
# PROFILE IMAGE
# ============================================================================


@transactional
def upload_profile_image(
    actor_user_id: int,
    storage_key: str,
) -> ProfileImageUploadResponseSchema:
    user = _get_user(
        actor_user_id
    )

    storage_key = _validate_profile_image_storage_key(
        storage_key
    )

    old_storage_key = user.profile_image_storage_key

    if old_storage_key == storage_key:
        raise ConflictError(
            "This profile image is already assigned"
        )

    user.profile_image_storage_key = storage_key

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="User",
        entity_id=user.id,
        description="User profile image updated",
        old_value={
            "profile_image_storage_key": old_storage_key,
        },
        new_value={
            "profile_image_storage_key": storage_key,
        },
    )

    return ProfileImageUploadResponseSchema(
        profile_image_storage_key=storage_key,
    )


@transactional
def remove_profile_image(
    actor_user_id: int,
) -> ProfileImageRemoveResponseSchema:
    user = _get_user(
        actor_user_id
    )

    old_storage_key = user.profile_image_storage_key

    if old_storage_key is None:
        raise NotFoundError(
            "User does not have a profile image"
        )

    user.profile_image_storage_key = None

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="User",
        entity_id=user.id,
        description="User profile image removed",
        old_value={
            "profile_image_storage_key": old_storage_key,
        },
        new_value={
            "profile_image_storage_key": None,
        },
    )

    return ProfileImageRemoveResponseSchema(
        profile_image_storage_key=None,
    )