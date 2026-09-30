from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.enums.asset_enums import (
    AssetCategory,
    AssetCondition,
    AssetHistoryEventType,
    AssetOwnership,
    AssetStatus,
    MaintenanceStatus,
)
from app.core.enums.role_enums import Role
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.asset_control.schemas.asset_assignment_schema import (
    AssetAssignmentCreateSchema,
    AssetAssignmentListQuerySchema,
    AssetAssignmentReturnSchema,
)
from app.modules.asset_control.schemas.asset_history_schema import (
    AssetHistoryListQuerySchema,
)
from app.modules.asset_control.schemas.asset_maintenance_schema import (
    AssetMaintenanceListQuerySchema,
)
from app.modules.asset_control.schemas.asset_schema import (
    AssetCreateSchema,
    AssetListQuerySchema,
    AssetRetireSchema,
    AssetUpdateSchema,
)


@pytest.fixture()
def asset_routes():
    from app.modules.asset_control.routes import asset_route

    return asset_route


def _empty_pagination(
    *,
    page: int = 1,
    per_page: int = 50,
):
    return {
        "items": [],
        "page": page,
        "per_page": per_page,
        "total": 0,
        "pages": 0,
        "has_next": False,
        "has_prev": False,
    }


def _asset_pagination(asset):
    return {
        "items": [asset],
        "page": 1,
        "per_page": 50,
        "total": 1,
        "pages": 1,
        "has_next": False,
        "has_prev": False,
    }


def _patch_assignment_serializer(
    asset_routes,
    monkeypatch,
    value=None,
):
    monkeypatch.setattr(
        asset_routes,
        "_serialize_assignment",
        Mock(
            return_value=(
                value
                if value is not None
                else {"id": 1}
            )
        ),
    )


def _patch_history_serializer(
    asset_routes,
    monkeypatch,
    value=None,
):
    monkeypatch.setattr(
        asset_routes,
        "_serialize_history",
        Mock(
            return_value=(
                value
                if value is not None
                else {"id": 1}
            )
        ),
    )


def _patch_maintenance_serializer(
    asset_routes,
    monkeypatch,
    value=None,
):
    monkeypatch.setattr(
        asset_routes,
        "_serialize_maintenance",
        Mock(
            return_value=(
                value
                if value is not None
                else {"id": 1}
            )
        ),
    )


def _patch_schema_validator(
    monkeypatch,
    module,
    schema_name,
    value=None,
):
    if value is None:
        value = object()

    validator = Mock(
        return_value=value
    )

    fake_schema = SimpleNamespace(
        model_validate=validator
    )

    monkeypatch.setattr(
        module,
        schema_name,
        fake_schema,
    )

    return validator, value


# =============================================================================
# AUTHORIZATION
# =============================================================================


