from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.enums.inventory_enums import (
    InventoryCategory,
    InventoryTransferStatus,
    StockMovementDirection,
    StockMovementType,
)
from app.core.enums.role_enums import Role


@pytest.fixture
def inventory_routes():
    import app.modules.inventory.routes.inventory_route as routes
    return routes


@pytest.fixture
def inventory_admin_context(make_authenticated_staff, clinic):
    """Create an authenticated ADMIN user linked to a Staff record."""
    return make_authenticated_staff(clinic, Role.ADMIN)


@pytest.fixture
def inventory_admin_headers(inventory_admin_context):
    """Headers for an authenticated ADMIN staff user."""
    _, headers = inventory_admin_context
    return headers


@pytest.fixture
def inventory_admin_staff(inventory_admin_context):
    """Staff record corresponding to inventory_admin_headers."""
    staff, _ = inventory_admin_context
    return staff


@pytest.fixture
def pharmacist_headers(make_authenticated_staff, clinic):
    """Headers for an authenticated PHARMACIST staff user."""
    _, headers = make_authenticated_staff(clinic, Role.PHARMACIST)
    return headers


def item(**overrides):
    values = dict(id=1, clinic_id=1, name="Gloves", category=InventoryCategory.MEDICAL_SUPPLY,
                  sku="SKU-1", barcode="BAR-1", unit="box", quantity_on_hand=10,
                  reorder_level=5, is_active=True, created_at=datetime.now(timezone.utc),
                  updated_at=datetime.now(timezone.utc))
    values.update(overrides)
    return SimpleNamespace(**values)


