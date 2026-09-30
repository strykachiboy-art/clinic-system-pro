from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.core.enums.role_enums import Role
from app.core.exceptions import NotFoundError, ValidationError

from app.modules.dashboard.schemas.dashboard_schema import (
    DashboardQuerySchema,
)
from app.modules.dashboard.services import dashboard_service


# ============================================================================
# ACTOR VALIDATION
# ============================================================================


@pytest.mark.parametrize(
    "actor_id",
    [
        0,
        -1,
        True,
        False,
        "1",
        1.0,
        None,
    ],
)
def test_get_dashboard_rejects_invalid_actor_id(
    actor_id,
):
    with pytest.raises(
        ValidationError,
        match="Actor ID must be a positive integer",
    ):
        dashboard_service.get_dashboard(
            actor_id=actor_id,
        )


def test_get_dashboard_rejects_missing_user(
    app,
):
    with pytest.raises(
        NotFoundError,
        match="User 999999 not found",
    ):
        dashboard_service.get_dashboard(
            actor_id=999999,
        )


def test_get_dashboard_rejects_inactive_user(
    clinic,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
        is_active=False,
    )

    with pytest.raises(
        ValidationError,
        match="User account is inactive",
    ):
        dashboard_service.get_dashboard(
            actor_id=actor.id,
        )


