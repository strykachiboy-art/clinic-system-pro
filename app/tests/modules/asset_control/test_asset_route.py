from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import Mock

import pytest

from app.core.enums.asset_enums import (
    AssetCategory,
    AssetCondition,
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
from app.modules.asset_control.schemas.asset_schema import (
    AssetCreateSchema,
    AssetListQuerySchema,
    AssetUpdateSchema,
)


# =============================================================================
# ROUTE MODULE
# =============================================================================


@pytest.fixture()
def asset_routes():
    from app.modules.asset_control.routes import asset_route

    return asset_route


# =============================================================================
# AUTHORIZATION
# =============================================================================


def test_create_asset_allows_admin(
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
        "/api/assets",
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
        "/api/assets",
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


def test_create_asset_forbidden_for_doctor(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    doctor = make_user(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        "/api/assets",
        headers=auth_headers_for(
            doctor,
            role=Role.DOCTOR,
        ),
        json={
            "asset_tag": "AST-FORBIDDEN",
            "name": "Forbidden Asset",
            "category": AssetCategory.COMPUTER.value,
        },
    )

    assert response.status_code == 403


def test_list_assets_allows_admin(
    client,
    user,
    monkeypatch,
    auth_headers_for,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "list_assets",
        Mock(
            return_value={
                "items": [],
                "page": 1,
                "per_page": 50,
                "total": 0,
                "pages": 0,
                "has_next": False,
                "has_prev": False,
            }
        ),
    )

    response = client.get(
        "/api/assets",
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
            return_value={
                "items": [],
                "page": 1,
                "per_page": 50,
                "total": 0,
                "pages": 0,
                "has_next": False,
                "has_prev": False,
            }
        ),
    )

    response = client.get(
        "/api/assets",
        headers=auth_headers_for(
            accountant,
            role=Role.ACCOUNTANT,
        ),
    )

    assert response.status_code == 200


def test_list_assets_forbidden_for_doctor(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    doctor = make_user(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/assets",
        headers=auth_headers_for(
            doctor,
            role=Role.DOCTOR,
        ),
    )

    assert response.status_code == 403


def test_get_asset_forbidden_for_doctor(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    doctor = make_user(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/assets/1",
        headers=auth_headers_for(
            doctor,
            role=Role.DOCTOR,
        ),
    )

    assert response.status_code == 403


def test_update_asset_forbidden_for_doctor(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    doctor = make_user(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    response = client.patch(
        "/api/assets/1",
        headers=auth_headers_for(
            doctor,
            role=Role.DOCTOR,
        ),
        json={
            "name": "Forbidden Update",
        },
    )

    assert response.status_code == 403


def test_retire_asset_forbidden_for_doctor(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    doctor = make_user(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        "/api/assets/1/retire",
        headers=auth_headers_for(
            doctor,
            role=Role.DOCTOR,
        ),
        json={},
    )

    assert response.status_code == 403


def test_dispose_asset_forbidden_for_doctor(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    doctor = make_user(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        "/api/assets/1/dispose",
        headers=auth_headers_for(
            doctor,
            role=Role.DOCTOR,
        ),
        json={
            "disposal_reason": "Disposed",
        },
    )

    assert response.status_code == 403


# =============================================================================
# UNAUTHENTICATED
# =============================================================================


def test_create_asset_requires_authentication(
    client,
):
    response = client.post(
        "/api/assets",
        json={
            "asset_tag": "AST-NO-AUTH",
            "name": "No Auth Asset",
            "category": AssetCategory.COMPUTER.value,
        },
    )

    assert response.status_code == 401


def test_list_assets_requires_authentication(
    client,
):
    response = client.get(
        "/api/assets",
    )

    assert response.status_code == 401


def test_get_asset_requires_authentication(
    client,
):
    response = client.get(
        "/api/assets/1",
    )

    assert response.status_code == 401


def test_update_asset_requires_authentication(
    client,
):
    response = client.patch(
        "/api/assets/1",
        json={
            "name": "No Auth",
        },
    )

    assert response.status_code == 401


def test_retire_asset_requires_authentication(
    client,
):
    response = client.post(
        "/api/assets/1/retire",
        json={},
    )

    assert response.status_code == 401


def test_dispose_asset_requires_authentication(
    client,
):
    response = client.post(
        "/api/assets/1/dispose",
        json={
            "disposal_reason": "No Auth",
        },
    )

    assert response.status_code == 401


# =============================================================================
# CREATE
# =============================================================================


def test_create_asset_forwards_authenticated_context(
    client,
    clinic,
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
        "/api/assets",
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
        "/api/assets",
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
    assert body["asset"]["clinic_id"] == asset.clinic_id
    assert body["asset"]["asset_tag"] == asset.asset_tag
    assert body["asset"]["status"] == (
        asset.status.value
    )
    assert body["asset"]["is_active"] is asset.is_active


def test_create_asset_rejects_missing_json(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/assets",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        data="not-json",
        content_type="text/plain",
    )

    assert response.status_code == 422


def test_create_asset_rejects_unknown_field(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/assets",
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
        "/api/assets",
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
        "/api/assets",
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
        return_value={
            "items": [asset],
            "page": 1,
            "per_page": 50,
            "total": 1,
            "pages": 1,
            "has_next": False,
            "has_prev": False,
        },
    )

    monkeypatch.setattr(
        asset_routes,
        "list_assets",
        service,
    )

    response = client.get(
        "/api/assets",
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
        "/api/assets?page=3&per_page=25",
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
        return_value={
            "items": [],
            "page": 1,
            "per_page": 50,
            "total": 0,
            "pages": 0,
            "has_next": False,
            "has_prev": False,
        },
    )

    monkeypatch.setattr(
        asset_routes,
        "list_assets",
        service,
    )

    response = client.get(
        "/api/assets"
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
        "/api/assets?page=2&per_page=10",
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
            return_value={
                "items": [],
                "page": 1,
                "per_page": 50,
                "total": 0,
                "pages": 0,
                "has_next": False,
                "has_prev": False,
            }
        ),
    )

    response = client.get(
        "/api/assets",
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


def test_list_assets_rejects_invalid_page(
    client,
    user,
    auth_headers_for,
):
    response = client.get(
        "/api/assets?page=0",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 422


def test_list_assets_rejects_invalid_per_page(
    client,
    user,
    auth_headers_for,
):
    response = client.get(
        "/api/assets?per_page=501",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 422


def test_list_assets_rejects_unknown_query_parameter(
    client,
    user,
    auth_headers_for,
):
    response = client.get(
        "/api/assets?unknown=value",
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
        f"/api/assets/{asset.id}",
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
        f"/api/assets/{asset.id}",
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
        "/api/assets/999",
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
        f"/api/assets/{asset.id}",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "name": "Updated Route Asset",
            "condition": AssetCondition.EXCELLENT.value,
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
        f"/api/assets/{asset.id}",
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
        f"/api/assets/{asset.id}",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "name": "Updated",
        },
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
        "/api/assets/1",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        data="not-json",
        content_type="text/plain",
    )

    assert response.status_code == 422


def test_update_asset_rejects_unknown_field(
    client,
    user,
    auth_headers_for,
):
    response = client.patch(
        "/api/assets/1",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "unknown": "value",
        },
    )

    assert response.status_code == 422


def test_update_asset_rejects_status_field(
    client,
    user,
    auth_headers_for,
):
    response = client.patch(
        "/api/assets/1",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "status": AssetStatus.RETIRED.value,
        },
    )

    assert response.status_code == 422


def test_update_asset_rejects_is_active_field(
    client,
    user,
    auth_headers_for,
):
    response = client.patch(
        "/api/assets/1",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "is_active": False,
        },
    )

    assert response.status_code == 422


def test_update_asset_rejects_retirement_date_field(
    client,
    user,
    auth_headers_for,
):
    response = client.patch(
        "/api/assets/1",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "retirement_date": date.today().isoformat(),
        },
    )

    assert response.status_code == 422


def test_update_asset_rejects_disposal_date_field(
    client,
    user,
    auth_headers_for,
):
    response = client.patch(
        "/api/assets/1",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "disposal_date": date.today().isoformat(),
        },
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
        "/api/assets/999",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "name": "Updated",
        },
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
            ),
        ),
    )

    response = client.patch(
        "/api/assets/1",
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
    retired_asset.retirement_date = date(2026, 8, 1)

    service = Mock(
        return_value=retired_asset,
    )

    monkeypatch.setattr(
        asset_routes,
        "retire_asset",
        service,
    )

    response = client.post(
        f"/api/assets/{asset.id}/retire",
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
    monkeypatch.setattr(
        asset_routes,
        "retire_asset",
        Mock(return_value=asset),
    )

    response = client.post(
        f"/api/assets/{asset.id}/retire",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={},
    )

    assert response.status_code == 200

    kwargs = (
        asset_routes.retire_asset
        .call_args.kwargs
    )

    assert kwargs["retirement_date"] is None


def test_retire_asset_allows_missing_body(
    client,
    user,
    asset,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    monkeypatch.setattr(
        asset_routes,
        "retire_asset",
        Mock(return_value=asset),
    )

    response = client.post(
        f"/api/assets/{asset.id}/retire",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 200

    kwargs = (
        asset_routes.retire_asset
        .call_args.kwargs
    )

    assert kwargs["retirement_date"] is None


def test_retire_asset_rejects_invalid_date(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/assets/1/retire",
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
        "/api/assets/1/retire",
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
            ),
        ),
    )

    response = client.post(
        "/api/assets/999/retire",
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
            ),
        ),
    )

    response = client.post(
        "/api/assets/1/retire",
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
    disposed_asset.retirement_date = date(2026, 8, 1)
    disposed_asset.disposal_date = date(2026, 9, 1)
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
        f"/api/assets/{asset.id}/dispose",
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
    monkeypatch.setattr(
        asset_routes,
        "dispose_asset",
        Mock(return_value=asset),
    )

    response = client.post(
        f"/api/assets/{asset.id}/dispose",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "disposal_reason": "Routine disposal",
        },
    )

    assert response.status_code == 200

    kwargs = (
        asset_routes.dispose_asset
        .call_args.kwargs
    )

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
        "/api/assets/1/dispose",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        data="not-json",
        content_type="text/plain",
    )

    assert response.status_code == 422


def test_dispose_asset_rejects_missing_reason(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/assets/1/dispose",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={},
    )

    assert response.status_code == 422


def test_dispose_asset_rejects_blank_reason(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/assets/1/dispose",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "disposal_reason": "   ",
        },
    )

    assert response.status_code == 422