def supplier(**overrides):
    values = dict(id=1, clinic_id=1, name="Supplier One", contact_person="John",
                  phone="08000000000", email="supplier@example.com", address="Address",
                  is_active=True, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    values.update(overrides)
    return SimpleNamespace(**values)


def batch(**overrides):
    values = dict(id=1, item_id=1, supplier_id=None, batch_number="BATCH-1", quantity_on_hand=10,
                  unit_cost=Decimal("12.50"), expiry_date=date.today(), received_at=datetime.now(timezone.utc),
                  is_active=True, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    values.update(overrides)
    return SimpleNamespace(**values)


def movement(**overrides):
    values = dict(id=1, item_id=1, batch_id=None, movement_type=StockMovementType.RESTOCK,
                  direction=StockMovementDirection.IN, quantity=5, reason="Restock",
                  performed_by_id=1, reference_type=None, reference_id=None,
                  created_at=datetime.now(timezone.utc))
    values.update(overrides)
    return SimpleNamespace(**values)


def transfer(**overrides):
    values = dict(id=1, item_id=1, batch_id=None, source_clinic_id=1,
                  destination_clinic_id=2, quantity=5, status=InventoryTransferStatus.PENDING,
                  reason="Transfer", requested_by_id=1, approved_by_id=None,
                  requested_at=datetime.now(timezone.utc), approved_at=None,
                  completed_at=None, cancelled_at=None, created_at=datetime.now(timezone.utc),
                  updated_at=datetime.now(timezone.utc))
    values.update(overrides)
    return SimpleNamespace(**values)


# ============================================================================
# AUTH / HELPERS
# ============================================================================

def test_endpoints_require_auth(client):
    response = client.get("/api/inventory/items")
    assert response.status_code in (401, 422)


def test_current_staff_uses_authenticated_user(
    inventory_routes,
    staff,
    monkeypatch,
):
    monkeypatch.setattr(
        inventory_routes,
        "_get_current_user",
        Mock(return_value=staff.user),
    )
    assert inventory_routes._get_current_staff_id() == staff.id


# ============================================================================
# ITEMS
# ============================================================================

def test_list_items_success(client, inventory_admin_headers, monkeypatch, inventory_routes):
    monkeypatch.setattr(inventory_routes, "list_inventory_items", Mock(return_value=[item()]))
    response = client.get("/api/inventory/items", headers=inventory_admin_headers)
    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"][0]["id"] == 1


def test_list_items_forwards_filters(client, inventory_admin_headers, monkeypatch, inventory_routes):
    service = Mock(return_value=[])
    monkeypatch.setattr(inventory_routes, "list_inventory_items", service)
    response = client.get(
        "/api/inventory/items?category=medical_supply&low_stock_only=true&include_inactive=true",
        headers=inventory_admin_headers,
    )
    assert response.status_code == 200
    assert service.call_args.kwargs["low_stock_only"] is True
    assert service.call_args.kwargs["include_inactive"] is True


def test_list_items_rejects_unknown_query_parameter(client, inventory_admin_headers):
    response = client.get("/api/inventory/items?unknown=x", headers=inventory_admin_headers)
    assert response.status_code == 400


def test_get_item_success(client, inventory_admin_headers, monkeypatch, inventory_routes):
    monkeypatch.setattr(inventory_routes, "get_inventory_item", Mock(return_value=item()))
    response = client.get("/api/inventory/items/1", headers=inventory_admin_headers)
    assert response.status_code == 200
    assert response.get_json()["data"]["name"] == "Gloves"


def test_get_item_not_found(client, inventory_admin_headers, monkeypatch, inventory_routes):
    from app.core.exceptions import NotFoundError
    monkeypatch.setattr(inventory_routes, "get_inventory_item", Mock(side_effect=NotFoundError("missing")))
    response = client.get("/api/inventory/items/1", headers=inventory_admin_headers)
    assert response.status_code == 404


def test_create_item_uses_jwt_clinic_and_staff(
    client, inventory_admin_headers, inventory_admin_staff, monkeypatch, inventory_routes
):
    service = Mock(return_value=item())
    monkeypatch.setattr(inventory_routes, "create_inventory_item", service)
    response = client.post(
        "/api/inventory/items",
        headers=inventory_admin_headers,
        json={"clinic_id": 999, "name": "Gloves", "initial_quantity": 2, "performed_by_id": 99999},
    )
    assert response.status_code == 201
    assert service.call_args.kwargs["clinic_id"] == inventory_admin_staff.clinic_id
    assert service.call_args.kwargs["performed_by_id"] == inventory_admin_staff.id


def test_create_item_validation_error(client, inventory_admin_headers):
    response = client.post("/api/inventory/items", headers=inventory_admin_headers, json={"name": ""})
    assert response.status_code == 400


def test_update_item_success(client, inventory_admin_headers, monkeypatch, inventory_routes):
    service = Mock(return_value=item(name="New"))
    monkeypatch.setattr(inventory_routes, "update_inventory_item", service)
    response = client.patch("/api/inventory/items/1", headers=inventory_admin_headers, json={"name": "New"})
    assert response.status_code == 200
    assert service.call_args.kwargs["name"] == "New"


@pytest.mark.parametrize("path", [
    "/api/inventory/items/1/deactivate",
    "/api/inventory/items/1/reactivate",
])
def test_item_status_is_admin_only(client, pharmacist_headers, path):
    response = client.post(path, headers=pharmacist_headers)
    assert response.status_code == 403


# ============================================================================
# BATCHES
# ============================================================================

def test_list_batches_success(client, inventory_admin_headers, monkeypatch, inventory_routes):
    monkeypatch.setattr(inventory_routes, "list_inventory_batches", Mock(return_value=[batch()]))
    response = client.get("/api/inventory/items/1/batches", headers=inventory_admin_headers)
    assert response.status_code == 200
    assert response.get_json()["data"][0]["batch_number"] == "BATCH-1"


def test_get_batch_success(client, inventory_admin_headers, monkeypatch, inventory_routes):
    monkeypatch.setattr(inventory_routes, "get_inventory_batch", Mock(return_value=batch()))
    response = client.get("/api/inventory/batches/1", headers=inventory_admin_headers)
    assert response.status_code == 200


def test_create_batch_forces_jwt_clinic(client, inventory_admin_headers, monkeypatch, inventory_routes):
    service = Mock(return_value=batch())
    monkeypatch.setattr(inventory_routes, "create_inventory_batch", service)
    response = client.post(
        "/api/inventory/batches",
        headers=inventory_admin_headers,
        json={"item_id": 1, "batch_number": "BATCH-1", "clinic_id": 999},
    )
    assert response.status_code == 201
    assert service.call_args.kwargs["clinic_id"] is not None


def test_create_batch_rejects_past_expiry(client, inventory_admin_headers):
    response = client.post(
        "/api/inventory/batches",
        headers=inventory_admin_headers,
        json={"item_id": 1, "batch_number": "BATCH-1", "expiry_date": "2000-01-01"},
    )
    assert response.status_code == 400


def test_expiring_batches_forwards_days(client, inventory_admin_headers, monkeypatch, inventory_routes):
    service = Mock(return_value=[])
    monkeypatch.setattr(inventory_routes, "list_expiring_inventory_batches", service)
    response = client.get("/api/inventory/batches/expiring?days=15", headers=inventory_admin_headers)
    assert response.status_code == 200
    assert service.call_args.kwargs["days"] == 15


# ============================================================================
# MOVEMENTS
# ============================================================================

def test_list_movements_success(client, inventory_admin_headers, monkeypatch, inventory_routes):
    monkeypatch.setattr(inventory_routes, "get_stock_movements", Mock(return_value=[movement()]))
    response = client.get("/api/inventory/items/1/movements", headers=inventory_admin_headers)
    assert response.status_code == 200
    assert response.get_json()["data"][0]["quantity"] == 5


def test_create_movement_uses_jwt_actor(client, inventory_admin_headers, inventory_admin_staff, monkeypatch, inventory_routes):
    service = Mock(return_value=movement())
    monkeypatch.setattr(inventory_routes, "record_stock_movement", service)
    response = client.post(
        "/api/inventory/movements",
        headers=inventory_admin_headers,
        json={"item_id": 1, "movement_type": "restock", "quantity": 5,
              "performed_by_id": 99999, "clinic_id": 999},
    )
    assert response.status_code == 201
    assert service.call_args.kwargs["performed_by_id"] == inventory_admin_staff.id
    assert service.call_args.kwargs["clinic_id"] == inventory_admin_staff.clinic_id


def test_movement_rejects_zero_for_normal_movement(client, inventory_admin_headers):
    response = client.post(
        "/api/inventory/movements",
        headers=inventory_admin_headers,
        json={"item_id": 1, "movement_type": "restock", "quantity": 0, "performed_by_id": 1},
    )
    assert response.status_code == 400


# ============================================================================
# SUPPLIERS
# ============================================================================

def test_list_suppliers_success(client, inventory_admin_headers, monkeypatch, inventory_routes):
    monkeypatch.setattr(inventory_routes, "list_suppliers", Mock(return_value=[supplier()]))
    response = client.get("/api/inventory/suppliers", headers=inventory_admin_headers)
    assert response.status_code == 200
    assert response.get_json()["data"][0]["name"] == "Supplier One"


def test_create_supplier_defaults_to_authenticated_clinic(client, inventory_admin_headers, inventory_admin_staff, monkeypatch, inventory_routes):
    service = Mock(return_value=supplier())
    monkeypatch.setattr(inventory_routes, "create_supplier", service)
    response = client.post("/api/inventory/suppliers", headers=inventory_admin_headers, json={"name": "Supplier One"})
    assert response.status_code == 201
    assert service.call_args.kwargs["clinic_id"] == inventory_admin_staff.clinic_id


def test_create_global_supplier_allowed_for_admin(client, inventory_admin_headers, monkeypatch, inventory_routes):
    monkeypatch.setattr(inventory_routes, "create_supplier", Mock(return_value=supplier(clinic_id=None)))
    response = client.post("/api/inventory/suppliers", headers=inventory_admin_headers, json={"name": "Global Supplier", "clinic_id": None})
    assert response.status_code == 201
    assert inventory_routes.create_supplier.call_args.kwargs["clinic_id"] is None


def test_create_global_supplier_rejected_for_pharmacist(client, make_authenticated_staff, clinic):
    _, headers = make_authenticated_staff(clinic, Role.PHARMACIST)
    response = client.post("/api/inventory/suppliers", headers=headers, json={"name": "Global Supplier", "clinic_id": None})
    assert response.status_code == 400


def test_supplier_update_is_admin_only(client, pharmacist_headers):
    response = client.patch("/api/inventory/suppliers/1", headers=pharmacist_headers, json={"name": "New"})
    assert response.status_code == 403


# ============================================================================
# TRANSFERS
# ============================================================================

def test_list_transfers_success(client, inventory_admin_headers, monkeypatch, inventory_routes):
    monkeypatch.setattr(inventory_routes, "list_inventory_transfers", Mock(return_value=[transfer()]))
    response = client.get("/api/inventory/transfers", headers=inventory_admin_headers)
    assert response.status_code == 200
    assert response.get_json()["data"][0]["id"] == 1


def test_list_transfers_forwards_status(client, inventory_admin_headers, monkeypatch, inventory_routes):
    service = Mock(return_value=[])
    monkeypatch.setattr(inventory_routes, "list_inventory_transfers", service)
    response = client.get("/api/inventory/transfers?status=pending", headers=inventory_admin_headers)
    assert response.status_code == 200
    assert service.call_args.kwargs["status"] == InventoryTransferStatus.PENDING


def test_create_transfer_rejects_foreign_source_clinic(client, inventory_admin_headers, monkeypatch, inventory_routes):
    service = Mock()
    monkeypatch.setattr(inventory_routes, "create_inventory_transfer", service)
    response = client.post(
        "/api/inventory/transfers",
        headers=inventory_admin_headers,
        json={"item_id": 1, "source_clinic_id": 999, "destination_clinic_id": 2, "quantity": 5, "requested_by_id": 999},
    )
    assert response.status_code == 400
    service.assert_not_called()


def test_create_transfer_uses_jwt_requester(client, inventory_admin_headers, inventory_admin_staff, monkeypatch, inventory_routes):
    service = Mock(return_value=transfer())
    monkeypatch.setattr(inventory_routes, "create_inventory_transfer", service)
    response = client.post(
        "/api/inventory/transfers",
        headers=inventory_admin_headers,
        json={"item_id": 1, "source_clinic_id": inventory_admin_staff.clinic_id,
              "destination_clinic_id": inventory_admin_staff.clinic_id + 1, "quantity": 5, "requested_by_id": 999},
    )
    assert response.status_code == 201
    assert service.call_args.kwargs["requested_by_id"] == inventory_admin_staff.id


def test_approve_transfer_ignores_body_actor(client, inventory_admin_headers, inventory_admin_staff, monkeypatch, inventory_routes):
    service = Mock(return_value=transfer(status=InventoryTransferStatus.APPROVED, approved_by_id=inventory_admin_staff.id))
    monkeypatch.setattr(inventory_routes, "approve_inventory_transfer", service)
    response = client.post("/api/inventory/transfers/1/approve", headers=inventory_admin_headers, json={"approved_by_id": 999999})
    assert response.status_code == 200
    assert service.call_args.kwargs["approved_by_id"] == inventory_admin_staff.id


def test_complete_transfer_ignores_body_actor(client, inventory_admin_headers, inventory_admin_staff, monkeypatch, inventory_routes):
    service = Mock(return_value=transfer(status=InventoryTransferStatus.COMPLETED))
    monkeypatch.setattr(inventory_routes, "complete_inventory_transfer", service)
    response = client.post("/api/inventory/transfers/1/complete", headers=inventory_admin_headers, json={"performed_by_id": 999999})
    assert response.status_code == 200
    assert service.call_args.kwargs["performed_by_id"] == inventory_admin_staff.id


def test_cancel_transfer_uses_jwt_actor(client, inventory_admin_headers, inventory_admin_staff, monkeypatch, inventory_routes):
    service = Mock(return_value=transfer(status=InventoryTransferStatus.CANCELLED))
    monkeypatch.setattr(inventory_routes, "cancel_inventory_transfer", service)
    response = client.post(
        "/api/inventory/transfers/1/cancel",
        headers=inventory_admin_headers,
        json={"cancelled_by_id": 999999, "reason": "Not needed"},
    )
    assert response.status_code == 200
    assert service.call_args.kwargs["cancelled_by_id"] == inventory_admin_staff.id
    assert service.call_args.kwargs["reason"] == "Not needed"


# ============================================================================
# ERROR TRANSLATION
# ============================================================================

@pytest.mark.parametrize("exc,status", [
    ("notfound", 404),
    ("conflict", 409),
    ("validation", 400),
])
def test_service_errors_are_mapped(client, inventory_admin_headers, monkeypatch, inventory_routes, exc, status):
    from app.core.exceptions import ConflictError, NotFoundError, ValidationError
    classes = {"notfound": NotFoundError, "conflict": ConflictError, "validation": ValidationError}
    monkeypatch.setattr(inventory_routes, "get_inventory_item", Mock(side_effect=classes[exc]("boom")))
    response = client.get("/api/inventory/items/1", headers=inventory_admin_headers)
    assert response.status_code == status
    assert response.get_json()["error"] == "boom"
