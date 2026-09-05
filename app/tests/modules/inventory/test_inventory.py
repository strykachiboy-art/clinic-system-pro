from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.enums.inventory_enums import (
    InventoryCategory,
    InventoryTransferStatus,
    StockMovementDirection,
    StockMovementType,
)
from app.core.enums.role_enums import Role
from app.modules.inventory.models.inventory_model import (
    InventoryBatch,
    InventoryItem,
    InventorySupplier,
    InventoryTransfer,
    StockMovement,
)


# ============================================================================
# LOCAL INVENTORY FIXTURES
# ============================================================================


@pytest.fixture()
def admin_staff_and_headers(make_authenticated_staff, clinic):
    return make_authenticated_staff(
        clinic,
        Role.ADMIN,
        first_name="Inventory",
        last_name="Admin",
    )


@pytest.fixture()
def pharmacist_staff_and_headers(make_authenticated_staff, clinic):
    return make_authenticated_staff(
        clinic,
        Role.PHARMACIST,
        first_name="Inventory",
        last_name="Pharmacist",
    )


@pytest.fixture()
def second_clinic(make_clinic):
    return make_clinic(name="Destination Clinic")


@pytest.fixture()
def second_admin_staff_and_headers(
    make_authenticated_staff,
    second_clinic,
):
    return make_authenticated_staff(
        second_clinic,
        Role.ADMIN,
        first_name="Destination",
        last_name="Admin",
    )


@pytest.fixture()
def inventory_item(db, clinic):
    item = InventoryItem(
        clinic_id=clinic.id,
        name="Test Medical Supply",
        category=InventoryCategory.MEDICAL_SUPPLY,
        sku="TEST-SKU-001",
        barcode="TEST-BARCODE-001",
        unit="piece",
        quantity_on_hand=100,
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
        name="Low Stock Supply",
        category=InventoryCategory.CONSUMABLE,
        sku="LOW-STOCK-001",
        unit="box",
        quantity_on_hand=5,
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
        name="Inactive Supply",
        category=InventoryCategory.MEDICAL_SUPPLY,
        sku="INACTIVE-001",
        unit="piece",
        quantity_on_hand=20,
        reorder_level=5,
        is_active=False,
    )

    db.session.add(item)
    db.session.commit()

    return item


@pytest.fixture()
def supplier(db, clinic):
    supplier = InventorySupplier(
        clinic_id=clinic.id,
        name="Test Supplier",
        contact_person="John Supplier",
        phone="08000000000",
        email="supplier@test.com",
        address="Test Supplier Address",
        is_active=True,
    )

    db.session.add(supplier)
    db.session.commit()

    return supplier


@pytest.fixture()
def global_supplier(db):
    supplier = InventorySupplier(
        clinic_id=None,
        name="Global Supplier",
        contact_person="Global Contact",
        phone="08111111111",
        email="global@supplier.test",
        address="Global Address",
        is_active=True,
    )

    db.session.add(supplier)
    db.session.commit()

    return supplier


@pytest.fixture()
def inactive_supplier(db, clinic):
    supplier = InventorySupplier(
        clinic_id=clinic.id,
        name="Inactive Supplier",
        is_active=False,
    )

    db.session.add(supplier)
    db.session.commit()

    return supplier


@pytest.fixture()
def inventory_batch(db, inventory_item, supplier):
    batch = InventoryBatch(
        item_id=inventory_item.id,
        supplier_id=supplier.id,
        batch_number="BATCH-001",
        quantity_on_hand=50,
        unit_cost=Decimal("1250.00"),
        expiry_date=date.today() + timedelta(days=60),
        is_active=True,
    )

    db.session.add(batch)
    db.session.commit()

    return batch


@pytest.fixture()
def expiring_batch(db, inventory_item, supplier):
    batch = InventoryBatch(
        item_id=inventory_item.id,
        supplier_id=supplier.id,
        batch_number="EXPIRING-001",
        quantity_on_hand=20,
        unit_cost=Decimal("500.00"),
        expiry_date=date.today() + timedelta(days=5),
        is_active=True,
    )

    db.session.add(batch)
    db.session.commit()

    return batch


@pytest.fixture()
def inactive_batch(db, inventory_item, supplier):
    batch = InventoryBatch(
        item_id=inventory_item.id,
        supplier_id=supplier.id,
        batch_number="INACTIVE-BATCH-001",
        quantity_on_hand=20,
        unit_cost=Decimal("500.00"),
        expiry_date=date.today() + timedelta(days=60),
        is_active=False,
    )

    db.session.add(batch)
    db.session.commit()

    return batch


@pytest.fixture()
def stock_movement(db, inventory_item, admin_staff_and_headers):
    staff, _headers = admin_staff_and_headers

    movement = StockMovement(
        item_id=inventory_item.id,
        batch_id=None,
        movement_type=StockMovementType.RESTOCK,
        direction=StockMovementDirection.IN,
        quantity=25,
        reason="Initial test movement",
        performed_by_id=staff.id,
        reference_type="test",
        reference_id=1,
    )

    db.session.add(movement)
    db.session.commit()

    return movement


@pytest.fixture()
def inventory_transfer(
    db,
    clinic,
    second_clinic,
    inventory_item,
    admin_staff_and_headers,
):
    staff, _headers = admin_staff_and_headers

    transfer = InventoryTransfer(
        item_id=inventory_item.id,
        batch_id=None,
        source_clinic_id=clinic.id,
        destination_clinic_id=second_clinic.id,
        quantity=10,
        status=InventoryTransferStatus.PENDING,
        reason="Test transfer",
        requested_by_id=staff.id,
    )

    db.session.add(transfer)
    db.session.commit()

    return transfer


def _body(response):
    body = response.get_json()
    assert body is not None
    return body


def _assert_success(response, status_code):
    assert response.status_code == status_code, response.get_json()

    body = _body(response)

    assert body["success"] is True
    assert "data" in body

    return body["data"]


def _assert_error(response, status_code):
    assert response.status_code == status_code, response.get_json()

    body = _body(response)

    assert "error" in body

    return body