@pytest.mark.parametrize(
    "method,url,body",
    [
        (
            "post",
            "/api/v1/assets",
            {
                "asset_tag": "AST-AUTH-001",
                "name": "Auth Asset",
                "category": "computer",
            },
        ),
        (
            "get",
            "/api/v1/assets",
            None,
        ),
        (
            "get",
            "/api/v1/assets/1",
            None,
        ),
        (
            "patch",
            "/api/v1/assets/1",
            {"name": "Updated"},
        ),
        (
            "post",
            "/api/v1/assets/1/retire",
            {},
        ),
        (
            "post",
            "/api/v1/assets/1/dispose",
            {"disposal_reason": "Disposed"},
        ),
        (
            "post",
            "/api/v1/assets/1/assign",
            {},
        ),
        (
            "post",
            "/api/v1/assets/1/return",
            {},
        ),
        (
            "get",
            "/api/v1/assets/1/assignments",
            None,
        ),
        (
            "get",
            "/api/v1/assets/assignments/1",
            None,
        ),
        (
            "get",
            "/api/v1/assets/1/history",
            None,
        ),
        (
            "get",
            "/api/v1/assets/history/1",
            None,
        ),
        (
            "post",
            "/api/v1/assets/1/maintenance",
            {},
        ),
        (
            "get",
            "/api/v1/assets/1/maintenance",
            None,
        ),
        (
            "get",
            "/api/v1/assets/maintenance/1",
            None,
        ),
        (
            "post",
            "/api/v1/assets/maintenance/1/start",
            {},
        ),
        (
            "post",
            "/api/v1/assets/maintenance/1/complete",
            {},
        ),
        (
            "post",
            "/api/v1/assets/maintenance/1/cancel",
            {},
        ),
    ],
)
def test_all_asset_routes_require_authentication(
    client,
    method,
    url,
    body,
):
    response = getattr(client, method)(
        url,
        json=body,
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "method,url,body",
    [
        (
            "post",
            "/api/v1/assets",
            {
                "asset_tag": "AST-FORBIDDEN",
                "name": "Forbidden",
                "category": "computer",
            },
        ),
        (
            "patch",
            "/api/v1/assets/1",
            {"name": "Forbidden"},
        ),
        (
            "post",
            "/api/v1/assets/1/retire",
            {},
        ),
        (
            "post",
            "/api/v1/assets/1/dispose",
            {"disposal_reason": "Forbidden"},
        ),
        (
            "post",
            "/api/v1/assets/1/assign",
            {},
        ),
        (
            "post",
            "/api/v1/assets/1/return",
            {},
        ),
        (
            "post",
            "/api/v1/assets/1/maintenance",
            {},
        ),
        (
            "post",
            "/api/v1/assets/maintenance/1/start",
            {},
        ),
        (
            "post",
            "/api/v1/assets/maintenance/1/complete",
            {},
        ),
        (
            "post",
            "/api/v1/assets/maintenance/1/cancel",
            {},
        ),
    ],
)
def test_management_routes_forbidden_for_doctor(
    client,
    clinic,
    make_user,
    auth_headers_for,
    method,
    url,
    body,
):
    doctor = make_user(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    response = getattr(client, method)(
        url,
        headers=auth_headers_for(
            doctor,
            role=Role.DOCTOR,
        ),
        json=body,
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "url",
    [
        "/api/v1/assets",
        "/api/v1/assets/1",
        "/api/v1/assets/1/assignments",
        "/api/v1/assets/assignments/1",
        "/api/v1/assets/1/history",
        "/api/v1/assets/history/1",
        "/api/v1/assets/1/maintenance",
        "/api/v1/assets/maintenance/1",
    ],
)
def test_view_routes_forbidden_for_doctor(
    client,
    clinic,
    make_user,
    auth_headers_for,
    url,
):
    doctor = make_user(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        url,
        headers=auth_headers_for(
            doctor,
            role=Role.DOCTOR,
        ),
    )

    assert response.status_code == 403


def test_create_asset_allows_admin(
    client,
    user,
    asset,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    service = Mock(return_value=asset)

    monkeypatch.setattr(
        asset_routes,
        "create_asset",
        service,
    )

    response = client.post(
        "/api/v1/assets",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "asset_tag": "AST-ROUTE-001",
            "name": "Route Asset",
            "category": AssetCategory.COMPUTER.value,
        },
    )

    assert response.status_code == 201


def test_create_asset_allows_accountant(
    client,
    clinic,
    asset,
    make_user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    accountant = make_user(
        clinic=clinic,
        role=Role.ACCOUNTANT,
    )

    monkeypatch.setattr(
        asset_routes,
        "create_asset",
        Mock(return_value=asset),
    )

    response = client.post(
        "/api/v1/assets",
        headers=auth_headers_for(
            accountant,
            role=Role.ACCOUNTANT,
        ),
        json={
            "asset_tag": "AST-ACCOUNTANT-001",
            "name": "Accountant Asset",
            "category": AssetCategory.COMPUTER.value,
        },
    )

    assert response.status_code == 201


def test_list_assets_allows_admin(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "list_assets",
        Mock(
            return_value=_empty_pagination()
        ),
    )

    response = client.get(
        "/api/v1/assets",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 200


def test_list_assets_allows_accountant(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    accountant = make_user(
        clinic=clinic,
        role=Role.ACCOUNTANT,
    )

    monkeypatch.setattr(
        asset_routes,
        "list_assets",
        Mock(
            return_value=_empty_pagination()
        ),
    )

    response = client.get(
        "/api/v1/assets",
        headers=auth_headers_for(
            accountant,
            role=Role.ACCOUNTANT,
        ),
    )

    assert response.status_code == 200


# =============================================================================
# CURRENT USER / CLINIC CONTEXT
# =============================================================================


def test_current_user_rejects_invalid_identity(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "get_jwt_identity",
        lambda: "invalid",
    )

    response = client.get(
        "/api/v1/assets",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Invalid authentication identity"
    )


def test_current_user_rejects_missing_user(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "get_jwt_identity",
        lambda: 999999,
    )

    response = client.get(
        "/api/v1/assets",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 404

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Authenticated user not found"
    )


def test_current_user_rejects_inactive_user(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "_current_user",
        Mock(
            side_effect=ValidationError(
                f"Authenticated user {user.id} is inactive"
            )
        ),
    )

    response = client.get(
        "/api/v1/assets",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "inactive" in body["error"].lower()


def test_current_clinic_rejects_invalid_clinic_context(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "_current_clinic_id",
        Mock(
            side_effect=ValidationError(
                "Authenticated user is not associated "
                "with a valid clinic"
            )
        ),
    )

    response = client.get(
        "/api/v1/assets",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Authenticated user is not associated "
        "with a valid clinic"
    )


# =============================================================================
# CREATE
# =============================================================================


def test_create_asset_forwards_authenticated_context(
    client,
    user,
    asset,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    service = Mock(
        return_value=asset,
    )

    monkeypatch.setattr(
        asset_routes,
        "create_asset",
        service,
    )

    response = client.post(
        "/api/v1/assets",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "asset_tag": "AST-CREATE-001",
            "name": "Route Created Asset",
            "category": AssetCategory.COMPUTER.value,
            "condition": AssetCondition.EXCELLENT.value,
            "ownership": AssetOwnership.LEASED.value,
            "purchase_cost": "25000.50",
        },
    )

    assert response.status_code == 201

    kwargs = service.call_args.kwargs

    assert kwargs["clinic_id"] == user.clinic_id
    assert kwargs["actor_user_id"] == user.id

    assert isinstance(
        kwargs["data"],
        AssetCreateSchema,
    )

    assert kwargs["data"].asset_tag == (
        "AST-CREATE-001"
    )

    assert kwargs["data"].name == (
        "Route Created Asset"
    )

    assert kwargs["data"].category == (
        AssetCategory.COMPUTER
    )

    assert kwargs["data"].condition == (
        AssetCondition.EXCELLENT
    )

    assert kwargs["data"].ownership == (
        AssetOwnership.LEASED
    )

    assert kwargs["data"].purchase_cost == (
        Decimal("25000.50")
    )


def test_create_asset_serializes_response(
    client,
    user,
    asset,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "create_asset",
        Mock(return_value=asset),
    )

    response = client.post(
        "/api/v1/assets",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "asset_tag": "AST-SERIALIZE",
            "name": "Serialize Asset",
            "category": AssetCategory.COMPUTER.value,
        },
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert "asset" in body
    assert body["asset"]["id"] == asset.id
    assert body["asset"]["clinic_id"] == (
        asset.clinic_id
    )
    assert body["asset"]["asset_tag"] == (
        asset.asset_tag
    )
    assert body["asset"]["status"] == (
        asset.status.value
    )
    assert body["asset"]["is_active"] is (
        asset.is_active
    )


def test_create_asset_rejects_missing_json(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/v1/assets",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        data="not-json",
        content_type="text/plain",
    )

    assert response.status_code == 422


def test_create_asset_rejects_non_object_json(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/v1/assets",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json=["not", "an", "object"],
    )

    assert response.status_code == 422


def test_create_asset_rejects_unknown_field(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/v1/assets",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "asset_tag": "AST-UNKNOWN",
            "name": "Unknown Field Asset",
            "category": AssetCategory.COMPUTER.value,
            "unexpected": "value",
        },
    )

    assert response.status_code == 422


def test_create_asset_rejects_missing_required_field(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/v1/assets",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "name": "Missing Tag",
            "category": AssetCategory.COMPUTER.value,
        },
    )

    assert response.status_code == 422


def test_create_asset_rejects_blank_required_field(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/v1/assets",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "asset_tag": "   ",
            "name": "Blank Tag",
            "category": AssetCategory.COMPUTER.value,
        },
    )

    assert response.status_code == 422


# =============================================================================
# LIST
# =============================================================================


def test_list_assets_forwards_authenticated_clinic(
    client,
    user,
    asset,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    service = Mock(
        return_value=_asset_pagination(asset),
    )

    monkeypatch.setattr(
        asset_routes,
        "list_assets",
        service,
    )

    response = client.get(
        "/api/v1/assets",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 200

    kwargs = service.call_args.kwargs

    assert kwargs["clinic_id"] == user.clinic_id

    assert isinstance(
        kwargs["query"],
        AssetListQuerySchema,
    )


def test_list_assets_forwards_pagination(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    service = Mock(
        return_value={
            "items": [],
            "page": 3,
            "per_page": 25,
            "total": 70,
            "pages": 3,
            "has_next": False,
            "has_prev": True,
        },
    )

    monkeypatch.setattr(
        asset_routes,
        "list_assets",
        service,
    )

    response = client.get(
        "/api/v1/assets?page=3&per_page=25",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 200

    query = service.call_args.kwargs["query"]

    assert isinstance(
        query,
        AssetListQuerySchema,
    )

    assert query.page == 3
    assert query.per_page == 25


def test_list_assets_forwards_filters(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    service = Mock(
        return_value=_empty_pagination(),
    )

    monkeypatch.setattr(
        asset_routes,
        "list_assets",
        service,
    )

    response = client.get(
        "/api/v1/assets"
        "?search=ultrasound"
        "&category=medical_equipment"
        "&status=active"
        "&condition=good"
        "&ownership=clinic"
        "&maintenance_status=scheduled"
        "&assigned_to_id=7"
        "&is_active=true",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 200

    query = service.call_args.kwargs["query"]

    assert query.search == "ultrasound"
    assert query.category == (
        AssetCategory.MEDICAL_EQUIPMENT
    )
    assert query.status == AssetStatus.ACTIVE
    assert query.condition == AssetCondition.GOOD
    assert query.ownership == AssetOwnership.CLINIC
    assert query.maintenance_status == (
        MaintenanceStatus.SCHEDULED
    )
    assert query.assigned_to_id == 7
    assert query.is_active is True


def test_list_assets_serializes_items_and_pagination(
    client,
    user,
    asset,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "list_assets",
        Mock(
            return_value={
                "items": [asset],
                "page": 2,
                "per_page": 10,
                "total": 11,
                "pages": 2,
                "has_next": False,
                "has_prev": True,
            }
        ),
    )

    response = client.get(
        "/api/v1/assets?page=2&per_page=10",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == asset.id
    assert body["page"] == 2
    assert body["per_page"] == 10
    assert body["total"] == 11
    assert body["pages"] == 2
    assert body["has_next"] is False
    assert body["has_prev"] is True


def test_list_assets_returns_empty_result(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "list_assets",
        Mock(
            return_value=_empty_pagination()
        ),
    )

    response = client.get(
        "/api/v1/assets",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["items"] == []
    assert body["total"] == 0
    assert body["pages"] == 0


@pytest.mark.parametrize(
    "query_string",
    [
        "page=0",
        "page=-1",
        "per_page=0",
        "per_page=501",
        "unknown=value",
    ],
)
def test_list_assets_rejects_invalid_query(
    client,
    user,
    auth_headers_for,
    query_string,
):
    response = client.get(
        f"/api/v1/assets?{query_string}",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 422


# =============================================================================
# GET SINGLE
# =============================================================================


def test_get_asset_success(
    client,
    user,
    asset,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    service = Mock(
        return_value=asset,
    )

    monkeypatch.setattr(
        asset_routes,
        "get_asset",
        service,
    )

    response = client.get(
        f"/api/v1/assets/{asset.id}",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["asset"]["id"] == asset.id

    kwargs = service.call_args.kwargs

    assert kwargs["asset_id"] == asset.id
    assert kwargs["clinic_id"] == user.clinic_id


def test_get_asset_serializes_asset(
    client,
    user,
    asset,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "get_asset",
        Mock(return_value=asset),
    )

    response = client.get(
        f"/api/v1/assets/{asset.id}",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 200

    data = response.get_json()["asset"]

    assert data["id"] == asset.id
    assert data["clinic_id"] == asset.clinic_id
    assert data["asset_tag"] == asset.asset_tag
    assert data["name"] == asset.name
    assert data["category"] == (
        asset.category.value
    )
    assert data["status"] == (
        asset.status.value
    )
    assert data["condition"] == (
        asset.condition.value
    )
    assert data["ownership"] == (
        asset.ownership.value
    )


def test_get_asset_maps_not_found(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "get_asset",
        Mock(
            side_effect=NotFoundError(
                "Asset 999 not found"
            )
        ),
    )

    response = client.get(
        "/api/v1/assets/999",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 404

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Asset 999 not found"
    )


def test_get_asset_maps_conflict(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "get_asset",
        Mock(
            side_effect=ConflictError(
                "Asset conflict"
            )
        ),
    )

    response = client.get(
        "/api/v1/assets/1",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 409

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Asset conflict"


# =============================================================================
# UPDATE
# =============================================================================


def test_update_asset_success(
    client,
    user,
    asset,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    service = Mock(
        return_value=asset,
    )

    monkeypatch.setattr(
        asset_routes,
        "update_asset",
        service,
    )

    response = client.patch(
        f"/api/v1/assets/{asset.id}",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "name": "Updated Route Asset",
            "condition": (
                AssetCondition.EXCELLENT.value
            ),
            "purchase_cost": "50000.00",
        },
    )

    assert response.status_code == 200

    kwargs = service.call_args.kwargs

    assert kwargs["asset_id"] == asset.id
    assert kwargs["clinic_id"] == user.clinic_id
    assert kwargs["actor_user_id"] == user.id

    assert isinstance(
        kwargs["data"],
        AssetUpdateSchema,
    )

    assert kwargs["data"].name == (
        "Updated Route Asset"
    )

    assert kwargs["data"].condition == (
        AssetCondition.EXCELLENT
    )

    assert kwargs["data"].purchase_cost == (
        Decimal("50000.00")
    )


def test_update_asset_allows_partial_fields(
    client,
    user,
    asset,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    service = Mock(
        return_value=asset,
    )

    monkeypatch.setattr(
        asset_routes,
        "update_asset",
        service,
    )

    response = client.patch(
        f"/api/v1/assets/{asset.id}",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "name": "Partial Update",
        },
    )

    assert response.status_code == 200

    data = service.call_args.kwargs["data"]

    assert data.name == "Partial Update"

    assert (
        "description"
        not in data.model_dump(
            exclude_unset=True
        )
    )


def test_update_asset_serializes_response(
    client,
    user,
    asset,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "update_asset",
        Mock(return_value=asset),
    )

    response = client.patch(
        f"/api/v1/assets/{asset.id}",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={"name": "Updated"},
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["asset"]["id"] == asset.id


def test_update_asset_rejects_missing_json(
    client,
    user,
    auth_headers_for,
):
    response = client.patch(
        "/api/v1/assets/1",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        data="not-json",
        content_type="text/plain",
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"unknown": "value"},
        {"status": AssetStatus.RETIRED.value},
        {"is_active": False},
        {
            "retirement_date":
                date.today().isoformat()
        },
        {
            "disposal_date":
                date.today().isoformat()
        },
    ],
)
def test_update_asset_rejects_forbidden_or_unknown_fields(
    client,
    user,
    auth_headers_for,
    payload,
):
    response = client.patch(
        "/api/v1/assets/1",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json=payload,
    )

    assert response.status_code == 422


def test_update_asset_maps_not_found(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "update_asset",
        Mock(
            side_effect=NotFoundError(
                "Asset not found"
            )
        ),
    )

    response = client.patch(
        "/api/v1/assets/999",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={"name": "Updated"},
    )

    assert response.status_code == 404

    assert response.get_json()["error"] == (
        "Asset not found"
    )


def test_update_asset_maps_conflict(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "update_asset",
        Mock(
            side_effect=ConflictError(
                "Asset tag already exists"
            )
        ),
    )

    response = client.patch(
        "/api/v1/assets/1",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "asset_tag": "AST-EXISTING",
        },
    )

    assert response.status_code == 409

    assert response.get_json()["error"] == (
        "Asset tag already exists"
    )


# =============================================================================
# RETIRE
# =============================================================================


def test_retire_asset_success(
    client,
    user,
    asset,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    retired_asset = asset
    retired_asset.status = AssetStatus.RETIRED
    retired_asset.is_active = False
    retired_asset.retirement_date = date(
        2026,
        8,
        1,
    )

    service = Mock(
        return_value=retired_asset,
    )

    monkeypatch.setattr(
        asset_routes,
        "retire_asset",
        service,
    )

    response = client.post(
        f"/api/v1/assets/{asset.id}/retire",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "retirement_date": "2026-08-01",
        },
    )

    assert response.status_code == 200

    kwargs = service.call_args.kwargs

    assert kwargs["asset_id"] == asset.id
    assert kwargs["clinic_id"] == user.clinic_id
    assert kwargs["actor_user_id"] == user.id
    assert kwargs["retirement_date"] == date(
        2026,
        8,
        1,
    )

    body = response.get_json()

    assert body["success"] is True
    assert body["asset"]["id"] == asset.id


def test_retire_asset_allows_empty_json_body(
    client,
    user,
    asset,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    service = Mock(return_value=asset)

    monkeypatch.setattr(
        asset_routes,
        "retire_asset",
        service,
    )

    response = client.post(
        f"/api/v1/assets/{asset.id}/retire",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={},
    )

    assert response.status_code == 200

    kwargs = service.call_args.kwargs

    assert kwargs["retirement_date"] is None


def test_retire_asset_allows_missing_body(
    client,
    user,
    asset,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    service = Mock(return_value=asset)

    monkeypatch.setattr(
        asset_routes,
        "retire_asset",
        service,
    )

    response = client.post(
        f"/api/v1/assets/{asset.id}/retire",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 200

    kwargs = service.call_args.kwargs

    assert kwargs["retirement_date"] is None


def test_retire_asset_passes_schema(
    client,
    user,
    asset,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    schema = SimpleNamespace(
        retirement_date=date(
            2026,
            8,
            5,
        )
    )

    validator = Mock(
        return_value=schema
    )

    fake_schema = SimpleNamespace(
        model_validate=validator
    )

    monkeypatch.setattr(
        asset_routes,
        "AssetRetireSchema",
        fake_schema,
    )

    service = Mock(
        return_value=asset
    )

    monkeypatch.setattr(
        asset_routes,
        "retire_asset",
        service,
    )

    response = client.post(
        f"/api/v1/assets/{asset.id}/retire",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "retirement_date": "2026-08-05"
        },
    )

    assert response.status_code == 200

    validator.assert_called_once()

    assert (
        service.call_args.kwargs[
            "retirement_date"
        ]
        == date(2026, 8, 5)
    )


def test_retire_asset_rejects_invalid_date(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/v1/assets/1/retire",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "retirement_date": "not-a-date",
        },
    )

    assert response.status_code == 422


def test_retire_asset_rejects_unknown_field(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/v1/assets/1/retire",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "retirement_date": "2026-08-01",
            "unknown": "value",
        },
    )

    assert response.status_code == 422


def test_retire_asset_maps_not_found(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "retire_asset",
        Mock(
            side_effect=NotFoundError(
                "Asset not found"
            )
        ),
    )

    response = client.post(
        "/api/v1/assets/999/retire",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={},
    )

    assert response.status_code == 404

    assert response.get_json()["error"] == (
        "Asset not found"
    )


def test_retire_asset_maps_conflict(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "retire_asset",
        Mock(
            side_effect=ConflictError(
                "Asset is already retired"
            )
        ),
    )

    response = client.post(
        "/api/v1/assets/1/retire",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={},
    )

    assert response.status_code == 409

    assert response.get_json()["error"] == (
        "Asset is already retired"
    )


# =============================================================================
# DISPOSE
# =============================================================================


def test_dispose_asset_success(
    client,
    user,
    asset,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    disposed_asset = asset
    disposed_asset.status = AssetStatus.DISPOSED
    disposed_asset.is_active = False
    disposed_asset.retirement_date = date(
        2026,
        8,
        1,
    )
    disposed_asset.disposal_date = date(
        2026,
        9,
        1,
    )
    disposed_asset.disposal_reason = (
        "Beyond economical repair"
    )

    service = Mock(
        return_value=disposed_asset,
    )

    monkeypatch.setattr(
        asset_routes,
        "dispose_asset",
        service,
    )

    response = client.post(
        f"/api/v1/assets/{asset.id}/dispose",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "disposal_reason": (
                "Beyond economical repair"
            ),
            "disposal_date": "2026-09-01",
        },
    )

    assert response.status_code == 200

    kwargs = service.call_args.kwargs

    assert kwargs["asset_id"] == asset.id
    assert kwargs["clinic_id"] == user.clinic_id
    assert kwargs["actor_user_id"] == user.id
    assert kwargs["disposal_reason"] == (
        "Beyond economical repair"
    )
    assert kwargs["disposal_date"] == date(
        2026,
        9,
        1,
    )

    body = response.get_json()

    assert body["success"] is True
    assert body["asset"]["id"] == asset.id


def test_dispose_asset_accepts_reason_only(
    client,
    user,
    asset,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    service = Mock(
        return_value=asset,
    )

    monkeypatch.setattr(
        asset_routes,
        "dispose_asset",
        service,
    )

    response = client.post(
        f"/api/v1/assets/{asset.id}/dispose",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "disposal_reason": "Routine disposal",
        },
    )

    assert response.status_code == 200

    kwargs = service.call_args.kwargs

    assert kwargs["disposal_reason"] == (
        "Routine disposal"
    )

    assert kwargs["disposal_date"] is None


def test_dispose_asset_rejects_missing_json(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/v1/assets/1/dispose",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        data="not-json",
        content_type="text/plain",
    )

    assert response.status_code == 422


def test_dispose_asset_rejects_non_object_json(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/v1/assets/1/dispose",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json=[],
    )

    assert response.status_code == 422


def test_dispose_asset_rejects_missing_reason(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/v1/assets/1/dispose",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={},
    )

    assert response.status_code == 422


def test_dispose_asset_rejects_invalid_disposal_date(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/v1/assets/1/dispose",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "disposal_reason": "Dispose",
            "disposal_date": "not-a-date",
        },
    )

    assert response.status_code == 422


def test_dispose_asset_rejects_unknown_field(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/v1/assets/1/dispose",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "disposal_reason": "Dispose",
            "unknown": "value",
        },
    )

    assert response.status_code == 422


def test_dispose_asset_maps_not_found(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "dispose_asset",
        Mock(
            side_effect=NotFoundError(
                "Asset not found"
            )
        ),
    )

    response = client.post(
        "/api/v1/assets/999/dispose",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "disposal_reason": "Dispose",
        },
    )

    assert response.status_code == 404

    assert response.get_json()["error"] == (
        "Asset not found"
    )


def test_dispose_asset_maps_validation_error(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "dispose_asset",
        Mock(
            side_effect=ValidationError(
                "Asset must be retired before disposal"
            )
        ),
    )

    response = client.post(
        "/api/v1/assets/1/dispose",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "disposal_reason": "Dispose",
        },
    )

    assert response.status_code == 422

    assert response.get_json()["error"] == (
        "Asset must be retired before disposal"
    )


# =============================================================================
# ASSIGN
# =============================================================================


def test_assign_asset_forwards_context(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    schema = object()

    validator = Mock(
        return_value=schema
    )

    fake_schema = SimpleNamespace(
        model_validate=validator
    )

    monkeypatch.setattr(
        asset_routes,
        "AssetAssignmentCreateSchema",
        fake_schema,
    )

    service = Mock(
        return_value=object()
    )

    monkeypatch.setattr(
        asset_routes,
        "assign_asset",
        service,
    )

    _patch_assignment_serializer(
        asset_routes,
        monkeypatch,
        {"id": 123},
    )

    response = client.post(
        "/api/v1/assets/10/assign",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "staff_id": 7
        },
    )

    assert response.status_code == 201

    validator.assert_called_once()

    kwargs = service.call_args.kwargs

    assert kwargs["asset_id"] == 10
    assert kwargs["clinic_id"] == user.clinic_id
    assert kwargs["actor_user_id"] == user.id
    assert kwargs["data"] is schema


def test_assign_asset_serializes_response(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "AssetAssignmentCreateSchema",
        SimpleNamespace(
            model_validate=Mock(
                return_value=object()
            )
        ),
    )

    monkeypatch.setattr(
        asset_routes,
        "assign_asset",
        Mock(return_value=object()),
    )

    _patch_assignment_serializer(
        asset_routes,
        monkeypatch,
        {
            "id": 55,
            "asset_id": 10,
        },
    )

    response = client.post(
        "/api/v1/assets/10/assign",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={},
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert body["assignment"]["id"] == 55
    assert body["assignment"]["asset_id"] == 10


def test_assign_asset_maps_conflict(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "AssetAssignmentCreateSchema",
        SimpleNamespace(
            model_validate=Mock(
                return_value=object()
            )
        ),
    )

    monkeypatch.setattr(
        asset_routes,
        "assign_asset",
        Mock(
            side_effect=ConflictError(
                "Asset is not available"
            )
        ),
    )

    response = client.post(
        "/api/v1/assets/10/assign",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={},
    )

    assert response.status_code == 409

    assert response.get_json()["error"] == (
        "Asset is not available"
    )


# =============================================================================
# RETURN
# =============================================================================


def test_return_asset_forwards_context(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    schema = object()

    validator = Mock(
        return_value=schema
    )

    monkeypatch.setattr(
        asset_routes,
        "AssetAssignmentReturnSchema",
        SimpleNamespace(
            model_validate=validator
        ),
    )

    service = Mock(
        return_value=object()
    )

    monkeypatch.setattr(
        asset_routes,
        "return_asset",
        service,
    )

    _patch_assignment_serializer(
        asset_routes,
        monkeypatch,
        {"id": 22},
    )

    response = client.post(
        "/api/v1/assets/10/return",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={},
    )

    assert response.status_code == 200

    kwargs = service.call_args.kwargs

    assert kwargs["asset_id"] == 10
    assert kwargs["clinic_id"] == user.clinic_id
    assert kwargs["actor_user_id"] == user.id
    assert kwargs["data"] is schema


def test_return_asset_allows_missing_body(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    schema = object()

    monkeypatch.setattr(
        asset_routes,
        "AssetAssignmentReturnSchema",
        SimpleNamespace(
            model_validate=Mock(
                return_value=schema
            )
        ),
    )

    service = Mock(
        return_value=object()
    )

    monkeypatch.setattr(
        asset_routes,
        "return_asset",
        service,
    )

    _patch_assignment_serializer(
        asset_routes,
        monkeypatch,
        {"id": 2},
    )

    response = client.post(
        "/api/v1/assets/10/return",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 200

    assert (
        service.call_args.kwargs["asset_id"]
        == 10
    )


def test_return_asset_maps_not_found(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "AssetAssignmentReturnSchema",
        SimpleNamespace(
            model_validate=Mock(
                return_value=object()
            )
        ),
    )

    monkeypatch.setattr(
        asset_routes,
        "return_asset",
        Mock(
            side_effect=NotFoundError(
                "Assignment not found"
            )
        ),
    )

    response = client.post(
        "/api/v1/assets/10/return",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 404

    assert response.get_json()["error"] == (
        "Assignment not found"
    )


# =============================================================================
# ASSIGNMENT LIST / GET
# =============================================================================


def test_list_asset_assignments_verifies_asset_and_forwards_query(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    get_asset_service = Mock(
        return_value=object()
    )

    monkeypatch.setattr(
        asset_routes,
        "get_asset",
        get_asset_service,
    )

    query = SimpleNamespace(
        page=2,
        per_page=10,
        asset_id=10,
    )

    validator = Mock(
        return_value=query
    )

    monkeypatch.setattr(
        asset_routes,
        "AssetAssignmentListQuerySchema",
        SimpleNamespace(
            model_validate=validator
        ),
    )

    service = Mock(
        return_value={
            "items": [object()],
            "page": 2,
            "per_page": 10,
            "total": 1,
            "pages": 1,
            "has_next": False,
            "has_prev": True,
        }
    )

    monkeypatch.setattr(
        asset_routes,
        "list_asset_assignments",
        service,
    )

    _patch_assignment_serializer(
        asset_routes,
        monkeypatch,
    )

    response = client.get(
        "/api/v1/assets/10/assignments"
        "?page=2&per_page=10",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 200

    get_kwargs = (
        get_asset_service.call_args.kwargs
    )

    assert get_kwargs["asset_id"] == 10
    assert (
        get_kwargs["clinic_id"]
        == user.clinic_id
    )

    query_payload = validator.call_args.args[0]

    assert query_payload["asset_id"] == 10
    assert query_payload["page"] == "2"
    assert query_payload["per_page"] == "10"

    service_kwargs = (
        service.call_args.kwargs
    )

    assert (
        service_kwargs["clinic_id"]
        == user.clinic_id
    )
    assert service_kwargs["query"] is query


def test_list_asset_assignments_serializes_pagination(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "get_asset",
        Mock(return_value=object()),
    )

    monkeypatch.setattr(
        asset_routes,
        "AssetAssignmentListQuerySchema",
        SimpleNamespace(
            model_validate=Mock(
                return_value=object()
            )
        ),
    )

    monkeypatch.setattr(
        asset_routes,
        "list_asset_assignments",
        Mock(
            return_value={
                "items": [object()],
                "page": 1,
                "per_page": 10,
                "total": 1,
                "pages": 1,
                "has_next": False,
                "has_prev": False,
            }
        ),
    )

    _patch_assignment_serializer(
        asset_routes,
        monkeypatch,
        {"id": 7},
    )

    response = client.get(
        "/api/v1/assets/10/assignments",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["items"] == [{"id": 7}]
    assert body["page"] == 1
    assert body["per_page"] == 10
    assert body["total"] == 1
    assert body["pages"] == 1


def test_get_asset_assignment_forwards_context(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    assignment = object()

    service = Mock(
        return_value=assignment
    )

    monkeypatch.setattr(
        asset_routes,
        "get_asset_assignment",
        service,
    )

    _patch_assignment_serializer(
        asset_routes,
        monkeypatch,
        {"id": 77},
    )

    response = client.get(
        "/api/v1/assets/assignments/77",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 200

    kwargs = service.call_args.kwargs

    assert kwargs["assignment_id"] == 77
    assert kwargs["clinic_id"] == user.clinic_id

    body = response.get_json()

    assert body["success"] is True
    assert body["assignment"]["id"] == 77


def test_get_asset_assignment_maps_not_found(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "get_asset_assignment",
        Mock(
            side_effect=NotFoundError(
                "Assignment not found"
            )
        ),
    )

    response = client.get(
        "/api/v1/assets/assignments/77",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 404

    assert response.get_json()["error"] == (
        "Assignment not found"
    )


# =============================================================================
# HISTORY
# =============================================================================


def test_list_asset_history_verifies_asset_and_forwards_query(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    get_asset_service = Mock(
        return_value=object()
    )

    monkeypatch.setattr(
        asset_routes,
        "get_asset",
        get_asset_service,
    )

    query = SimpleNamespace(
        page=1,
        per_page=20,
        asset_id=12,
    )

    validator = Mock(
        return_value=query
    )

    monkeypatch.setattr(
        asset_routes,
        "AssetHistoryListQuerySchema",
        SimpleNamespace(
            model_validate=validator
        ),
    )

    service = Mock(
        return_value={
            "items": [object()],
            "page": 1,
            "per_page": 20,
            "total": 1,
            "pages": 1,
            "has_next": False,
            "has_prev": False,
        }
    )

    monkeypatch.setattr(
        asset_routes,
        "list_asset_history",
        service,
    )

    _patch_history_serializer(
        asset_routes,
        monkeypatch,
        {"id": 100},
    )

    response = client.get(
        "/api/v1/assets/12/history?page=1&per_page=20",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 200

    get_kwargs = (
        get_asset_service.call_args.kwargs
    )

    assert get_kwargs["asset_id"] == 12
    assert (
        get_kwargs["clinic_id"]
        == user.clinic_id
    )

    payload = validator.call_args.args[0]

    assert payload["asset_id"] == 12
    assert payload["page"] == "1"
    assert payload["per_page"] == "20"

    kwargs = service.call_args.kwargs

    assert (
        kwargs["clinic_id"]
        == user.clinic_id
    )

    assert kwargs["query"] is query

    body = response.get_json()

    assert body["success"] is True
    assert body["items"] == [{"id": 100}]


def test_get_asset_history_forwards_context(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    history = object()

    service = Mock(
        return_value=history
    )

    monkeypatch.setattr(
        asset_routes,
        "get_asset_history",
        service,
    )

    _patch_history_serializer(
        asset_routes,
        monkeypatch,
        {"id": 88},
    )

    response = client.get(
        "/api/v1/assets/history/88",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 200

    kwargs = service.call_args.kwargs

    assert kwargs["history_id"] == 88
    assert kwargs["clinic_id"] == user.clinic_id

    body = response.get_json()

    assert body["success"] is True
    assert body["history"]["id"] == 88


def test_get_asset_history_maps_not_found(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "get_asset_history",
        Mock(
            side_effect=NotFoundError(
                "History not found"
            )
        ),
    )

    response = client.get(
        "/api/v1/assets/history/88",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 404

    assert response.get_json()["error"] == (
        "History not found"
    )


# =============================================================================
# MAINTENANCE
# =============================================================================


def test_schedule_maintenance_forwards_context(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    schema = object()

    monkeypatch.setattr(
        asset_routes,
        "AssetMaintenanceScheduleSchema",
        SimpleNamespace(
            model_validate=Mock(
                return_value=schema
            )
        ),
    )

    service = Mock(
        return_value=object()
    )

    monkeypatch.setattr(
        asset_routes,
        "schedule_maintenance",
        service,
    )

    _patch_maintenance_serializer(
        asset_routes,
        monkeypatch,
        {"id": 201},
    )

    response = client.post(
        "/api/v1/assets/25/maintenance",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={},
    )

    assert response.status_code == 201

    kwargs = service.call_args.kwargs

    assert kwargs["asset_id"] == 25
    assert kwargs["clinic_id"] == user.clinic_id
    assert kwargs["actor_user_id"] == user.id
    assert kwargs["data"] is schema

    body = response.get_json()

    assert body["success"] is True
    assert body["maintenance"]["id"] == 201


def test_schedule_maintenance_maps_conflict(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "AssetMaintenanceScheduleSchema",
        SimpleNamespace(
            model_validate=Mock(
                return_value=object()
            )
        ),
    )

    monkeypatch.setattr(
        asset_routes,
        "schedule_maintenance",
        Mock(
            side_effect=ConflictError(
                "Maintenance already exists"
            )
        ),
    )

    response = client.post(
        "/api/v1/assets/25/maintenance",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={},
    )

    assert response.status_code == 409

    assert response.get_json()["error"] == (
        "Maintenance already exists"
    )


def test_list_asset_maintenance_verifies_asset_and_forwards_query(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    get_asset_service = Mock(
        return_value=object()
    )

    monkeypatch.setattr(
        asset_routes,
        "get_asset",
        get_asset_service,
    )

    query = object()

    validator = Mock(
        return_value=query
    )

    monkeypatch.setattr(
        asset_routes,
        "AssetMaintenanceListQuerySchema",
        SimpleNamespace(
            model_validate=validator
        ),
    )

    service = Mock(
        return_value={
            "items": [object()],
            "page": 1,
            "per_page": 10,
            "total": 1,
            "pages": 1,
            "has_next": False,
            "has_prev": False,
        }
    )

    monkeypatch.setattr(
        asset_routes,
        "list_asset_maintenance",
        service,
    )

    _patch_maintenance_serializer(
        asset_routes,
        monkeypatch,
        {"id": 301},
    )

    response = client.get(
        "/api/v1/assets/25/maintenance"
        "?page=1&per_page=10",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 200

    get_kwargs = (
        get_asset_service.call_args.kwargs
    )

    assert get_kwargs["asset_id"] == 25
    assert (
        get_kwargs["clinic_id"]
        == user.clinic_id
    )

    payload = validator.call_args.args[0]

    assert payload["asset_id"] == 25
    assert payload["page"] == "1"
    assert payload["per_page"] == "10"

    kwargs = service.call_args.kwargs

    assert kwargs["clinic_id"] == user.clinic_id
    assert kwargs["query"] is query

    body = response.get_json()

    assert body["success"] is True
    assert body["items"] == [{"id": 301}]


def test_get_asset_maintenance_forwards_context(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    service = Mock(
        return_value=object()
    )

    monkeypatch.setattr(
        asset_routes,
        "get_asset_maintenance",
        service,
    )

    _patch_maintenance_serializer(
        asset_routes,
        monkeypatch,
        {"id": 401},
    )

    response = client.get(
        "/api/v1/assets/maintenance/401",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 200

    kwargs = service.call_args.kwargs

    assert (
        kwargs["maintenance_id"]
        == 401
    )
    assert (
        kwargs["clinic_id"]
        == user.clinic_id
    )

    body = response.get_json()

    assert body["success"] is True
    assert body["maintenance"]["id"] == 401


def test_get_asset_maintenance_maps_not_found(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "get_asset_maintenance",
        Mock(
            side_effect=NotFoundError(
                "Maintenance not found"
            )
        ),
    )

    response = client.get(
        "/api/v1/assets/maintenance/401",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 404

    assert response.get_json()["error"] == (
        "Maintenance not found"
    )


def test_start_maintenance_forwards_context(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    schema = object()

    monkeypatch.setattr(
        asset_routes,
        "AssetMaintenanceStartSchema",
        SimpleNamespace(
            model_validate=Mock(
                return_value=schema
            )
        ),
    )

    service = Mock(
        return_value=object()
    )

    monkeypatch.setattr(
        asset_routes,
        "start_maintenance",
        service,
    )

    _patch_maintenance_serializer(
        asset_routes,
        monkeypatch,
        {"id": 501},
    )

    response = client.post(
        "/api/v1/assets/maintenance/501/start",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={},
    )

    assert response.status_code == 200

    kwargs = service.call_args.kwargs

    assert kwargs["maintenance_id"] == 501
    assert kwargs["clinic_id"] == user.clinic_id
    assert kwargs["actor_user_id"] == user.id
    assert kwargs["data"] is schema


def test_start_maintenance_allows_missing_body(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    schema = object()

    monkeypatch.setattr(
        asset_routes,
        "AssetMaintenanceStartSchema",
        SimpleNamespace(
            model_validate=Mock(
                return_value=schema
            )
        ),
    )

    service = Mock(
        return_value=object()
    )

    monkeypatch.setattr(
        asset_routes,
        "start_maintenance",
        service,
    )

    _patch_maintenance_serializer(
        asset_routes,
        monkeypatch,
    )

    response = client.post(
        "/api/v1/assets/maintenance/501/start",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 200

    assert (
        service.call_args.kwargs["data"]
        is schema
    )


def test_start_maintenance_maps_conflict(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "AssetMaintenanceStartSchema",
        SimpleNamespace(
            model_validate=Mock(
                return_value=object()
            )
        ),
    )

    monkeypatch.setattr(
        asset_routes,
        "start_maintenance",
        Mock(
            side_effect=ConflictError(
                "Maintenance already started"
            )
        ),
    )

    response = client.post(
        "/api/v1/assets/maintenance/501/start",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={},
    )

    assert response.status_code == 409

    assert response.get_json()["error"] == (
        "Maintenance already started"
    )


def test_complete_maintenance_forwards_context(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    schema = object()

    monkeypatch.setattr(
        asset_routes,
        "AssetMaintenanceCompleteSchema",
        SimpleNamespace(
            model_validate=Mock(
                return_value=schema
            )
        ),
    )

    service = Mock(
        return_value=object()
    )

    monkeypatch.setattr(
        asset_routes,
        "complete_maintenance",
        service,
    )

    _patch_maintenance_serializer(
        asset_routes,
        monkeypatch,
        {"id": 601},
    )

    response = client.post(
        "/api/v1/assets/maintenance/601/complete",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={},
    )

    assert response.status_code == 200

    kwargs = service.call_args.kwargs

    assert kwargs["maintenance_id"] == 601
    assert kwargs["clinic_id"] == user.clinic_id
    assert kwargs["actor_user_id"] == user.id
    assert kwargs["data"] is schema


def test_complete_maintenance_allows_missing_body(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    schema = object()

    monkeypatch.setattr(
        asset_routes,
        "AssetMaintenanceCompleteSchema",
        SimpleNamespace(
            model_validate=Mock(
                return_value=schema
            )
        ),
    )

    service = Mock(
        return_value=object()
    )

    monkeypatch.setattr(
        asset_routes,
        "complete_maintenance",
        service,
    )

    _patch_maintenance_serializer(
        asset_routes,
        monkeypatch,
    )

    response = client.post(
        "/api/v1/assets/maintenance/601/complete",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 200

    assert (
        service.call_args.kwargs["data"]
        is schema
    )


def test_complete_maintenance_maps_not_found(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "AssetMaintenanceCompleteSchema",
        SimpleNamespace(
            model_validate=Mock(
                return_value=object()
            )
        ),
    )

    monkeypatch.setattr(
        asset_routes,
        "complete_maintenance",
        Mock(
            side_effect=NotFoundError(
                "Maintenance not found"
            )
        ),
    )

    response = client.post(
        "/api/v1/assets/maintenance/601/complete",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={},
    )

    assert response.status_code == 404

    assert response.get_json()["error"] == (
        "Maintenance not found"
    )


def test_cancel_maintenance_forwards_context(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    schema = object()

    monkeypatch.setattr(
        asset_routes,
        "AssetMaintenanceCancelSchema",
        SimpleNamespace(
            model_validate=Mock(
                return_value=schema
            )
        ),
    )

    service = Mock(
        return_value=object()
    )

    monkeypatch.setattr(
        asset_routes,
        "cancel_maintenance",
        service,
    )

    _patch_maintenance_serializer(
        asset_routes,
        monkeypatch,
        {"id": 701},
    )

    response = client.post(
        "/api/v1/assets/maintenance/701/cancel",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "reason": "Cancelled",
        },
    )

    assert response.status_code == 200

    kwargs = service.call_args.kwargs

    assert kwargs["maintenance_id"] == 701
    assert kwargs["clinic_id"] == user.clinic_id
    assert kwargs["actor_user_id"] == user.id
    assert kwargs["data"] is schema


def test_cancel_maintenance_rejects_missing_json(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/v1/assets/maintenance/701/cancel",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        data="not-json",
        content_type="text/plain",
    )

    assert response.status_code == 422


def test_cancel_maintenance_maps_conflict(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "AssetMaintenanceCancelSchema",
        SimpleNamespace(
            model_validate=Mock(
                return_value=object()
            )
        ),
    )

    monkeypatch.setattr(
        asset_routes,
        "cancel_maintenance",
        Mock(
            side_effect=ConflictError(
                "Maintenance cannot be cancelled"
            )
        ),
    )

    response = client.post(
        "/api/v1/assets/maintenance/701/cancel",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "reason": "Cancelled",
        },
    )

    assert response.status_code == 409

    assert response.get_json()["error"] == (
        "Maintenance cannot be cancelled"
    )


# =============================================================================
# SERIALIZATION
# =============================================================================


def test_response_serializes_asset_enum_values(
    client,
    user,
    asset,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    asset.category = AssetCategory.COMPUTER
    asset.status = AssetStatus.ACTIVE
    asset.condition = AssetCondition.GOOD
    asset.ownership = AssetOwnership.CLINIC
    asset.maintenance_status = (
        MaintenanceStatus.NOT_REQUIRED
    )

    monkeypatch.setattr(
        asset_routes,
        "get_asset",
        Mock(return_value=asset),
    )

    response = client.get(
        f"/api/v1/assets/{asset.id}",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 200

    data = response.get_json()["asset"]

    assert data["category"] == "computer"
    assert data["status"] == "active"
    assert data["condition"] == "good"
    assert data["ownership"] == "clinic"
    assert data["maintenance_status"] == (
        "not_required"
    )


# =============================================================================
# UNEXPECTED ERRORS
# =============================================================================


def test_unexpected_exception_is_not_exposed(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "get_asset",
        Mock(
            side_effect=RuntimeError(
                "SECRET INTERNAL DETAIL"
            )
        ),
    )

    response = client.get(
        "/api/v1/assets/1",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Internal server error"
    )

    assert (
        "SECRET INTERNAL DETAIL"
        not in response.text
    )