def test_dispose_asset_rejects_reason_over_500(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/assets/1/dispose",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "disposal_reason": "x" * 501,
        },
    )

    assert response.status_code == 422


def test_dispose_asset_rejects_invalid_disposal_date(
    client,
    user,
    auth_headers_for,
):
    response = client.post(
        "/api/assets/1/dispose",
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
        "/api/assets/1/dispose",
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
            ),
        ),
    )

    response = client.post(
        "/api/assets/999/dispose",
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
            ),
        ),
    )

    response = client.post(
        "/api/assets/1/dispose",
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
# CURRENT USER / CLINIC CONTEXT
# =============================================================================


def test_inactive_authenticated_user_is_rejected(
    client,
    user,
    db,
    auth_headers_for,
):
    user.is_active = False
    db.session.flush()

    response = client.get(
        "/api/assets",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "inactive" in body["error"].lower()


def test_authenticated_user_without_clinic_is_rejected(
    client,
    user,
    db,
    auth_headers_for,
):
    user.clinic_id = None
    db.session.flush()

    response = client.get(
        "/api/assets",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "clinic" in body["error"].lower()


# =============================================================================
# HTTP ERROR TRANSLATION
# =============================================================================


@pytest.mark.parametrize(
    "exception,status_code",
    [
        (NotFoundError("Asset not found"), 404),
        (ConflictError("Asset conflict"), 409),
        (ValidationError("Asset validation failed"), 422),
    ],
)
def test_get_asset_maps_domain_errors(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
    exception,
    status_code,
):
    monkeypatch.setattr(
        asset_routes,
        "get_asset",
        Mock(
            side_effect=exception,
        ),
    )

    response = client.get(
        "/api/assets/1",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
    )

    assert response.status_code == status_code

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == str(exception)


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
            ),
        ),
    )

    response = client.get(
        "/api/assets/1",
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


# =============================================================================
# RESPONSE / ENUM SERIALIZATION
# =============================================================================


def test_response_serializes_enum_values(
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
        f"/api/assets/{asset.id}",
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
# SERVICE INVOCATION CONTRACT
# =============================================================================


def test_create_asset_passes_schema_object_to_service(
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
        "/api/assets",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "asset_tag": "AST-CONTRACT-001",
            "name": "Contract Asset",
            "category": "medical_device",
            "condition": "excellent",
            "ownership": "donated",
            "location": "ICU",
            "purchase_cost": "1000.00",
        },
    )

    assert response.status_code == 201

    data = service.call_args.kwargs["data"]

    assert isinstance(
        data,
        AssetCreateSchema,
    )

    assert data.asset_tag == (
        "AST-CONTRACT-001"
    )
    assert data.category == (
        AssetCategory.MEDICAL_DEVICE
    )
    assert data.condition == (
        AssetCondition.EXCELLENT
    )
    assert data.ownership == (
        AssetOwnership.DONATED
    )
    assert data.purchase_cost == (
        Decimal("1000.00")
    )


def test_update_asset_passes_schema_object_to_service(
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
        f"/api/assets/{asset.id}",
        headers=auth_headers_for(
            user,
            role=Role.ADMIN,
        ),
        json={
            "name": "Contract Updated",
            "category": "computer",
        },
    )

    assert response.status_code == 200

    data = service.call_args.kwargs["data"]

    assert isinstance(
        data,
        AssetUpdateSchema,
    )

    assert data.name == "Contract Updated"
    assert data.category == (
        AssetCategory.COMPUTER
    )


def test_list_asset_query_passes_schema_object(
    client,
    user,
    auth_headers_for,
    monkeypatch,
    asset_routes,
):
    service = Mock(
        return_value={
            "items": [],
            "page": 1,
            "per_page": 20,
            "total": 0,
            "pages": 0,
            "has_next": False,
            "has_prev": False,
        }
    )

    monkeypatch.setattr(
        asset_routes,
        "list_assets",
        service,
    )

    response = client.get(
        "/api/assets"
        "?page=1"
        "&per_page=20"
        "&category=computer"
        "&is_active=true",
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
    assert query.page == 1
    assert query.per_page == 20
    assert query.category == (
        AssetCategory.COMPUTER
    )
    assert query.is_active is True