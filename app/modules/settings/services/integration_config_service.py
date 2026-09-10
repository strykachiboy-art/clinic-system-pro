from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.security.encryption import (
    decrypt_credentials,
    encrypt_credentials,
)
from app.core.utils.decorators import transactional
from app.extensions import db
from app.modules.clinic.models.clinic_model import Clinic
from app.modules.settings.models.integration_config import (
    IntegrationConfig,
)
from app.modules.settings.schemas.integration_config import (
    IntegrationConfigCreateSchema,
    IntegrationConfigUpdateSchema,
)


DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_clinic(clinic_id: int) -> Clinic:
    clinic = db.session.get(Clinic, clinic_id)

    if clinic is None:
        raise NotFoundError("Clinic not found")

    return clinic


def _ensure_active_clinic(clinic: Clinic) -> None:
    if clinic.status.value != "active":
        raise ValidationError(
            "Clinic must be active to modify integration settings"
        )


def _get_integration_config(
    clinic_id: int,
    provider: str,
) -> IntegrationConfig:
    integration = (
        db.session.query(IntegrationConfig)
        .filter(
            IntegrationConfig.clinic_id == clinic_id,
            IntegrationConfig.provider == provider,
        )
        .first()
    )

    if integration is None:
        raise NotFoundError(
            "Integration configuration not found"
        )

    return integration


def _get_integration_config_by_id(
    clinic_id: int,
    integration_id: int,
) -> IntegrationConfig:
    integration = db.session.get(
        IntegrationConfig,
        integration_id,
    )

    if integration is None:
        raise NotFoundError(
            "Integration configuration not found"
        )

    if integration.clinic_id != clinic_id:
        raise NotFoundError(
            "Integration configuration not found"
        )

    return integration


def _ensure_credentials_are_supported(
    credentials: dict[str, Any],
) -> None:
    if not isinstance(credentials, dict):
        raise ValidationError(
            "Credentials must be an object"
        )

    if not credentials:
        raise ValidationError(
            "Credentials cannot be empty"
        )


def _ensure_configuration_is_supported(
    configuration: dict[str, Any],
) -> None:
    if not isinstance(configuration, dict):
        raise ValidationError(
            "Configuration must be an object"
        )


def _validate_pagination(
    page: int,
    per_page: int,
) -> None:
    if page < 1:
        raise ValidationError(
            "Page must be greater than 0"
        )

    if per_page < 1:
        raise ValidationError(
            "Per-page must be greater than 0"
        )

    if per_page > MAX_PER_PAGE:
        raise ValidationError(
            f"Per-page cannot exceed {MAX_PER_PAGE}"
        )


@transactional
def create_integration_config(
    clinic_id: int,
    payload: IntegrationConfigCreateSchema,
) -> IntegrationConfig:
    clinic = _get_clinic(clinic_id)
    _ensure_active_clinic(clinic)

    existing = (
        db.session.query(IntegrationConfig)
        .filter(
            IntegrationConfig.clinic_id == clinic_id,
            IntegrationConfig.provider == payload.provider,
        )
        .first()
    )

    if existing is not None:
        raise ConflictError(
            "Integration configuration already exists"
        )

    _ensure_credentials_are_supported(
        payload.credentials
    )

    _ensure_configuration_is_supported(
        payload.configuration
    )

    encrypted_credentials = encrypt_credentials(
        payload.credentials
    )

    integration = IntegrationConfig(
        clinic_id=clinic_id,
        provider=payload.provider,
        is_enabled=payload.is_enabled,
        configuration=payload.configuration,
        encrypted_credentials=encrypted_credentials,
        credentials_version=1,
        last_rotated_at=_utcnow(),
    )

    db.session.add(integration)

    try:
        db.session.flush()

    except IntegrityError as exc:
        raise ConflictError(
            "Integration configuration already exists"
        ) from exc

    return integration


def get_integration_config(
    clinic_id: int,
    provider: str,
) -> IntegrationConfig:
    _get_clinic(clinic_id)

    provider = provider.strip().lower()

    if not provider:
        raise ValidationError(
            "Provider is required"
        )

    return _get_integration_config(
        clinic_id,
        provider,
    )


def get_integration_config_by_id(
    clinic_id: int,
    integration_id: int,
) -> IntegrationConfig:
    _get_clinic(clinic_id)

    if integration_id <= 0:
        raise ValidationError(
            "Integration configuration ID must be greater than 0"
        )

    return _get_integration_config_by_id(
        clinic_id,
        integration_id,
    )