# ============================================================================
# INVENTORY ITEMS
# ============================================================================


class TestListInventoryItemsRoute:
    def test_returns_items(
        self,
        client,
        clinic,
        inventory_item,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/items?clinic_id={clinic.id}",
            headers=headers,
        )

        data = _assert_success(response, 200)

        assert isinstance(data, list)
        assert any(item["id"] == inventory_item.id for item in data)

    def test_filters_by_category(
        self,
        client,
        clinic,
        inventory_item,
        low_stock_item,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/items"
            f"?clinic_id={clinic.id}"
            f"&category={InventoryCategory.MEDICAL_SUPPLY.value}",
            headers=headers,
        )

        data = _assert_success(response, 200)

        assert all(
            item["category"] == InventoryCategory.MEDICAL_SUPPLY.value
            for item in data
        )

    def test_filters_low_stock(
        self,
        client,
        clinic,
        inventory_item,
        low_stock_item,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/items"
            f"?clinic_id={clinic.id}"
            f"&low_stock_only=true",
            headers=headers,
        )

        data = _assert_success(response, 200)

        ids = {item["id"] for item in data}

        assert low_stock_item.id in ids
        assert inventory_item.id not in ids

    def test_excludes_inactive_items_by_default(
        self,
        client,
        clinic,
        inactive_inventory_item,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/items?clinic_id={clinic.id}",
            headers=headers,
        )

        data = _assert_success(response, 200)

        ids = {item["id"] for item in data}

        assert inactive_inventory_item.id not in ids

    def test_include_inactive_returns_inactive_items(
        self,
        client,
        clinic,
        inactive_inventory_item,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/items"
            f"?clinic_id={clinic.id}"
            f"&include_inactive=true",
            headers=headers,
        )

        data = _assert_success(response, 200)

        ids = {item["id"] for item in data}

        assert inactive_inventory_item.id in ids

    def test_requires_clinic_id(
        self,
        client,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            "/api/inventory/items",
            headers=headers,
        )

        _assert_error(response, 400)

    def test_requires_authentication(self, client, clinic):
        response = client.get(
            f"/api/inventory/items?clinic_id={clinic.id}",
        )

        assert response.status_code in (401, 422)


class TestGetInventoryItemRoute:
    def test_returns_item(
        self,
        client,
        inventory_item,
        clinic,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/items/{inventory_item.id}"
            f"?clinic_id={clinic.id}",
            headers=headers,
        )

        data = _assert_success(response, 200)

        assert data["id"] == inventory_item.id
        assert data["clinic_id"] == clinic.id
        assert data["name"] == inventory_item.name

    def test_returns_not_found(
        self,
        client,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            "/api/inventory/items/999999",
            headers=headers,
        )

        _assert_error(response, 404)

    def test_rejects_wrong_clinic(
        self,
        client,
        inventory_item,
        make_clinic,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers
        other_clinic = make_clinic(name="Other Inventory Clinic")

        response = client.get(
            f"/api/inventory/items/{inventory_item.id}"
            f"?clinic_id={other_clinic.id}",
            headers=headers,
        )

        _assert_error(response, 400)


class TestCreateInventoryItemRoute:
    def test_creates_item(
        self,
        client,
        clinic,
        admin_staff_and_headers,
    ):
        staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/items",
            headers=headers,
            json={
                "clinic_id": clinic.id,
                "name": "Surgical Gloves",
                "category": InventoryCategory.CONSUMABLE.value,
                "sku": "GLOVES-001",
                "barcode": "BARCODE-001",
                "unit": "box",
                "initial_quantity": 50,
                "reorder_level": 10,
                "performed_by_id": staff.id,
            },
        )

        data = _assert_success(response, 201)

        assert data["id"] > 0
        assert data["clinic_id"] == clinic.id
        assert data["name"] == "Surgical Gloves"
        assert data["category"] == InventoryCategory.CONSUMABLE.value
        assert data["quantity_on_hand"] == 50
        assert data["reorder_level"] == 10

    def test_creates_item_without_initial_quantity(
        self,
        client,
        clinic,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/items",
            headers=headers,
            json={
                "clinic_id": clinic.id,
                "name": "Empty Stock Item",
            },
        )

        data = _assert_success(response, 201)

        assert data["quantity_on_hand"] == 0

    def test_rejects_invalid_payload(
        self,
        client,
        clinic,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/items",
            headers=headers,
            json={
                "clinic_id": clinic.id,
                "name": "",
            },
        )

        _assert_error(response, 400)

    def test_rejects_negative_initial_quantity(
        self,
        client,
        clinic,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/items",
            headers=headers,
            json={
                "clinic_id": clinic.id,
                "name": "Invalid Quantity Item",
                "initial_quantity": -1,
            },
        )

        _assert_error(response, 400)

    def test_rejects_unknown_fields(
        self,
        client,
        clinic,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/items",
            headers=headers,
            json={
                "clinic_id": clinic.id,
                "name": "Unknown Field Item",
                "quantity_on_hand": 100,
            },
        )

        _assert_error(response, 400)


