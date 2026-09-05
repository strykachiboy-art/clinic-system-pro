from __future__ import annotations

from datetime import date, timedelta
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
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.extensions import db as _db
from app.modules.inventory.models.inventory_model import (
    InventoryBatch,
    InventoryItem,
    InventorySupplier,
)
from app.modules.inventory.routes import inventory_route as inventory_routes


# ============================================================================
# HELPERS
# ============================================================================


def response_json(response):
    body = response.get_json()
    assert body is not None, response.data
    return body


def assert_error(response, status_code, message=None):
    assert response.status_code == status_code, response.get_json()

    body = response_json(response)
    assert "error" in body

    if message is not None:
        assert message in body["error"]

    return body


# ============================================================================
# INVENTORY FIXTURES
# ============================================================================


@pytest.fixture()
def inventory_item(db, clinic):
    item = InventoryItem(
        clinic_id=clinic.id,
        name="Paracetamol",
        category=InventoryCategory.MEDICAL_SUPPLY,
        sku="PAR-001",
        barcode="123456789",
        unit="box",
        quantity_on_hand=25,
        reorder_level=10,
        is_active=True,
    )
    db.session.add(item)
    db.session.commit()
    return item


@pytest.fixture()
def low_stock_item(db, clinic):
    item = InventoryItem(
        clinic_id=clinic.id,
        name="Low Stock Syringes",
        category=InventoryCategory.CONSUMABLE,
        sku="SYR-001",
        unit="box",
        quantity_on_hand=2,
        reorder_level=10,
        is_active=True,
    )
    db.session.add(item)
    db.session.commit()
    return item


@pytest.fixture()
def inactive_inventory_item(db, clinic):
    item = InventoryItem(
        clinic_id=clinic.id,
        name="Inactive Item",
        category=InventoryCategory.MEDICAL_SUPPLY,
        sku="INA-001",
        unit="box",
        quantity_on_hand=10,
        reorder_level=5,
        is_active=False,
    )
    db.session.add(item)
    db.session.commit()
    return item


@pytest.fixture()
def inventory_supplier(db, clinic):
    supplier = InventorySupplier(
        clinic_id=clinic.id,
        name="MediSupply Ltd",
        contact_person="John Supplier",
        phone="08012345678",
        email="supplier@example.com",
        address="Port Harcourt",
        is_active=True,
    )
    db.session.add(supplier)
    db.session.commit()
    return supplier


@pytest.fixture()
def inactive_inventory_supplier(db, clinic):
    supplier = InventorySupplier(
        clinic_id=clinic.id,
        name="Inactive Supplier",
        contact_person="Jane Supplier",
        phone="08087654321",
        email="inactive@example.com",
        address="Port Harcourt",
        is_active=False,
    )
    db.session.add(supplier)
    db.session.commit()
    return supplier


@pytest.fixture()
def inventory_batch(db, inventory_item, inventory_supplier):
    batch = InventoryBatch(
        item_id=inventory_item.id,
        supplier_id=inventory_supplier.id,
        batch_number="BATCH-001",
        quantity_on_hand=25,
        unit_cost=Decimal("150.00"),
        expiry_date=date.today() + timedelta(days=60),
        is_active=True,
    )
    db.session.add(batch)
    db.session.commit()
    return batch


@pytest.fixture()
def second_inventory_batch(db, inventory_item):
    batch = InventoryBatch(
        item_id=inventory_item.id,
        batch_number="BATCH-002",
        quantity_on_hand=10,
        unit_cost=Decimal("175.00"),
        expiry_date=date.today() + timedelta(days=120),
        is_active=True,
    )
    db.session.add(batch)
    db.session.commit()
    return batch


@pytest.fixture()
def inactive_inventory_batch(db, inventory_item):
    batch = InventoryBatch(
        item_id=inventory_item.id,
        batch_number="BATCH-INACTIVE",
        quantity_on_hand=5,
        unit_cost=Decimal("100.00"),
        expiry_date=date.today() + timedelta(days=90),
        is_active=False,
    )
    db.session.add(batch)
    db.session.commit()
    return batch


@pytest.fixture()
def pharmacist(make_authenticated_staff, clinic):
    return make_authenticated_staff(
        clinic,
        Role.PHARMACIST,
        first_name="Pharmacist",
        last_name="User",
    )


@pytest.fixture()
def suspended_staff(make_staff, clinic):
    return make_staff(
        clinic,
        role=Role.PHARMACIST,
        status=StaffStatus.SUSPENDED,
    )


# ============================================================================
# AUTHORIZATION
# ============================================================================