def test_get_dashboard_resolves_active_user(
    clinic,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    resolved = dashboard_service._get_active_user(
        actor.id,
    )

    assert resolved.id == actor.id
    assert resolved.is_active is True
    assert resolved.role is Role.DOCTOR


# ============================================================================
# ROLE DISPATCH
# ============================================================================


def test_get_dashboard_dispatches_to_super_admin_service(
    clinic,
    make_user,
    monkeypatch,
):
    actor = make_user(
        None,
        role=Role.SUPER_ADMIN,
    )

    expected = object()

    mock_service = Mock(
        return_value=expected,
    )

    monkeypatch.setattr(
        dashboard_service,
        "get_super_admin_dashboard",
        mock_service,
    )

    result = dashboard_service.get_dashboard(
        actor_id=actor.id,
    )

    assert result is expected

    mock_service.assert_called_once_with(
        actor=actor,
        query=None,
    )


def test_get_dashboard_dispatches_to_management_service(
    clinic,
    make_user,
    monkeypatch,
):
    actor = make_user(
        clinic,
        role=Role.ADMIN,
    )

    expected = object()

    mock_service = Mock(
        return_value=expected,
    )

    monkeypatch.setattr(
        dashboard_service,
        "get_management_dashboard",
        mock_service,
    )

    result = dashboard_service.get_dashboard(
        actor_id=actor.id,
    )

    assert result is expected

    mock_service.assert_called_once_with(
        actor=actor,
        query=None,
    )


@pytest.mark.parametrize(
    "role",
    [
        Role.DOCTOR,
        Role.NURSE,
        Role.PHARMACIST,
        Role.LAB_TECHNICIAN,
        Role.PARAMEDIC,
        Role.EMT,
    ],
)
def test_get_dashboard_dispatches_all_clinical_roles(
    clinic,
    make_user,
    monkeypatch,
    role,
):
    actor = make_user(
        clinic,
        role=role,
    )

    expected = object()

    mock_service = Mock(
        return_value=expected,
    )

    monkeypatch.setattr(
        dashboard_service,
        "get_clinical_dashboard",
        mock_service,
    )

    result = dashboard_service.get_dashboard(
        actor_id=actor.id,
    )

    assert result is expected

    mock_service.assert_called_once_with(
        actor=actor,
        query=None,
    )


@pytest.mark.parametrize(
    "role",
    [
        Role.RECEPTIONIST,
        Role.DRIVER,
        Role.AMBULANCE_DISPATCHER,
        Role.AMBULANCE_COORDINATOR,
        Role.OTHER,
    ],
)
def test_get_dashboard_dispatches_all_operations_roles(
    clinic,
    make_user,
    monkeypatch,
    role,
):
    actor = make_user(
        clinic,
        role=role,
    )

    expected = object()

    mock_service = Mock(
        return_value=expected,
    )

    monkeypatch.setattr(
        dashboard_service,
        "get_operations_dashboard",
        mock_service,
    )

    result = dashboard_service.get_dashboard(
        actor_id=actor.id,
    )

    assert result is expected

    mock_service.assert_called_once_with(
        actor=actor,
        query=None,
    )


def test_get_dashboard_dispatches_to_finance_service(
    clinic,
    make_user,
    monkeypatch,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    expected = object()

    mock_service = Mock(
        return_value=expected,
    )

    monkeypatch.setattr(
        dashboard_service,
        "get_finance_dashboard",
        mock_service,
    )

    result = dashboard_service.get_dashboard(
        actor_id=actor.id,
    )

    assert result is expected

    mock_service.assert_called_once_with(
        actor=actor,
        query=None,
    )


def test_get_dashboard_dispatches_to_patient_service(
    clinic,
    make_user,
    monkeypatch,
):
    actor = make_user(
        clinic,
        role=Role.PATIENT,
    )

    expected = object()

    mock_service = Mock(
        return_value=expected,
    )

    monkeypatch.setattr(
        dashboard_service,
        "get_patient_dashboard",
        mock_service,
    )

    result = dashboard_service.get_dashboard(
        actor_id=actor.id,
    )

    assert result is expected

    mock_service.assert_called_once_with(
        actor=actor,
        query=None,
    )


# ============================================================================
# QUERY PROPAGATION
# ============================================================================


def test_get_dashboard_forwards_query_to_role_service(
    clinic,
    make_user,
    monkeypatch,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    query = DashboardQuerySchema(
        date_from="2026-09-01",
        date_to="2026-09-15",
    )

    expected = object()

    mock_service = Mock(
        return_value=expected,
    )

    monkeypatch.setattr(
        dashboard_service,
        "get_clinical_dashboard",
        mock_service,
    )

    result = dashboard_service.get_dashboard(
        actor_id=actor.id,
        query=query,
    )

    assert result is expected

    mock_service.assert_called_once_with(
        actor=actor,
        query=query,
    )


@pytest.mark.parametrize(
    "role,service_name",
    [
        (
            Role.SUPER_ADMIN,
            "get_super_admin_dashboard",
        ),
        (
            Role.ADMIN,
            "get_management_dashboard",
        ),
        (
            Role.DOCTOR,
            "get_clinical_dashboard",
        ),
        (
            Role.ACCOUNTANT,
            "get_finance_dashboard",
        ),
        (
            Role.PATIENT,
            "get_patient_dashboard",
        ),
    ],
)
def test_get_dashboard_passes_same_query_object(
    clinic,
    make_user,
    monkeypatch,
    role,
    service_name,
):
    actor = make_user(
        None if role is Role.SUPER_ADMIN else clinic,
        role=role,
    )

    query = DashboardQuerySchema(
        date_from="2026-09-10",
        date_to="2026-09-12",
    )

    expected = object()

    mock_service = Mock(
        return_value=expected,
    )

    monkeypatch.setattr(
        dashboard_service,
        service_name,
        mock_service,
    )

    result = dashboard_service.get_dashboard(
        actor_id=actor.id,
        query=query,
    )

    assert result is expected

    mock_service.assert_called_once_with(
        actor=actor,
        query=query,
    )


# ============================================================================
# UNSUPPORTED ROLE
# ============================================================================


def test_get_dashboard_rejects_role_without_dashboard_configuration(
    clinic,
    make_user,
    monkeypatch,
):
    actor = make_user(
        clinic,
        role=Role.OTHER,
    )

    monkeypatch.setattr(
        dashboard_service,
        "OPERATIONS_ROLES",
        {
            Role.RECEPTIONIST,
            Role.DRIVER,
            Role.AMBULANCE_DISPATCHER,
            Role.AMBULANCE_COORDINATOR,
        },
    )

    with pytest.raises(
        ValidationError,
        match="No dashboard is configured for role",
    ):
        dashboard_service.get_dashboard(
            actor_id=actor.id,
        )