class TestUpdateInventoryItemRoute:
    def test_updates_item(
        self,
        client,
        clinic,
        inventory_item,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.patch(
            f"/api/inventory/items/{inventory_item.id}"
            f"?clinic_id={clinic.id}",
            headers=headers,
            json={
                "name": "Updated Medical Supply",
                "reorder_level": 25,
            },
        )

        data = _assert_success(response, 200)

        assert data["id"] == inventory_item.id
        assert data["name"] == "Updated Medical Supply"
        assert data["reorder_level"] == 25

    def test_rejects_unknown_field(
        self,
        client,
        clinic,
        inventory_item,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.patch(
            f"/api/inventory/items/{inventory_item.id}"
            f"?clinic_id={clinic.id}",
            headers=headers,
            json={
                "quantity_on_hand": 999,
            },
        )

        _assert_error(response, 400)

    def test_requires_clinic_id(
        self,
        client,
        inventory_item,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.patch(
            f"/api/inventory/items/{inventory_item.id}",
            headers=headers,
            json={"name": "Updated"},
        )

        _assert_error(response, 400)


class TestDeactivateInventoryItemRoute:
    def test_admin_can_deactivate(
        self,
        client,
        clinic,
        inventory_item,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.post(
            f"/api/inventory/items/{inventory_item.id}/deactivate"
            f"?clinic_id={clinic.id}",
            headers=headers,
        )

        data = _assert_success(response, 200)

        assert data["id"] == inventory_item.id
        assert data["is_active"] is False

    def test_requires_admin_role(
        self,
        client,
        clinic,
        inventory_item,
        pharmacist_staff_and_headers,
    ):
        _staff, headers = pharmacist_staff_and_headers

        response = client.post(
            f"/api/inventory/items/{inventory_item.id}/deactivate"
            f"?clinic_id={clinic.id}",
            headers=headers,
        )

        assert response.status_code == 403

    def test_requires_clinic_id(
        self,
        client,
        inventory_item,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.post(
            f"/api/inventory/items/{inventory_item.id}/deactivate",
            headers=headers,
        )

        _assert_error(response, 400)


class TestReactivateInventoryItemRoute:
    def test_admin_can_reactivate(
        self,
        client,
        clinic,
        inactive_inventory_item,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.post(
            f"/api/inventory/items/{inactive_inventory_item.id}/reactivate"
            f"?clinic_id={clinic.id}",
            headers=headers,
        )

        data = _assert_success(response, 200)

        assert data["id"] == inactive_inventory_item.id
        assert data["is_active"] is True

    def test_requires_admin_role(
        self,
        client,
        clinic,
        inactive_inventory_item,
        pharmacist_staff_and_headers,
    ):
        _staff, headers = pharmacist_staff_and_headers

        response = client.post(
            f"/api/inventory/items/{inactive_inventory_item.id}/reactivate"
            f"?clinic_id={clinic.id}",
            headers=headers,
        )

        assert response.status_code == 403


class TestLowStockItemsRoute:
    def test_returns_low_stock_items(
        self,
        client,
        clinic,
        low_stock_item,
        inventory_item,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/items/low-stock?clinic_id={clinic.id}",
            headers=headers,
        )

        data = _assert_success(response, 200)

        ids = {item["id"] for item in data}

        assert low_stock_item.id in ids
        assert inventory_item.id not in ids

    def test_requires_clinic_id(
        self,
        client,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            "/api/inventory/items/low-stock",
            headers=headers,
        )

        _assert_error(response, 400)


# ============================================================================
# INVENTORY BATCHES
# ============================================================================


class TestListInventoryBatchesRoute:
    def test_returns_batches(
        self,
        client,
        clinic,
        inventory_item,
        inventory_batch,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/items/{inventory_item.id}/batches"
            f"?clinic_id={clinic.id}",
            headers=headers,
        )

        data = _assert_success(response, 200)

        assert isinstance(data, list)
        assert any(
            batch["id"] == inventory_batch.id
            for batch in data
        )

    def test_excludes_inactive_batches_by_default(
        self,
        client,
        clinic,
        inventory_item,
        inactive_batch,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/items/{inventory_item.id}/batches"
            f"?clinic_id={clinic.id}",
            headers=headers,
        )

        data = _assert_success(response, 200)

        ids = {batch["id"] for batch in data}

        assert inactive_batch.id not in ids

    def test_include_inactive_batches(
        self,
        client,
        clinic,
        inventory_item,
        inactive_batch,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/items/{inventory_item.id}/batches"
            f"?clinic_id={clinic.id}"
            f"&include_inactive=true",
            headers=headers,
        )

        data = _assert_success(response, 200)

        ids = {batch["id"] for batch in data}

        assert inactive_batch.id in ids

    def test_requires_clinic_id(
        self,
        client,
        inventory_item,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/items/{inventory_item.id}/batches",
            headers=headers,
        )

        _assert_error(response, 400)


class TestGetInventoryBatchRoute:
    def test_returns_batch(
        self,
        client,
        inventory_batch,
        clinic,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/batches/{inventory_batch.id}"
            f"?clinic_id={clinic.id}",
            headers=headers,
        )

        data = _assert_success(response, 200)

        assert data["id"] == inventory_batch.id
        assert data["item_id"] == inventory_batch.item_id
        assert data["batch_number"] == inventory_batch.batch_number

    def test_returns_not_found(
        self,
        client,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            "/api/inventory/batches/999999",
            headers=headers,
        )

        _assert_error(response, 404)


class TestCreateInventoryBatchRoute:
    def test_creates_batch(
        self,
        client,
        clinic,
        inventory_item,
        supplier,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/batches",
            headers=headers,
            json={
                "item_id": inventory_item.id,
                "supplier_id": supplier.id,
                "batch_number": "NEW-BATCH-001",
                "unit_cost": "1500.00",
                "expiry_date": (
                    date.today() + timedelta(days=90)
                ).isoformat(),
                "clinic_id": clinic.id,
            },
        )

        data = _assert_success(response, 201)

        assert data["id"] > 0
        assert data["item_id"] == inventory_item.id
        assert data["supplier_id"] == supplier.id
        assert data["batch_number"] == "NEW-BATCH-001"
        assert data["quantity_on_hand"] == 0

    def test_rejects_past_expiry_date(
        self,
        client,
        clinic,
        inventory_item,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/batches",
            headers=headers,
            json={
                "item_id": inventory_item.id,
                "batch_number": "PAST-EXPIRY",
                "expiry_date": (
                    date.today() - timedelta(days=1)
                ).isoformat(),
                "clinic_id": clinic.id,
            },
        )

        _assert_error(response, 400)

    def test_rejects_duplicate_batch(
        self,
        client,
        clinic,
        inventory_item,
        inventory_batch,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/batches",
            headers=headers,
            json={
                "item_id": inventory_item.id,
                "batch_number": inventory_batch.batch_number,
                "clinic_id": clinic.id,
            },
        )

        _assert_error(response, 400)


class TestUpdateInventoryBatchRoute:
    def test_updates_batch(
        self,
        client,
        clinic,
        inventory_batch,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.patch(
            f"/api/inventory/batches/{inventory_batch.id}"
            f"?clinic_id={clinic.id}",
            headers=headers,
            json={
                "batch_number": "UPDATED-BATCH",
                "unit_cost": "2000.00",
            },
        )

        data = _assert_success(response, 200)

        assert data["id"] == inventory_batch.id
        assert data["batch_number"] == "UPDATED-BATCH"
        assert data["unit_cost"] == "2000.00"

    def test_requires_clinic_id(
        self,
        client,
        inventory_batch,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.patch(
            f"/api/inventory/batches/{inventory_batch.id}",
            headers=headers,
            json={"batch_number": "UPDATED"},
        )

        _assert_error(response, 400)

    def test_rejects_past_expiry_date(
        self,
        client,
        clinic,
        inventory_batch,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.patch(
            f"/api/inventory/batches/{inventory_batch.id}"
            f"?clinic_id={clinic.id}",
            headers=headers,
            json={
                "expiry_date": (
                    date.today() - timedelta(days=1)
                ).isoformat(),
            },
        )

        _assert_error(response, 400)


class TestExpiringInventoryBatchesRoute:
    def test_returns_expiring_batches(
        self,
        client,
        clinic,
        expiring_batch,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/batches/expiring"
            f"?clinic_id={clinic.id}"
            f"&days=30",
            headers=headers,
        )

        data = _assert_success(response, 200)

        ids = {batch["id"] for batch in data}

        assert expiring_batch.id in ids

    def test_does_not_return_batches_outside_window(
        self,
        client,
        clinic,
        inventory_batch,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/batches/expiring"
            f"?clinic_id={clinic.id}"
            f"&days=1",
            headers=headers,
        )

        data = _assert_success(response, 200)

        ids = {batch["id"] for batch in data}

        assert inventory_batch.id not in ids

    def test_rejects_negative_days(
        self,
        client,
        clinic,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/batches/expiring"
            f"?clinic_id={clinic.id}"
            f"&days=-1",
            headers=headers,
        )

        _assert_error(response, 400)


# ============================================================================
# STOCK MOVEMENTS
# ============================================================================


class TestListStockMovementsRoute:
    def test_returns_movements(
        self,
        client,
        clinic,
        inventory_item,
        stock_movement,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/items/{inventory_item.id}/movements"
            f"?clinic_id={clinic.id}",
            headers=headers,
        )

        data = _assert_success(response, 200)

        assert isinstance(data, list)
        assert any(
            movement["id"] == stock_movement.id
            for movement in data
        )

    def test_requires_clinic_id(
        self,
        client,
        inventory_item,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/items/{inventory_item.id}/movements",
            headers=headers,
        )

        _assert_error(response, 400)


class TestCreateStockMovementRoute:
    def test_creates_restock_movement(
        self,
        client,
        clinic,
        inventory_item,
        admin_staff_and_headers,
    ):
        staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/movements",
            headers=headers,
            json={
                "item_id": inventory_item.id,
                "movement_type": StockMovementType.RESTOCK.value,
                "quantity": 25,
                "reason": "Restocking supplies",
                "performed_by_id": staff.id,
                "clinic_id": clinic.id,
            },
        )

        data = _assert_success(response, 201)

        assert data["id"] > 0
        assert data["item_id"] == inventory_item.id
        assert data["movement_type"] == StockMovementType.RESTOCK.value
        assert data["direction"] == StockMovementDirection.IN.value
        assert data["quantity"] == 25

    def test_creates_usage_movement(
        self,
        client,
        clinic,
        inventory_item,
        admin_staff_and_headers,
    ):
        staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/movements",
            headers=headers,
            json={
                "item_id": inventory_item.id,
                "movement_type": StockMovementType.USAGE.value,
                "quantity": 10,
                "reason": "Used during procedure",
                "performed_by_id": staff.id,
                "clinic_id": clinic.id,
            },
        )

        data = _assert_success(response, 201)

        assert data["movement_type"] == StockMovementType.USAGE.value
        assert data["direction"] == StockMovementDirection.OUT.value
        assert data["quantity"] == 10

    def test_creates_positive_adjustment(
        self,
        client,
        clinic,
        inventory_item,
        admin_staff_and_headers,
    ):
        staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/movements",
            headers=headers,
            json={
                "item_id": inventory_item.id,
                "movement_type": StockMovementType.ADJUSTMENT.value,
                "quantity": 5,
                "reason": "Stock count adjustment",
                "performed_by_id": staff.id,
                "clinic_id": clinic.id,
            },
        )

        data = _assert_success(response, 201)

        assert data["movement_type"] == StockMovementType.ADJUSTMENT.value
        assert data["direction"] == StockMovementDirection.IN.value
        assert data["quantity"] == 5

    def test_creates_negative_adjustment(
        self,
        client,
        clinic,
        inventory_item,
        admin_staff_and_headers,
    ):
        staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/movements",
            headers=headers,
            json={
                "item_id": inventory_item.id,
                "movement_type": StockMovementType.ADJUSTMENT.value,
                "quantity": -5,
                "reason": "Damaged stock correction",
                "performed_by_id": staff.id,
                "clinic_id": clinic.id,
            },
        )

        data = _assert_success(response, 201)

        assert data["movement_type"] == StockMovementType.ADJUSTMENT.value
        assert data["direction"] == StockMovementDirection.OUT.value
        assert data["quantity"] == 5

    def test_rejects_zero_adjustment(
        self,
        client,
        clinic,
        inventory_item,
        admin_staff_and_headers,
    ):
        staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/movements",
            headers=headers,
            json={
                "item_id": inventory_item.id,
                "movement_type": StockMovementType.ADJUSTMENT.value,
                "quantity": 0,
                "performed_by_id": staff.id,
                "clinic_id": clinic.id,
            },
        )

        _assert_error(response, 400)

    def test_rejects_zero_regular_movement(
        self,
        client,
        clinic,
        inventory_item,
        admin_staff_and_headers,
    ):
        staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/movements",
            headers=headers,
            json={
                "item_id": inventory_item.id,
                "movement_type": StockMovementType.RESTOCK.value,
                "quantity": 0,
                "performed_by_id": staff.id,
                "clinic_id": clinic.id,
            },
        )

        _assert_error(response, 400)

    def test_rejects_negative_regular_movement(
        self,
        client,
        clinic,
        inventory_item,
        admin_staff_and_headers,
    ):
        staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/movements",
            headers=headers,
            json={
                "item_id": inventory_item.id,
                "movement_type": StockMovementType.RESTOCK.value,
                "quantity": -5,
                "performed_by_id": staff.id,
                "clinic_id": clinic.id,
            },
        )

        _assert_error(response, 400)

    def test_rejects_insufficient_stock(
        self,
        client,
        clinic,
        inventory_item,
        admin_staff_and_headers,
    ):
        staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/movements",
            headers=headers,
            json={
                "item_id": inventory_item.id,
                "movement_type": StockMovementType.USAGE.value,
                "quantity": 999999,
                "performed_by_id": staff.id,
                "clinic_id": clinic.id,
            },
        )

        _assert_error(response, 400)


# ============================================================================
# SUPPLIERS
# ============================================================================


class TestListSuppliersRoute:
    def test_returns_suppliers(
        self,
        client,
        clinic,
        supplier,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/suppliers?clinic_id={clinic.id}",
            headers=headers,
        )

        data = _assert_success(response, 200)

        assert isinstance(data, list)
        assert any(
            item["id"] == supplier.id
            for item in data
        )

    def test_returns_global_suppliers(
        self,
        client,
        clinic,
        global_supplier,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/suppliers?clinic_id={clinic.id}",
            headers=headers,
        )

        data = _assert_success(response, 200)

        ids = {item["id"] for item in data}

        assert global_supplier.id in ids

    def test_excludes_inactive_suppliers(
        self,
        client,
        clinic,
        inactive_supplier,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/suppliers?clinic_id={clinic.id}",
            headers=headers,
        )

        data = _assert_success(response, 200)

        ids = {item["id"] for item in data}

        assert inactive_supplier.id not in ids

    def test_include_inactive_suppliers(
        self,
        client,
        clinic,
        inactive_supplier,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/suppliers"
            f"?clinic_id={clinic.id}"
            f"&include_inactive=true",
            headers=headers,
        )

        data = _assert_success(response, 200)

        ids = {item["id"] for item in data}

        assert inactive_supplier.id in ids


class TestGetSupplierRoute:
    def test_returns_supplier(
        self,
        client,
        clinic,
        supplier,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/suppliers/{supplier.id}"
            f"?clinic_id={clinic.id}",
            headers=headers,
        )

        data = _assert_success(response, 200)

        assert data["id"] == supplier.id
        assert data["clinic_id"] == clinic.id
        assert data["name"] == supplier.name

    def test_returns_not_found(
        self,
        client,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            "/api/inventory/suppliers/999999",
            headers=headers,
        )

        _assert_error(response, 404)


class TestCreateSupplierRoute:
    def test_creates_supplier(
        self,
        client,
        clinic,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/suppliers",
            headers=headers,
            json={
                "clinic_id": clinic.id,
                "name": "New Supplier",
                "contact_person": "Jane Supplier",
                "phone": "08012345678",
                "email": "new@supplier.com",
                "address": "New Supplier Address",
            },
        )

        data = _assert_success(response, 201)

        assert data["id"] > 0
        assert data["clinic_id"] == clinic.id
        assert data["name"] == "New Supplier"
        assert data["email"] == "new@supplier.com"

    def test_creates_global_supplier(
        self,
        client,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/suppliers",
            headers=headers,
            json={
                "name": "Global New Supplier",
            },
        )

        data = _assert_success(response, 201)

        assert data["clinic_id"] is None

    def test_rejects_empty_name(
        self,
        client,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/suppliers",
            headers=headers,
            json={
                "name": "",
            },
        )

        _assert_error(response, 400)

    def test_rejects_invalid_email(
        self,
        client,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/suppliers",
            headers=headers,
            json={
                "name": "Invalid Email Supplier",
                "email": "not-an-email",
            },
        )

        _assert_error(response, 400)

    def test_rejects_duplicate_supplier(
        self,
        client,
        clinic,
        supplier,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/suppliers",
            headers=headers,
            json={
                "clinic_id": clinic.id,
                "name": supplier.name,
            },
        )

        _assert_error(response, 400)


class TestUpdateSupplierRoute:
    def test_admin_can_update_supplier(
        self,
        client,
        clinic,
        supplier,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.patch(
            f"/api/inventory/suppliers/{supplier.id}"
            f"?clinic_id={clinic.id}",
            headers=headers,
            json={
                "name": "Updated Supplier",
                "phone": "08999999999",
            },
        )

        data = _assert_success(response, 200)

        assert data["id"] == supplier.id
        assert data["name"] == "Updated Supplier"
        assert data["phone"] == "08999999999"

    def test_rejects_clinic_id_in_json(
        self,
        client,
        clinic,
        supplier,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.patch(
            f"/api/inventory/suppliers/{supplier.id}"
            f"?clinic_id={clinic.id}",
            headers=headers,
            json={
                "clinic_id": clinic.id,
                "name": "Updated Supplier",
            },
        )

        _assert_error(response, 400)

    def test_requires_admin_role(
        self,
        client,
        clinic,
        supplier,
        pharmacist_staff_and_headers,
    ):
        _staff, headers = pharmacist_staff_and_headers

        response = client.patch(
            f"/api/inventory/suppliers/{supplier.id}"
            f"?clinic_id={clinic.id}",
            headers=headers,
            json={
                "name": "Pharmacist Update",
            },
        )

        assert response.status_code == 403


class TestDeactivateSupplierRoute:
    def test_admin_can_deactivate_supplier(
        self,
        client,
        clinic,
        supplier,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.post(
            f"/api/inventory/suppliers/{supplier.id}/deactivate"
            f"?clinic_id={clinic.id}",
            headers=headers,
        )

        data = _assert_success(response, 200)

        assert data["id"] == supplier.id
        assert data["is_active"] is False

    def test_requires_clinic_id(
        self,
        client,
        supplier,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.post(
            f"/api/inventory/suppliers/{supplier.id}/deactivate",
            headers=headers,
        )

        _assert_error(response, 400)

    def test_requires_admin_role(
        self,
        client,
        clinic,
        supplier,
        pharmacist_staff_and_headers,
    ):
        _staff, headers = pharmacist_staff_and_headers

        response = client.post(
            f"/api/inventory/suppliers/{supplier.id}/deactivate"
            f"?clinic_id={clinic.id}",
            headers=headers,
        )

        assert response.status_code == 403


class TestReactivateSupplierRoute:
    def test_admin_can_reactivate_supplier(
        self,
        client,
        clinic,
        inactive_supplier,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.post(
            f"/api/inventory/suppliers/{inactive_supplier.id}/reactivate"
            f"?clinic_id={clinic.id}",
            headers=headers,
        )

        data = _assert_success(response, 200)

        assert data["id"] == inactive_supplier.id
        assert data["is_active"] is True

    def test_requires_clinic_id(
        self,
        client,
        inactive_supplier,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.post(
            f"/api/inventory/suppliers/{inactive_supplier.id}/reactivate",
            headers=headers,
        )

        _assert_error(response, 400)

    def test_requires_admin_role(
        self,
        client,
        clinic,
        inactive_supplier,
        pharmacist_staff_and_headers,
    ):
        _staff, headers = pharmacist_staff_and_headers

        response = client.post(
            f"/api/inventory/suppliers/{inactive_supplier.id}/reactivate"
            f"?clinic_id={clinic.id}",
            headers=headers,
        )

        assert response.status_code == 403


# ============================================================================
# INVENTORY TRANSFERS
# ============================================================================


class TestListInventoryTransfersRoute:
    def test_returns_transfers(
        self,
        client,
        clinic,
        inventory_transfer,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/transfers?clinic_id={clinic.id}",
            headers=headers,
        )

        data = _assert_success(response, 200)

        assert isinstance(data, list)
        assert any(
            transfer["id"] == inventory_transfer.id
            for transfer in data
        )

    def test_filters_by_status(
        self,
        client,
        clinic,
        inventory_transfer,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/transfers"
            f"?clinic_id={clinic.id}"
            f"&status={InventoryTransferStatus.PENDING.value}",
            headers=headers,
        )

        data = _assert_success(response, 200)

        assert all(
            transfer["status"] == InventoryTransferStatus.PENDING.value
            for transfer in data
        )

    def test_requires_clinic_id(
        self,
        client,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            "/api/inventory/transfers",
            headers=headers,
        )

        _assert_error(response, 400)


class TestGetInventoryTransferRoute:
    def test_returns_transfer(
        self,
        client,
        clinic,
        inventory_transfer,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/transfers/{inventory_transfer.id}"
            f"?clinic_id={clinic.id}",
            headers=headers,
        )

        data = _assert_success(response, 200)

        assert data["id"] == inventory_transfer.id
        assert data["item_id"] == inventory_transfer.item_id
        assert data["quantity"] == inventory_transfer.quantity
        assert data["status"] == InventoryTransferStatus.PENDING.value

    def test_returns_not_found(
        self,
        client,
        clinic,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.get(
            f"/api/inventory/transfers/999999"
            f"?clinic_id={clinic.id}",
            headers=headers,
        )

        _assert_error(response, 404)

    def test_accepts_valid_clinic_id(
        self,
        client,
        inventory_transfer,
        second_clinic,
        second_admin_staff_and_headers,
    ):
        _staff, headers = second_admin_staff_and_headers

        response = client.get(
            f"/api/inventory/transfers/{inventory_transfer.id}"
            f"?clinic_id={second_clinic.id}",
            headers=headers,
        )

        data = _assert_success(response, 200)

        assert data["id"] == inventory_transfer.id
        assert data["source_clinic_id"] == inventory_transfer.source_clinic_id
        assert data["destination_clinic_id"] == inventory_transfer.destination_clinic_id


class TestCreateInventoryTransferRoute:
    def test_creates_transfer(
        self,
        client,
        clinic,
        second_clinic,
        inventory_item,
        admin_staff_and_headers,
    ):
        staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/transfers",
            headers=headers,
            json={
                "item_id": inventory_item.id,
                "source_clinic_id": clinic.id,
                "destination_clinic_id": second_clinic.id,
                "quantity": 10,
                "requested_by_id": staff.id,
                "reason": "Transfer to destination clinic",
            },
        )

        data = _assert_success(response, 201)

        assert data["id"] > 0
        assert data["item_id"] == inventory_item.id
        assert data["source_clinic_id"] == clinic.id
        assert data["destination_clinic_id"] == second_clinic.id
        assert data["quantity"] == 10
        assert data["status"] == InventoryTransferStatus.PENDING.value

    def test_rejects_same_source_and_destination(
        self,
        client,
        clinic,
        inventory_item,
        admin_staff_and_headers,
    ):
        staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/transfers",
            headers=headers,
            json={
                "item_id": inventory_item.id,
                "source_clinic_id": clinic.id,
                "destination_clinic_id": clinic.id,
                "quantity": 10,
                "requested_by_id": staff.id,
            },
        )

        _assert_error(response, 400)

    def test_rejects_zero_quantity(
        self,
        client,
        clinic,
        second_clinic,
        inventory_item,
        admin_staff_and_headers,
    ):
        staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/transfers",
            headers=headers,
            json={
                "item_id": inventory_item.id,
                "source_clinic_id": clinic.id,
                "destination_clinic_id": second_clinic.id,
                "quantity": 0,
                "requested_by_id": staff.id,
            },
        )

        _assert_error(response, 400)

    def test_rejects_insufficient_stock(
        self,
        client,
        clinic,
        second_clinic,
        inventory_item,
        admin_staff_and_headers,
    ):
        staff, headers = admin_staff_and_headers

        response = client.post(
            "/api/inventory/transfers",
            headers=headers,
            json={
                "item_id": inventory_item.id,
                "source_clinic_id": clinic.id,
                "destination_clinic_id": second_clinic.id,
                "quantity": 999999,
                "requested_by_id": staff.id,
            },
        )

        _assert_error(response, 400)


class TestApproveInventoryTransferRoute:
    def test_admin_can_approve(
        self,
        client,
        clinic,
        inventory_transfer,
        admin_staff_and_headers,
        make_authenticated_staff,
    ):
        _requester, _requester_headers = admin_staff_and_headers

        approver = make_authenticated_staff(
            clinic,
            Role.ADMIN,
            first_name="Approving",
            last_name="Admin",
        )

        approving_staff, approving_headers = approver

        response = client.post(
            f"/api/inventory/transfers/{inventory_transfer.id}/approve",
            headers=approving_headers,
            json={
                "approved_by_id": approving_staff.id,
            },
        )

        data = _assert_success(response, 200)

        assert data["id"] == inventory_transfer.id
        assert data["status"] == InventoryTransferStatus.APPROVED.value
        assert data["approved_by_id"] == approving_staff.id

    def test_pharmacist_can_approve(
        self,
        client,
        clinic,
        inventory_transfer,
        pharmacist_staff_and_headers,
        make_authenticated_staff,
    ):
        _requester, _requester_headers = pharmacist_staff_and_headers

        approver_staff, approver_headers = make_authenticated_staff(
            clinic,
            Role.PHARMACIST,
            first_name="Approving",
            last_name="Pharmacist",
        )

        response = client.post(
            f"/api/inventory/transfers/{inventory_transfer.id}/approve",
            headers=approver_headers,
            json={
                "approved_by_id": approver_staff.id,
            },
        )

        data = _assert_success(response, 200)

        assert data["status"] == InventoryTransferStatus.APPROVED.value
        assert data["approved_by_id"] == approver_staff.id

    def test_requester_cannot_approve_own_transfer(
        self,
        client,
        inventory_transfer,
        admin_staff_and_headers,
    ):
        staff, headers = admin_staff_and_headers

        response = client.post(
            f"/api/inventory/transfers/{inventory_transfer.id}/approve",
            headers=headers,
            json={
                "approved_by_id": staff.id,
            },
        )

        _assert_error(response, 400)

    def test_requires_approved_by_id(
        self,
        client,
        inventory_transfer,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.post(
            f"/api/inventory/transfers/{inventory_transfer.id}/approve",
            headers=headers,
            json={},
        )

        _assert_error(response, 400)

    def test_cannot_approve_twice(
        self,
        client,
        clinic,
        inventory_transfer,
        admin_staff_and_headers,
        make_authenticated_staff,
    ):
        _requester, _requester_headers = admin_staff_and_headers

        approver1, headers1 = make_authenticated_staff(
            clinic,
            Role.ADMIN,
            first_name="First",
            last_name="Approver",
        )

        response = client.post(
            f"/api/inventory/transfers/{inventory_transfer.id}/approve",
            headers=headers1,
            json={"approved_by_id": approver1.id},
        )

        _assert_success(response, 200)

        approver2, headers2 = make_authenticated_staff(
            clinic,
            Role.ADMIN,
            first_name="Second",
            last_name="Approver",
        )

        response = client.post(
            f"/api/inventory/transfers/{inventory_transfer.id}/approve",
            headers=headers2,
            json={"approved_by_id": approver2.id},
        )

        _assert_error(response, 400)


class TestCompleteInventoryTransferRoute:
    def test_admin_can_complete(
        self,
        client,
        clinic,
        inventory_transfer,
        admin_staff_and_headers,
        make_authenticated_staff,
    ):
        requester, _requester_headers = admin_staff_and_headers

        approver, approver_headers = make_authenticated_staff(
            clinic,
            Role.ADMIN,
            first_name="Approver",
            last_name="Admin",
        )

        response = client.post(
            f"/api/inventory/transfers/{inventory_transfer.id}/approve",
            headers=approver_headers,
            json={
                "approved_by_id": approver.id,
            },
        )

        _assert_success(response, 200)

        performer, performer_headers = make_authenticated_staff(
            clinic,
            Role.ADMIN,
            first_name="Completing",
            last_name="Admin",
        )

        response = client.post(
            f"/api/inventory/transfers/{inventory_transfer.id}/complete",
            headers=performer_headers,
            json={
                "performed_by_id": performer.id,
            },
        )

        data = _assert_success(response, 200)

        assert data["id"] == inventory_transfer.id
        assert data["status"] == InventoryTransferStatus.COMPLETED.value
        assert data["completed_at"] is not None

        assert requester.id == inventory_transfer.requested_by_id

    def test_pharmacist_can_complete(
        self,
        client,
        clinic,
        inventory_transfer,
        make_authenticated_staff,
    ):
        approver, approver_headers = make_authenticated_staff(
            clinic,
            Role.PHARMACIST,
            first_name="Approver",
            last_name="Pharmacist",
        )

        response = client.post(
            f"/api/inventory/transfers/{inventory_transfer.id}/approve",
            headers=approver_headers,
            json={
                "approved_by_id": approver.id,
            },
        )

        _assert_success(response, 200)

        performer, performer_headers = make_authenticated_staff(
            clinic,
            Role.PHARMACIST,
            first_name="Completing",
            last_name="Pharmacist",
        )

        response = client.post(
            f"/api/inventory/transfers/{inventory_transfer.id}/complete",
            headers=performer_headers,
            json={
                "performed_by_id": performer.id,
            },
        )

        data = _assert_success(response, 200)

        assert data["status"] == InventoryTransferStatus.COMPLETED.value

    def test_cannot_complete_pending_transfer(
        self,
        client,
        inventory_transfer,
        admin_staff_and_headers,
    ):
        staff, headers = admin_staff_and_headers

        response = client.post(
            f"/api/inventory/transfers/{inventory_transfer.id}/complete",
            headers=headers,
            json={
                "performed_by_id": staff.id,
            },
        )

        _assert_error(response, 400)

    def test_requires_performed_by_id(
        self,
        client,
        inventory_transfer,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.post(
            f"/api/inventory/transfers/{inventory_transfer.id}/complete",
            headers=headers,
            json={},
        )

        _assert_error(response, 400)


class TestCancelInventoryTransferRoute:
    def test_admin_can_cancel(
        self,
        client,
        inventory_transfer,
        admin_staff_and_headers,
    ):
        staff, headers = admin_staff_and_headers

        response = client.post(
            f"/api/inventory/transfers/{inventory_transfer.id}/cancel",
            headers=headers,
            json={
                "cancelled_by_id": staff.id,
                "reason": "Transfer no longer required",
            },
        )

        data = _assert_success(response, 200)

        assert data["id"] == inventory_transfer.id
        assert data["status"] == InventoryTransferStatus.CANCELLED.value
        assert data["cancelled_at"] is not None
        assert data["reason"] == "Transfer no longer required"

    def test_pharmacist_can_cancel(
        self,
        client,
        inventory_transfer,
        pharmacist_staff_and_headers,
    ):
        staff, headers = pharmacist_staff_and_headers

        response = client.post(
            f"/api/inventory/transfers/{inventory_transfer.id}/cancel",
            headers=headers,
            json={
                "cancelled_by_id": staff.id,
                "reason": "Cancelled by pharmacy",
            },
        )

        data = _assert_success(response, 200)

        assert data["status"] == InventoryTransferStatus.CANCELLED.value

    def test_cancel_can_update_reason(
        self,
        client,
        inventory_transfer,
        admin_staff_and_headers,
    ):
        staff, headers = admin_staff_and_headers

        response = client.post(
            f"/api/inventory/transfers/{inventory_transfer.id}/cancel",
            headers=headers,
            json={
                "cancelled_by_id": staff.id,
                "reason": "Updated cancellation reason",
            },
        )

        data = _assert_success(response, 200)

        assert data["reason"] == "Updated cancellation reason"

    def test_requires_cancelled_by_id(
        self,
        client,
        inventory_transfer,
        admin_staff_and_headers,
    ):
        _staff, headers = admin_staff_and_headers

        response = client.post(
            f"/api/inventory/transfers/{inventory_transfer.id}/cancel",
            headers=headers,
            json={},
        )

        _assert_error(response, 400)

    def test_cannot_cancel_completed_transfer(
        self,
        client,
        clinic,
        second_clinic,
        inventory_item,
        admin_staff_and_headers,
        make_authenticated_staff,
    ):
        _requester, _requester_headers = admin_staff_and_headers

        transfer = InventoryTransfer(
            item_id=inventory_item.id,
            source_clinic_id=clinic.id,
            destination_clinic_id=second_clinic.id,
            quantity=10,
            status=InventoryTransferStatus.COMPLETED,
            reason="Already completed",
            requested_by_id=_requester.id,
        )

        from app.extensions import db

        db.session.add(transfer)
        db.session.commit()

        staff, headers = make_authenticated_staff(
            clinic,
            Role.ADMIN,
            first_name="Cancelling",
            last_name="Admin",
        )

        response = client.post(
            f"/api/inventory/transfers/{transfer.id}/cancel",
            headers=headers,
            json={
                "cancelled_by_id": staff.id,
                "reason": "Too late",
            },
        )

        _assert_error(response, 400)


# ============================================================================
# GENERAL AUTHORIZATION
# ============================================================================


class TestInventoryAuthorization:
    def test_inventory_item_list_allows_pharmacist(
        self,
        client,
        clinic,
        pharmacist_staff_and_headers,
    ):
        _staff, headers = pharmacist_staff_and_headers

        response = client.get(
            f"/api/inventory/items?clinic_id={clinic.id}",
            headers=headers,
        )

        assert response.status_code == 200

    def test_inventory_item_create_allows_pharmacist(
        self,
        client,
        clinic,
        pharmacist_staff_and_headers,
    ):
        staff, headers = pharmacist_staff_and_headers

        response = client.post(
            "/api/inventory/items",
            headers=headers,
            json={
                "clinic_id": clinic.id,
                "name": "Pharmacist Created Item",
                "initial_quantity": 0,
            },
        )

        assert response.status_code == 201

    def test_supplier_update_is_admin_only(
        self,
        client,
        clinic,
        supplier,
        pharmacist_staff_and_headers,
    ):
        _staff, headers = pharmacist_staff_and_headers

        response = client.patch(
            f"/api/inventory/suppliers/{supplier.id}"
            f"?clinic_id={clinic.id}",
            headers=headers,
            json={
                "name": "Should Not Update",
            },
        )

        assert response.status_code == 403

    def test_supplier_deactivate_is_admin_only(
        self,
        client,
        clinic,
        supplier,
        pharmacist_staff_and_headers,
    ):
        _staff, headers = pharmacist_staff_and_headers

        response = client.post(
            f"/api/inventory/suppliers/{supplier.id}/deactivate"
            f"?clinic_id={clinic.id}",
            headers=headers,
        )

        assert response.status_code == 403

    def test_supplier_reactivate_is_admin_only(
        self,
        client,
        clinic,
        inactive_supplier,
        pharmacist_staff_and_headers,
    ):
        _staff, headers = pharmacist_staff_and_headers

        response = client.post(
            f"/api/inventory/suppliers/{inactive_supplier.id}/reactivate"
            f"?clinic_id={clinic.id}",
            headers=headers,
        )

        assert response.status_code == 403

    def test_item_deactivate_is_admin_only(
        self,
        client,
        clinic,
        inventory_item,
        pharmacist_staff_and_headers,
    ):
        _staff, headers = pharmacist_staff_and_headers

        response = client.post(
            f"/api/inventory/items/{inventory_item.id}/deactivate"
            f"?clinic_id={clinic.id}",
            headers=headers,
        )

        assert response.status_code == 403

    def test_item_reactivate_is_admin_only(
        self,
        client,
        clinic,
        inactive_inventory_item,
        pharmacist_staff_and_headers,
    ):
        _staff, headers = pharmacist_staff_and_headers

        response = client.post(
            f"/api/inventory/items/{inactive_inventory_item.id}/reactivate"
            f"?clinic_id={clinic.id}",
            headers=headers,
        )

        assert response.status_code == 403