class TestInventoryAuthorization:

    def test_items_requires_authentication(self, client):
        response = client.get("/api/inventory/items?clinic_id=1")

        assert response.status_code in (401, 422)

    def test_items_rejects_unauthorized_role(
        self,
        client,
        make_user,
        clinic,
        auth_headers_for,
    ):
        user = make_user(clinic, role=Role.PATIENT)

        response = client.get(
            f"/api/inventory/items?clinic_id={clinic.id}",
            headers=auth_headers_for(user, role=Role.PATIENT),
        )

        assert response.status_code == 403

    def test_admin_can_access_items(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        response = client.get(
            f"/api/inventory/items?clinic_id={clinic.id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 200

    def test_pharmacist_can_access_items(
        self,
        client,
        pharmacist,
        clinic,
    ):
        _, headers = pharmacist

        response = client.get(
            f"/api/inventory/items?clinic_id={clinic.id}",
            headers=headers,
        )

        assert response.status_code == 200

    def test_admin_only_item_deactivation_rejects_pharmacist(
        self,
        client,
        pharmacist,
        inventory_item,
    ):
        _, headers = pharmacist

        response = client.post(
            f"/api/inventory/items/{inventory_item.id}/deactivate"
            f"?clinic_id={inventory_item.clinic_id}",
            headers=headers,
        )

        assert response.status_code == 403

    def test_admin_only_item_reactivation_rejects_pharmacist(
        self,
        client,
        pharmacist,
        inventory_item,
    ):
        _, headers = pharmacist

        response = client.post(
            f"/api/inventory/items/{inventory_item.id}/reactivate"
            f"?clinic_id={inventory_item.clinic_id}",
            headers=headers,
        )

        assert response.status_code == 403

    def test_admin_only_supplier_update_rejects_pharmacist(
        self,
        client,
        pharmacist,
        inventory_supplier,
    ):
        _, headers = pharmacist

        response = client.patch(
            f"/api/inventory/suppliers/{inventory_supplier.id}"
            f"?clinic_id={inventory_supplier.clinic_id}",
            headers=headers,
            json={"name": "Updated Supplier"},
        )

        assert response.status_code == 403

    def test_admin_only_supplier_deactivation_rejects_pharmacist(
        self,
        client,
        pharmacist,
        inventory_supplier,
    ):
        _, headers = pharmacist

        response = client.post(
            f"/api/inventory/suppliers/{inventory_supplier.id}/deactivate"
            f"?clinic_id={inventory_supplier.clinic_id}",
            headers=headers,
        )

        assert response.status_code == 403

    def test_admin_only_supplier_reactivation_rejects_pharmacist(
        self,
        client,
        pharmacist,
        inactive_inventory_supplier,
    ):
        _, headers = pharmacist

        response = client.post(
            f"/api/inventory/suppliers/{inactive_inventory_supplier.id}/reactivate"
            f"?clinic_id={inactive_inventory_supplier.clinic_id}",
            headers=headers,
        )

        assert response.status_code == 403


# ============================================================================
# INVENTORY ITEMS
# ============================================================================


class TestListInventoryItemsRoute:

    def test_returns_items(
        self,
        client,
        user,
        inventory_item,
        auth_headers_for,
    ):
        response = client.get(
            f"/api/inventory/items?clinic_id={inventory_item.clinic_id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 200, response.get_json()

        body = response_json(response)

        assert body["success"] is True
        assert len(body["data"]) == 1
        assert body["data"][0]["id"] == inventory_item.id
        assert body["data"][0]["name"] == "Paracetamol"

    def test_requires_clinic_id(
        self,
        client,
        user,
        auth_headers_for,
    ):
        response = client.get(
            "/api/inventory/items",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert_error(response, 400, "clinic_id")

    @pytest.mark.parametrize(
        "clinic_id",
        ["abc", "0", "-1"],
    )
    def test_rejects_invalid_clinic_id(
        self,
        client,
        user,
        auth_headers_for,
        clinic_id,
    ):
        response = client.get(
            f"/api/inventory/items?clinic_id={clinic_id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 400


class TestLowStockItemsRoute:

    def test_returns_low_stock_items(
        self,
        client,
        user,
        low_stock_item,
        auth_headers_for,
    ):
        response = client.get(
            f"/api/inventory/items/low-stock"
            f"?clinic_id={low_stock_item.clinic_id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 200, response.get_json()

        body = response_json(response)

        assert body["success"] is True
        assert any(
            item["id"] == low_stock_item.id
            for item in body["data"]
        )

    def test_requires_clinic_id(
        self,
        client,
        user,
        auth_headers_for,
    ):
        response = client.get(
            "/api/inventory/items/low-stock",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert_error(response, 400, "clinic_id")


class TestGetInventoryItemRoute:

    def test_returns_item(
        self,
        client,
        user,
        inventory_item,
        auth_headers_for,
    ):
        response = client.get(
            f"/api/inventory/items/{inventory_item.id}"
            f"?clinic_id={inventory_item.clinic_id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 200

        body = response_json(response)

        assert body["success"] is True
        assert body["data"]["id"] == inventory_item.id

    def test_allows_missing_optional_clinic_id(
        self,
        client,
        user,
        inventory_item,
        auth_headers_for,
    ):
        response = client.get(
            f"/api/inventory/items/{inventory_item.id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 200

    def test_rejects_invalid_optional_clinic_id(
        self,
        client,
        user,
        inventory_item,
        auth_headers_for,
    ):
        response = client.get(
            f"/api/inventory/items/{inventory_item.id}?clinic_id=abc",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 400

    def test_returns_404_for_missing_item(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        response = client.get(
            f"/api/inventory/items/999999?clinic_id={clinic.id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert_error(response, 404)


class TestCreateInventoryItemRoute:

    def test_creates_item(
        self,
        client,
        user,
        staff,
        clinic,
        auth_headers_for,
    ):
        response = client.post(
            "/api/inventory/items",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json={
                "clinic_id": clinic.id,
                "name": "Amoxicillin",
                "category": InventoryCategory.MEDICAL_SUPPLY.value,
                "sku": "AMX-001",
                "unit": "box",
                "initial_quantity": 20,
                "reorder_level": 5,
                "performed_by_id": staff.id,
            },
        )

        assert response.status_code == 201, response.get_json()

        body = response_json(response)

        assert body["success"] is True
        assert body["data"]["clinic_id"] == clinic.id
        assert body["data"]["name"] == "Amoxicillin"

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"clinic_id": 0, "name": "Test"},
            {"clinic_id": 1},
            {"clinic_id": 1, "name": ""},
            {"clinic_id": 1, "name": "   "},
        ],
    )
    def test_rejects_invalid_payload(
        self,
        client,
        user,
        auth_headers_for,
        payload,
    ):
        response = client.post(
            "/api/inventory/items",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json=payload,
        )

        assert response.status_code == 400

    def test_rejects_unknown_field(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        response = client.post(
            "/api/inventory/items",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json={
                "clinic_id": clinic.id,
                "name": "Test Item",
                "unknown_field": "bad",
            },
        )

        assert response.status_code == 400

    def test_rejects_non_object_json(
        self,
        client,
        user,
        auth_headers_for,
    ):
        response = client.post(
            "/api/inventory/items",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json=["not", "an", "object"],
        )

        assert response.status_code == 400


class TestUpdateInventoryItemRoute:

    def test_updates_item(
        self,
        client,
        user,
        inventory_item,
        auth_headers_for,
    ):
        response = client.patch(
            f"/api/inventory/items/{inventory_item.id}"
            f"?clinic_id={inventory_item.clinic_id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json={
                "name": "Updated Paracetamol",
                "reorder_level": 15,
            },
        )

        assert response.status_code == 200, response.get_json()

        body = response_json(response)

        assert body["success"] is True
        assert body["data"]["name"] == "Updated Paracetamol"
        assert body["data"]["reorder_level"] == 15

    def test_requires_clinic_id(
        self,
        client,
        user,
        inventory_item,
        auth_headers_for,
    ):
        response = client.patch(
            f"/api/inventory/items/{inventory_item.id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json={"name": "Updated"},
        )

        assert_error(response, 400, "clinic_id")

    def test_rejects_invalid_payload(
        self,
        client,
        user,
        inventory_item,
        auth_headers_for,
    ):
        response = client.patch(
            f"/api/inventory/items/{inventory_item.id}"
            f"?clinic_id={inventory_item.clinic_id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json={"name": ""},
        )

        assert response.status_code == 400


class TestDeactivateReactivateInventoryItemRoute:

    def test_deactivates_item(
        self,
        client,
        user,
        inventory_item,
        auth_headers_for,
    ):
        response = client.post(
            f"/api/inventory/items/{inventory_item.id}/deactivate"
            f"?clinic_id={inventory_item.clinic_id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 200, response.get_json()

        body = response_json(response)

        assert body["success"] is True
        assert body["data"]["is_active"] is False

    def test_reactivates_item(
        self,
        client,
        user,
        inactive_inventory_item,
        auth_headers_for,
    ):
        response = client.post(
            f"/api/inventory/items/{inactive_inventory_item.id}/reactivate"
            f"?clinic_id={inactive_inventory_item.clinic_id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 200, response.get_json()

        body = response_json(response)

        assert body["success"] is True
        assert body["data"]["is_active"] is True

    @pytest.mark.parametrize(
        "endpoint",
        ["deactivate", "reactivate"],
    )
    def test_requires_clinic_id(
        self,
        client,
        user,
        inventory_item,
        auth_headers_for,
        endpoint,
    ):
        response = client.post(
            f"/api/inventory/items/{inventory_item.id}/{endpoint}",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert_error(response, 400, "clinic_id")


# ============================================================================
# BATCHES
# ============================================================================


class TestListInventoryBatchesRoute:

    def test_returns_batches(
        self,
        client,
        user,
        inventory_item,
        inventory_batch,
        auth_headers_for,
    ):
        response = client.get(
            f"/api/inventory/items/{inventory_item.id}/batches"
            f"?clinic_id={inventory_item.clinic_id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 200, response.get_json()

        body = response_json(response)

        assert body["success"] is True
        assert any(
            batch["id"] == inventory_batch.id
            for batch in body["data"]
        )

    def test_requires_clinic_id(
        self,
        client,
        user,
        inventory_item,
        auth_headers_for,
    ):
        response = client.get(
            f"/api/inventory/items/{inventory_item.id}/batches",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert_error(response, 400, "clinic_id")


class TestGetInventoryBatchRoute:

    def test_returns_batch(
        self,
        client,
        user,
        inventory_batch,
        auth_headers_for,
    ):
        response = client.get(
            f"/api/inventory/batches/{inventory_batch.id}"
            f"?clinic_id={inventory_batch.item.clinic_id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 200

        body = response_json(response)

        assert body["success"] is True
        assert body["data"]["id"] == inventory_batch.id

    def test_allows_missing_optional_clinic_id(
        self,
        client,
        user,
        inventory_batch,
        auth_headers_for,
    ):
        response = client.get(
            f"/api/inventory/batches/{inventory_batch.id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 200


class TestCreateInventoryBatchRoute:

    def test_creates_batch(
        self,
        client,
        user,
        clinic,
        inventory_item,
        inventory_supplier,
        auth_headers_for,
    ):
        response = client.post(
            "/api/inventory/batches",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json={
                "clinic_id": clinic.id,
                "item_id": inventory_item.id,
                "supplier_id": inventory_supplier.id,
                "batch_number": "NEW-BATCH-001",
                "unit_cost": "125.50",
                "expiry_date": (
                    date.today() + timedelta(days=90)
                ).isoformat(),
            },
        )

        assert response.status_code == 201, response.get_json()

        body = response_json(response)

        assert body["success"] is True
        assert body["data"]["item_id"] == inventory_item.id
        assert body["data"]["batch_number"] == "NEW-BATCH-001"

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"item_id": 0, "batch_number": "B-1", "unit_cost": "10"},
            {"item_id": 1, "batch_number": "", "unit_cost": "10"},
            {"item_id": 1, "batch_number": "B-1", "unit_cost": "-1"},
        ],
    )
    def test_rejects_invalid_payload(
        self,
        client,
        user,
        auth_headers_for,
        payload,
    ):
        response = client.post(
            "/api/inventory/batches",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json=payload,
        )

        assert response.status_code == 400


class TestUpdateInventoryBatchRoute:

    def test_updates_batch(
        self,
        client,
        user,
        inventory_batch,
        auth_headers_for,
    ):
        clinic_id = inventory_batch.item.clinic_id

        response = client.patch(
            f"/api/inventory/batches/{inventory_batch.id}"
            f"?clinic_id={clinic_id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json={
                "batch_number": "UPDATED-BATCH",
                "unit_cost": "200.00",
            },
        )

        assert response.status_code == 200, response.get_json()

        body = response_json(response)

        assert body["success"] is True
        assert body["data"]["batch_number"] == "UPDATED-BATCH"

    def test_requires_clinic_id(
        self,
        client,
        user,
        inventory_batch,
        auth_headers_for,
    ):
        response = client.patch(
            f"/api/inventory/batches/{inventory_batch.id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json={"batch_number": "UPDATED"},
        )

        assert_error(response, 400, "clinic_id")


class TestExpiringInventoryBatchesRoute:

    def test_returns_expiring_batches(
        self,
        client,
        user,
        inventory_batch,
        auth_headers_for,
    ):
        clinic_id = inventory_batch.item.clinic_id

        response = client.get(
            f"/api/inventory/batches/expiring"
            f"?clinic_id={clinic_id}&days=90",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 200, response.get_json()

        body = response_json(response)

        assert body["success"] is True
        assert any(
            batch["id"] == inventory_batch.id
            for batch in body["data"]
        )

    def test_requires_clinic_id(
        self,
        client,
        user,
        auth_headers_for,
    ):
        response = client.get(
            "/api/inventory/batches/expiring",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert_error(response, 400, "clinic_id")

    def test_rejects_negative_days(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        response = client.get(
            f"/api/inventory/batches/expiring"
            f"?clinic_id={clinic.id}&days=-1",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 400


# ============================================================================
# STOCK MOVEMENTS
# ============================================================================


class TestListStockMovementsRoute:

    def test_returns_movements(
        self,
        client,
        user,
        staff,
        inventory_item,
        auth_headers_for,
        monkeypatch,
    ):
        movement = SimpleNamespace(
            id=1,
            item_id=inventory_item.id,
            batch_id=None,
            movement_type=StockMovementType.RESTOCK,
            direction=StockMovementDirection.IN,
            quantity=10,
            reason="Initial restock",
            reference_type="TEST",
            reference_id=1,
            performed_by_id=staff.id,
            created_at=None,
        )

        monkeypatch.setattr(
            inventory_routes,
            "get_stock_movements",
            Mock(return_value=[movement]),
        )

        response = client.get(
            f"/api/inventory/items/{inventory_item.id}/movements"
            f"?clinic_id={inventory_item.clinic_id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 200, response.get_json()

        body = response_json(response)

        assert body["success"] is True
        assert body["data"][0]["item_id"] == inventory_item.id

    def test_requires_clinic_id(
        self,
        client,
        user,
        inventory_item,
        auth_headers_for,
    ):
        response = client.get(
            f"/api/inventory/items/{inventory_item.id}/movements",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert_error(response, 400, "clinic_id")


class TestCreateStockMovementRoute:

    def test_creates_movement(
        self,
        client,
        user,
        staff,
        inventory_item,
        auth_headers_for,
        monkeypatch,
    ):
        movement = SimpleNamespace(
            id=1,
            item_id=inventory_item.id,
            batch_id=None,
            movement_type=StockMovementType.RESTOCK,
            direction=StockMovementDirection.IN,
            quantity=10,
            reason="Restock",
            reference_type="RESTOCK",
            reference_id=1,
            performed_by_id=staff.id,
            created_at=None,
        )

        service = Mock(return_value=movement)

        monkeypatch.setattr(
            inventory_routes,
            "record_stock_movement",
            service,
        )

        response = client.post(
            "/api/inventory/movements",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json={
                "item_id": inventory_item.id,
                "movement_type": StockMovementType.RESTOCK.value,
                "quantity": 10,
                "reason": "Restock",
                "reference_type": "RESTOCK",
                "reference_id": 1,
                "performed_by_id": staff.id,
                "clinic_id": inventory_item.clinic_id,
            },
        )

        assert response.status_code == 201, response.get_json()

        service.assert_called_once()

        body = response_json(response)

        assert body["success"] is True
        assert body["data"]["item_id"] == inventory_item.id

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {
                "item_id": 1,
                "movement_type": StockMovementType.RESTOCK.value,
                "quantity": 0,
                "performed_by_id": 1,
            },
            {
                "item_id": 1,
                "movement_type": StockMovementType.RESTOCK.value,
                "quantity": -1,
                "performed_by_id": 1,
            },
        ],
    )
    def test_rejects_invalid_payload(
        self,
        client,
        user,
        auth_headers_for,
        payload,
    ):
        response = client.post(
            "/api/inventory/movements",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json=payload,
        )

        assert response.status_code == 400


# ============================================================================
# SUPPLIERS
# ============================================================================


class TestListSuppliersRoute:

    def test_returns_suppliers(
        self,
        client,
        user,
        inventory_supplier,
        auth_headers_for,
    ):
        response = client.get(
            f"/api/inventory/suppliers"
            f"?clinic_id={inventory_supplier.clinic_id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 200, response.get_json()

        body = response_json(response)

        assert body["success"] is True
        assert any(
            supplier["id"] == inventory_supplier.id
            for supplier in body["data"]
        )

    def test_allows_missing_optional_clinic_id(
        self,
        client,
        user,
        inventory_supplier,
        auth_headers_for,
    ):
        response = client.get(
            "/api/inventory/suppliers",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 200


class TestGetSupplierRoute:

    def test_returns_supplier(
        self,
        client,
        user,
        inventory_supplier,
        auth_headers_for,
    ):
        response = client.get(
            f"/api/inventory/suppliers/{inventory_supplier.id}"
            f"?clinic_id={inventory_supplier.clinic_id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 200

        body = response_json(response)

        assert body["success"] is True
        assert body["data"]["id"] == inventory_supplier.id


class TestCreateSupplierRoute:

    def test_creates_supplier(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        response = client.post(
            "/api/inventory/suppliers",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json={
                "clinic_id": clinic.id,
                "name": "New Medical Supplier",
                "contact_person": "Supplier Person",
                "phone": "08012345678",
                "email": "new-supplier@example.com",
                "address": "Port Harcourt",
            },
        )

        assert response.status_code == 201, response.get_json()

        body = response_json(response)

        assert body["success"] is True
        assert body["data"]["name"] == "New Medical Supplier"

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"name": ""},
            {"name": "   "},
            {"name": "Supplier", "email": "not-an-email"},
        ],
    )
    def test_rejects_invalid_payload(
        self,
        client,
        user,
        auth_headers_for,
        payload,
    ):
        response = client.post(
            "/api/inventory/suppliers",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json=payload,
        )

        assert response.status_code == 400


class TestUpdateSupplierRoute:

    def test_updates_supplier(
        self,
        client,
        user,
        inventory_supplier,
        auth_headers_for,
    ):
        response = client.patch(
            f"/api/inventory/suppliers/{inventory_supplier.id}"
            f"?clinic_id={inventory_supplier.clinic_id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json={
                "name": "Updated Supplier",
                "phone": "08111111111",
            },
        )

        assert response.status_code == 200, response.get_json()

        body = response_json(response)

        assert body["success"] is True
        assert body["data"]["name"] == "Updated Supplier"


class TestDeactivateReactivateSupplierRoute:

    def test_deactivates_supplier(
        self,
        client,
        user,
        inventory_supplier,
        auth_headers_for,
    ):
        response = client.post(
            f"/api/inventory/suppliers/{inventory_supplier.id}/deactivate"
            f"?clinic_id={inventory_supplier.clinic_id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 200, response.get_json()

        body = response_json(response)

        assert body["success"] is True
        assert body["data"]["is_active"] is False

    def test_reactivates_supplier(
        self,
        client,
        user,
        inactive_inventory_supplier,
        auth_headers_for,
    ):
        response = client.post(
            f"/api/inventory/suppliers/{inactive_inventory_supplier.id}/reactivate"
            f"?clinic_id={inactive_inventory_supplier.clinic_id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 200, response.get_json()

        body = response_json(response)

        assert body["success"] is True
        assert body["data"]["is_active"] is True

    def test_deactivate_requires_clinic_id(
        self,
        client,
        user,
        inventory_supplier,
        auth_headers_for,
    ):
        response = client.post(
            f"/api/inventory/suppliers/{inventory_supplier.id}/deactivate",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert_error(response, 400, "clinic_id")

    def test_reactivate_requires_clinic_id(
        self,
        client,
        user,
        inactive_inventory_supplier,
        auth_headers_for,
    ):
        response = client.post(
            f"/api/inventory/suppliers/{inactive_inventory_supplier.id}/reactivate",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert_error(response, 400, "clinic_id")


# ============================================================================
# INVENTORY TRANSFERS
# ============================================================================


def _fake_transfer(
    clinic_id,
    item_id=1,
    transfer_id=1,
    requested_by_id=1,
):
    return SimpleNamespace(
        id=transfer_id,
        item_id=item_id,
        batch_id=None,
        source_clinic_id=clinic_id,
        destination_clinic_id=clinic_id + 1,
        quantity=5,
        status=InventoryTransferStatus.PENDING,
        reason="Transfer",
        requested_by_id=requested_by_id,
        approved_by_id=None,
        requested_at=None,
        approved_at=None,
        completed_at=None,
        cancelled_at=None,
        created_at=None,
        updated_at=None,
    )


class TestListInventoryTransfersRoute:

    def test_returns_transfers(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        transfer = _fake_transfer(
            clinic.id,
            requested_by_id=user.id,
        )

        monkeypatch.setattr(
            inventory_routes,
            "list_inventory_transfers",
            Mock(return_value=[transfer]),
        )

        response = client.get(
            f"/api/inventory/transfers?clinic_id={clinic.id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 200, response.get_json()

        body = response_json(response)

        assert body["success"] is True
        assert body["data"][0]["id"] == transfer.id

    def test_requires_clinic_id(
        self,
        client,
        user,
        auth_headers_for,
    ):
        response = client.get(
            "/api/inventory/transfers",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert_error(response, 400, "clinic_id")


class TestGetInventoryTransferRoute:

    def test_returns_transfer(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        transfer = _fake_transfer(
            clinic.id,
            requested_by_id=user.id,
            transfer_id=55,
        )

        monkeypatch.setattr(
            inventory_routes,
            "get_inventory_transfer",
            Mock(return_value=transfer),
        )

        response = client.get(
            f"/api/inventory/transfers/{transfer.id}"
            f"?clinic_id={clinic.id}",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 200, response.get_json()

        body = response_json(response)

        assert body["success"] is True
        assert body["data"]["id"] == transfer.id

    def test_requires_clinic_id(
        self,
        client,
        user,
        auth_headers_for,
    ):
        response = client.get(
            "/api/inventory/transfers/999999",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert_error(response, 400, "clinic_id")


class TestCreateInventoryTransferRoute:

    def test_creates_transfer(
        self,
        client,
        user,
        staff,
        clinic,
        inventory_item,
        auth_headers_for,
        monkeypatch,
    ):
        transfer = _fake_transfer(
            clinic.id,
            item_id=inventory_item.id,
            requested_by_id=staff.id,
        )

        service = Mock(return_value=transfer)

        monkeypatch.setattr(
            inventory_routes,
            "create_inventory_transfer",
            service,
        )

        response = client.post(
            "/api/inventory/transfers",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json={
                "item_id": inventory_item.id,
                "source_clinic_id": clinic.id,
                "destination_clinic_id": clinic.id + 1,
                "quantity": 5,
                "requested_by_id": staff.id,
                "reason": "Transfer",
            },
        )

        assert response.status_code == 201, response.get_json()

        service.assert_called_once()

        body = response_json(response)

        assert body["success"] is True
        assert body["data"]["item_id"] == inventory_item.id

    def test_rejects_same_source_and_destination(
        self,
        client,
        user,
        staff,
        clinic,
        inventory_item,
        auth_headers_for,
    ):
        response = client.post(
            "/api/inventory/transfers",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json={
                "item_id": inventory_item.id,
                "source_clinic_id": clinic.id,
                "destination_clinic_id": clinic.id,
                "quantity": 5,
                "requested_by_id": staff.id,
            },
        )

        assert response.status_code == 400

    def test_rejects_zero_quantity(
        self,
        client,
        user,
        staff,
        clinic,
        inventory_item,
        auth_headers_for,
    ):
        response = client.post(
            "/api/inventory/transfers",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json={
                "item_id": inventory_item.id,
                "source_clinic_id": clinic.id,
                "destination_clinic_id": clinic.id + 1,
                "quantity": 0,
                "requested_by_id": staff.id,
            },
        )

        assert response.status_code == 400


# ============================================================================
# TRANSFER LIFECYCLE
# ============================================================================


class TestApproveInventoryTransferRoute:

    def test_admin_can_approve(
        self,
        client,
        user,
        staff,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        transfer = _fake_transfer(
            clinic.id,
            requested_by_id=staff.id,
        )

        service = Mock(return_value=transfer)

        monkeypatch.setattr(
            inventory_routes,
            "approve_inventory_transfer",
            service,
        )

        response = client.post(
            f"/api/inventory/transfers/{transfer.id}/approve",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json={"approved_by_id": staff.id},
        )

        assert response.status_code == 200, response.get_json()
        service.assert_called_once()

    def test_pharmacist_can_approve(
        self,
        client,
        pharmacist,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        staff, headers = pharmacist

        transfer = _fake_transfer(
            clinic.id,
            requested_by_id=staff.id,
        )

        monkeypatch.setattr(
            inventory_routes,
            "approve_inventory_transfer",
            Mock(return_value=transfer),
        )

        response = client.post(
            f"/api/inventory/transfers/{transfer.id}/approve",
            headers=headers,
            json={"approved_by_id": staff.id},
        )

        assert response.status_code == 200, response.get_json()

    def test_rejects_invalid_payload(
        self,
        client,
        user,
        auth_headers_for,
    ):
        response = client.post(
            "/api/inventory/transfers/1/approve",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json={},
        )

        assert response.status_code == 400


class TestCompleteInventoryTransferRoute:

    def test_admin_can_complete(
        self,
        client,
        user,
        staff,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        transfer = _fake_transfer(
            clinic.id,
            requested_by_id=staff.id,
        )

        service = Mock(return_value=transfer)

        monkeypatch.setattr(
            inventory_routes,
            "complete_inventory_transfer",
            service,
        )

        response = client.post(
            f"/api/inventory/transfers/{transfer.id}/complete",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json={"completed_by_id": staff.id},
        )

        assert response.status_code == 200, response.get_json()
        service.assert_called_once()

    def test_rejects_invalid_payload(
        self,
        client,
        user,
        auth_headers_for,
    ):
        response = client.post(
            "/api/inventory/transfers/1/complete",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json={},
        )

        assert response.status_code == 400


class TestCancelInventoryTransferRoute:

    def test_admin_can_cancel(
        self,
        client,
        user,
        staff,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        transfer = _fake_transfer(
            clinic.id,
            requested_by_id=staff.id,
        )

        service = Mock(return_value=transfer)

        monkeypatch.setattr(
            inventory_routes,
            "cancel_inventory_transfer",
            service,
        )

        response = client.post(
            f"/api/inventory/transfers/{transfer.id}/cancel",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json={
                "cancelled_by_id": staff.id,
                "reason": "No longer required",
            },
        )

        assert response.status_code == 200, response.get_json()
        service.assert_called_once()

    def test_rejects_invalid_payload(
        self,
        client,
        user,
        auth_headers_for,
    ):
        response = client.post(
            "/api/inventory/transfers/1/cancel",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json={},
        )

        assert response.status_code == 400


# ============================================================================
# SERVICE ERROR MAPPING
# ============================================================================


class TestInventoryRouteExceptionMapping:

    @pytest.mark.parametrize(
        "service_name,method,url",
        [
            (
                "get_inventory_item",
                "get",
                "/api/inventory/items/1?clinic_id=1",
            ),
            (
                "get_inventory_batch",
                "get",
                "/api/inventory/batches/1?clinic_id=1",
            ),
            (
                "get_supplier",
                "get",
                "/api/inventory/suppliers/1?clinic_id=1",
            ),
            (
                "get_inventory_transfer",
                "get",
                "/api/inventory/transfers/1?clinic_id=1",
            ),
        ],
    )
    def test_maps_not_found_to_404(
        self,
        client,
        user,
        auth_headers_for,
        monkeypatch,
        service_name,
        method,
        url,
    ):
        monkeypatch.setattr(
            inventory_routes,
            service_name,
            Mock(side_effect=NotFoundError("Resource not found")),
        )

        response = getattr(client, method)(
            url,
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert_error(response, 404, "Resource not found")

    def test_create_item_maps_validation_to_400(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        monkeypatch.setattr(
            inventory_routes,
            "create_inventory_item",
            Mock(side_effect=ValidationError("Invalid inventory item")),
        )

        response = client.post(
            "/api/inventory/items",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json={
                "clinic_id": clinic.id,
                "name": "Test Item",
            },
        )

        assert_error(response, 400, "Invalid inventory item")

    def test_create_item_maps_conflict_to_400(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        monkeypatch.setattr(
            inventory_routes,
            "create_inventory_item",
            Mock(side_effect=ConflictError("Item already exists")),
        )

        response = client.post(
            "/api/inventory/items",
            headers=auth_headers_for(user, role=Role.ADMIN),
            json={
                "clinic_id": clinic.id,
                "name": "Test Item",
            },
        )

        assert_error(response, 400, "Item already exists")


# ============================================================================
# QUERY FILTER VALIDATION
# ============================================================================


class TestInventoryQueryValidation:

    def test_items_reject_unknown_query_parameter(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        response = client.get(
            f"/api/inventory/items"
            f"?clinic_id={clinic.id}&unknown=true",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 400

    def test_batches_reject_unknown_query_parameter(
        self,
        client,
        user,
        inventory_item,
        auth_headers_for,
    ):
        response = client.get(
            f"/api/inventory/items/{inventory_item.id}/batches"
            f"?clinic_id={inventory_item.clinic_id}&unknown=true",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 400

    def test_suppliers_reject_unknown_query_parameter(
        self,
        client,
        user,
        auth_headers_for,
    ):
        response = client.get(
            "/api/inventory/suppliers?unknown=true",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 400

    def test_transfers_reject_unknown_query_parameter(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        response = client.get(
            f"/api/inventory/transfers"
            f"?clinic_id={clinic.id}&unknown=true",
            headers=auth_headers_for(user, role=Role.ADMIN),
        )

        assert response.status_code == 400