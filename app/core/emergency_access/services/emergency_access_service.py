from __future__ import annotations

from typing import Any

from app.core.emergency_access.models.emergency_access_model import (
    EmergencyAccessGrant,
)


def request_emergency_access(
    *,
    actor_id: int,
    patient_id: int,
    reason: str,
    purpose: str,
    scope: list[str],
) -> EmergencyAccessGrant:
    raise NotImplementedError


def grant_emergency_access(
    *,
    emergency_access_id: int,
    reviewer_id: int,
    duration_minutes: int,
    review_notes: str | None = None,
) -> EmergencyAccessGrant:
    raise NotImplementedError


def deny_emergency_access(
    *,
    emergency_access_id: int,
    reviewer_id: int,
    review_notes: str | None = None,
) -> EmergencyAccessGrant:
    raise NotImplementedError


def revoke_emergency_access(
    *,
    emergency_access_id: int,
    actor_id: int,
    reason: str,
) -> EmergencyAccessGrant:
    raise NotImplementedError


def expire_emergency_access(
    *,
    emergency_access_id: int,
) -> EmergencyAccessGrant:
    raise NotImplementedError


def assert_emergency_access(
    *,
    actor_id: int,
    patient_id: int,
    resource_type: str,
    resource_id: int,
    action: str,
) -> bool:
    raise NotImplementedError