def list_integration_configs(
    clinic_id: int,
    *,
    include_disabled: bool = False,
    provider: str | None = None,
    page: int = DEFAULT_PAGE,
    per_page: int = DEFAULT_PER_PAGE,
) -> tuple[list[IntegrationConfig], int]:
    _get_clinic(clinic_id)

    _validate_pagination(
        page,
        per_page,
    )

    query = (
        db.session.query(IntegrationConfig)
        .filter(
            IntegrationConfig.clinic_id == clinic_id
        )
    )

    if not include_disabled:
        query = query.filter(
            IntegrationConfig.is_enabled.is_(True)
        )

    if provider is not None:
        provider = provider.strip().lower()

        if not provider:
            raise ValidationError(
                "Provider cannot be empty"
            )

        query = query.filter(
            IntegrationConfig.provider == provider
        )

    total = query.count()

    offset = (page - 1) * per_page

    items = (
        query
        .order_by(
            IntegrationConfig.provider.asc(),
            IntegrationConfig.id.asc(),
        )
        .offset(offset)
        .limit(per_page)
        .all()
    )

    return items, total


@transactional
def update_integration_config(
    clinic_id: int,
    provider: str,
    payload: IntegrationConfigUpdateSchema,
) -> IntegrationConfig:
    clinic = _get_clinic(clinic_id)
    _ensure_active_clinic(clinic)

    provider = provider.strip().lower()

    if not provider:
        raise ValidationError(
            "Provider is required"
        )

    integration = _get_integration_config(
        clinic_id,
        provider,
    )

    changes = payload.model_dump(
        exclude_unset=True,
        exclude_none=True,
    )

    if not changes:
        raise ValidationError(
            "At least one integration field must be provided"
        )

    if "configuration" in changes:
        _ensure_configuration_is_supported(
            changes["configuration"]
        )

        integration.configuration = (
            changes["configuration"]
        )

    if "is_enabled" in changes:
        integration.is_enabled = (
            changes["is_enabled"]
        )

    if "credentials" in changes:
        credentials = changes["credentials"]

        _ensure_credentials_are_supported(
            credentials
        )

        integration.encrypted_credentials = (
            encrypt_credentials(credentials)
        )

        integration.credentials_version += 1
        integration.last_rotated_at = _utcnow()

    try:
        db.session.flush()

    except IntegrityError as exc:
        raise ConflictError(
            "Unable to update integration configuration"
        ) from exc

    return integration


@transactional
def rotate_integration_credentials(
    clinic_id: int,
    provider: str,
    credentials: dict[str, Any],
) -> IntegrationConfig:
    clinic = _get_clinic(clinic_id)
    _ensure_active_clinic(clinic)

    provider = provider.strip().lower()

    if not provider:
        raise ValidationError(
            "Provider is required"
        )

    integration = _get_integration_config(
        clinic_id,
        provider,
    )

    _ensure_credentials_are_supported(
        credentials
    )

    integration.encrypted_credentials = (
        encrypt_credentials(credentials)
    )

    integration.credentials_version += 1
    integration.last_rotated_at = _utcnow()

    return integration


@transactional
def enable_integration_config(
    clinic_id: int,
    provider: str,
) -> IntegrationConfig:
    clinic = _get_clinic(clinic_id)
    _ensure_active_clinic(clinic)

    provider = provider.strip().lower()

    if not provider:
        raise ValidationError(
            "Provider is required"
        )

    integration = _get_integration_config(
        clinic_id,
        provider,
    )

    if integration.is_enabled:
        return integration

    integration.is_enabled = True

    return integration


@transactional
def disable_integration_config(
    clinic_id: int,
    provider: str,
) -> IntegrationConfig:
    clinic = _get_clinic(clinic_id)
    _ensure_active_clinic(clinic)

    provider = provider.strip().lower()

    if not provider:
        raise ValidationError(
            "Provider is required"
        )

    integration = _get_integration_config(
        clinic_id,
        provider,
    )

    if not integration.is_enabled:
        return integration

    integration.is_enabled = False

    return integration


@transactional
def delete_integration_config(
    clinic_id: int,
    provider: str,
) -> None:
    clinic = _get_clinic(clinic_id)
    _ensure_active_clinic(clinic)

    provider = provider.strip().lower()

    if not provider:
        raise ValidationError(
            "Provider is required"
        )

    integration = _get_integration_config(
        clinic_id,
        provider,
    )

    db.session.delete(integration)


def get_integration_credentials(
    clinic_id: int,
    provider: str,
) -> dict[str, Any]:
    _get_clinic(clinic_id)

    provider = provider.strip().lower()

    if not provider:
        raise ValidationError(
            "Provider is required"
        )

    integration = _get_integration_config(
        clinic_id,
        provider,
    )

    if not integration.encrypted_credentials:
        raise ValidationError(
            "Integration credentials are not configured"
        )

    return decrypt_credentials(
        integration.encrypted_credentials
    )