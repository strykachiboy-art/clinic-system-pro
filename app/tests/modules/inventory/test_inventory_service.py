from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.enums.clinic_enums import ClinicStatus
from app.core.enums.inventory_enums import (
    InventoryCategory,
    InventoryTransferStatus,
    StockMovementDirection,
    StockMovementType,
)
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.inventory.models.inventory_model import (
    InventoryBatch,
    InventoryItem,
    InventorySupplier,
    InventoryTransfer,
    StockMovement,
)
from app.modules.inventory.services import inventory_service


# ============================================================================
# FIXTURES / HELPERS
# ============================================================================


@pytest.fixture(autouse=True)
def disable_audit_side_effects(monkeypatch):
    """
    Inventory service tests focus on inventory behavior.

    Audit creation is tested by the audit module itself, so keep it out of
    these tests to avoid unrelated audit persistence affecting assertions.
    """
    monkeypatch.setattr(
        inventory_service,
        "create_audit_log",
        lambda *args, **kwargs: None,
    )


@pytest.fixture()
def inventory_item(db, clinic):
    item = InventoryItem(
        clinic_id=clinic.id,
        name="Paracetamol",
        category=InventoryCategory.MEDICAL_SUPPLY,
        sku="PAR-001",
        barcode="123456789",
        unit="box",
        quantity_on_hand=100,
        reorder_level=10,
        is_active=True,
    )
    db.session.add(item)
    db.session.commit()
    return item


@pytest.fixture()
def second_inventory_item(db, clinic):
    item = InventoryItem(
        clinic_id=clinic.id,
        name="Surgical Gloves",
        category=InventoryCategory.CONSUMABLE,
        sku="GLV-001",
        unit="box",
        quantity_on_hand=50,
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
        quantity_on_hand=5,
        reorder_level=10,
        is_active=False,
    )
    db.session.add(item)
    db.session.commit()
    return item


@pytest.fixture()
def inventory_supplier(db, clinic):
    supplier = InventorySupplier(
        clinic_id=clinic.id,
        name="Test Medical Supplier",
        contact_person="John Supplier",
        phone="08000000000",
        email="supplier@test.com",
        address="Test Address",
        is_active=True,
    )
    db.session.add(supplier)
    db.session.commit()
    return supplier


@pytest.fixture()
def global_inventory_supplier(db):
    supplier = InventorySupplier(
        clinic_id=None,
        name="Global Medical Supplier",
        contact_person="Global Contact",
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
        quantity_on_hand=50,
        unit_cost=Decimal("100.00"),
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
        quantity_on_hand=20,
        unit_cost=Decimal("150.00"),
        expiry_date=date.today() + timedelta(days=30),
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
        quantity_on_hand=10,
        unit_cost=Decimal("75.00"),
        expiry_date=date.today() + timedelta(days=30),
        is_active=False,
    )
    db.session.add(batch)
    db.session.commit()
    return batch


@pytest.fixture()
def source_clinic(make_clinic):
    return make_clinic(name="Source Clinic")


@pytest.fixture()
def destination_clinic(make_clinic):
    return make_clinic(name="Destination Clinic")


@pytest.fixture()
def source_staff(make_staff, source_clinic):
    return make_staff(
        source_clinic,
        role=Role.ADMIN,
    )


@pytest.fixture()
def second_source_staff(make_staff, source_clinic):
    return make_staff(
        source_clinic,
        role=Role.ADMIN,
        first_name="Second",
        last_name="Staff",
    )


@pytest.fixture()
def destination_staff(make_staff, destination_clinic):
    return make_staff(
        destination_clinic,
        role=Role.ADMIN,
    )


# ============================================================================
# INVENTORY ITEM HELPERS
# ============================================================================


class TestInventoryItemHelpers:
    def test_get_inventory_item_returns_item(self, inventory_item):
        result = inventory_service.get_inventory_item(
            inventory_item.id,
        )

        assert result.id == inventory_item.id
        assert result.name == "Paracetamol"

    def test_get_inventory_item_filters_by_clinic(
        self,
        inventory_item,
        make_clinic,
    ):
        other_clinic = make_clinic(name="Other Clinic")

        with pytest.raises(ValidationError):
            inventory_service.get_inventory_item(
                inventory_item.id,
                clinic_id=other_clinic.id,
            )

    def test_get_inventory_item_not_found(self):
        with pytest.raises(NotFoundError):
            inventory_service.get_inventory_item(999999)


# ============================================================================
# INVENTORY ITEMS
# ============================================================================


class TestCreateInventoryItem:
    def test_create_inventory_item_with_defaults(
        self,
        clinic,
    ):
        item = inventory_service.create_inventory_item(
            clinic_id=clinic.id,
            name="  Examination Gloves  ",
        )

        assert item.id is not None
        assert item.name == "Examination Gloves"
        assert item.category == InventoryCategory.MEDICAL_SUPPLY
        assert item.quantity_on_hand == 0

    def test_create_inventory_item_with_fields(
        self,
        clinic,
        staff,
    ):
        item = inventory_service.create_inventory_item(
            clinic_id=clinic.id,
            name="Syringe",
            category=InventoryCategory.CONSUMABLE,
            initial_quantity=20,
            performed_by_id=staff.id,
            sku=" SYR-001 ",
            barcode=" BAR-001 ",
            unit="piece",
            reorder_level=5,
        )

        assert item.name == "Syringe"
        assert item.category == InventoryCategory.CONSUMABLE
        assert item.quantity_on_hand == 20
        assert item.sku == "SYR-001"
        assert item.barcode == "BAR-001"
        assert item.unit == "piece"
        assert item.reorder_level == 5

    def test_create_inventory_item_requires_name(
        self,
        clinic,
    ):
        with pytest.raises(ValidationError):
            inventory_service.create_inventory_item(
                clinic_id=clinic.id,
                name="   ",
            )

    def test_create_inventory_item_rejects_negative_initial_quantity(
        self,
        clinic,
    ):
        with pytest.raises(ValidationError):
            inventory_service.create_inventory_item(
                clinic_id=clinic.id,
                name="Syringe",
                initial_quantity=-1,
            )

    def test_create_inventory_item_rejects_unknown_fields(
        self,
        clinic,
    ):
        with pytest.raises(ValidationError):
            inventory_service.create_inventory_item(
                clinic_id=clinic.id,
                name="Syringe",
                invalid_field="value",
            )

    def test_create_inventory_item_rejects_negative_reorder_level(
        self,
        clinic,
    ):
        with pytest.raises(ValidationError):
            inventory_service.create_inventory_item(
                clinic_id=clinic.id,
                name="Syringe",
                reorder_level=-1,
            )

    def test_create_inventory_item_rejects_duplicate_sku(
        self,
        clinic,
        inventory_item,
    ):
        with pytest.raises(ConflictError):
            inventory_service.create_inventory_item(
                clinic_id=clinic.id,
                name="Another Item",
                sku=inventory_item.sku,
            )

    def test_create_inventory_item_rejects_duplicate_barcode(
        self,
        clinic,
        inventory_item,
    ):
        with pytest.raises(ConflictError):
            inventory_service.create_inventory_item(
                clinic_id=clinic.id,
                name="Another Item",
                barcode=inventory_item.barcode,
            )

    def test_create_inventory_item_initial_quantity_requires_staff(
        self,
        clinic,
    ):
        with pytest.raises(ValidationError):
            inventory_service.create_inventory_item(
                clinic_id=clinic.id,
                name="Syringe",
                initial_quantity=10,
            )

    def test_create_inventory_item_initial_quantity_requires_active_staff(
        self,
        clinic,
        make_staff,
    ):
        suspended_staff = make_staff(
            clinic,
            status=StaffStatus.SUSPENDED,
        )

        with pytest.raises(ConflictError):
            inventory_service.create_inventory_item(
                clinic_id=clinic.id,
                name="Syringe",
                initial_quantity=10,
                performed_by_id=suspended_staff.id,
            )

    def test_create_inventory_item_initial_quantity_requires_same_clinic_staff(
        self,
        clinic,
        make_clinic,
        make_staff,
    ):
        other_clinic = make_clinic(name="Other Clinic")
        other_staff = make_staff(other_clinic)

        with pytest.raises(ValidationError):
            inventory_service.create_inventory_item(
                clinic_id=clinic.id,
                name="Syringe",
                initial_quantity=10,
                performed_by_id=other_staff.id,
            )

    def test_create_inventory_item_with_positive_quantity_creates_restock_movement(
        self,
        clinic,
        staff,
        db,
    ):
        """
        This test intentionally protects the enum/service contract.

        StockMovementType.RESTOCK exists in the inventory enum. The service
        must use RESTOCK when recording the initial inventory quantity.
        """
        item = inventory_service.create_inventory_item(
            clinic_id=clinic.id,
            name="Syringe",
            initial_quantity=10,
            performed_by_id=staff.id,
        )

        movement = StockMovement.query.filter_by(
            item_id=item.id,
        ).one()

        assert movement.movement_type == StockMovementType.RESTOCK
        assert movement.direction == StockMovementDirection.IN
        assert movement.quantity == 10
        assert movement.reason == "Initial inventory quantity"
        assert movement.performed_by_id == staff.id
        assert movement.reference_type == "inventory_item"
        assert movement.reference_id == item.id

    def test_create_inventory_item_rejects_inactive_clinic(
        self,
        suspended_clinic,
    ):
        with pytest.raises(ConflictError):
            inventory_service.create_inventory_item(
                clinic_id=suspended_clinic.id,
                name="Syringe",
            )


class TestListInventoryItems:
    def test_list_inventory_items_returns_active_items(
        self,
        clinic,
        inventory_item,
        inactive_inventory_item,
    ):
        result = inventory_service.list_inventory_items(
            clinic_id=clinic.id,
        )

        assert inventory_item in result
        assert inactive_inventory_item not in result

    def test_list_inventory_items_can_include_inactive(
        self,
        clinic,
        inventory_item,
        inactive_inventory_item,
    ):
        result = inventory_service.list_inventory_items(
            clinic_id=clinic.id,
            include_inactive=True,
        )

        assert inventory_item in result
        assert inactive_inventory_item in result

    def test_list_inventory_items_filters_category(
        self,
        clinic,
        inventory_item,
        second_inventory_item,
    ):
        result = inventory_service.list_inventory_items(
            clinic_id=clinic.id,
            category=InventoryCategory.CONSUMABLE,
        )

        assert second_inventory_item in result
        assert inventory_item not in result

    def test_list_inventory_items_filters_low_stock(
        self,
        clinic,
        inventory_item,
        second_inventory_item,
    ):
        inventory_item.quantity_on_hand = 5
        inventory_item.reorder_level = 10

        second_inventory_item.quantity_on_hand = 50
        second_inventory_item.reorder_level = 10

        from app.extensions import db

        db.session.commit()

        result = inventory_service.list_inventory_items(
            clinic_id=clinic.id,
            low_stock_only=True,
        )

        assert inventory_item in result
        assert second_inventory_item not in result

    def test_list_inventory_items_sorts_by_name(
        self,
        clinic,
        inventory_item,
        second_inventory_item,
    ):
        inventory_item.name = "Zinc"
        second_inventory_item.name = "Aspirin"

        from app.extensions import db

        db.session.commit()

        result = inventory_service.list_inventory_items(
            clinic_id=clinic.id,
        )

        assert result[0].name == "Aspirin"
        assert result[1].name == "Zinc"

    def test_list_inventory_items_rejects_inactive_clinic(
        self,
        suspended_clinic,
    ):
        with pytest.raises(ConflictError):
            inventory_service.list_inventory_items(
                clinic_id=suspended_clinic.id,
            )


class TestGetLowStockItems:
    def test_get_low_stock_items_returns_only_low_stock(
        self,
        clinic,
        inventory_item,
        second_inventory_item,
    ):
        inventory_item.quantity_on_hand = 5
        inventory_item.reorder_level = 10

        second_inventory_item.quantity_on_hand = 50
        second_inventory_item.reorder_level = 10

        from app.extensions import db

        db.session.commit()

        result = inventory_service.get_low_stock_items(
            clinic.id,
        )

        assert inventory_item in result
        assert second_inventory_item not in result


class TestUpdateInventoryItem:
    def test_update_inventory_item_updates_fields(
        self,
        inventory_item,
    ):
        updated = inventory_service.update_inventory_item(
            inventory_item.id,
            name="  Updated Paracetamol ",
            sku=" NEW-SKU ",
            barcode=" NEW-BARCODE ",
            unit="pack",
            reorder_level=20,
            category=InventoryCategory.CONSUMABLE,
        )

        assert updated.name == "Updated Paracetamol"
        assert updated.sku == "NEW-SKU"
        assert updated.barcode == "NEW-BARCODE"
        assert updated.unit == "pack"
        assert updated.reorder_level == 20
        assert updated.category == InventoryCategory.CONSUMABLE

    def test_update_inventory_item_rejects_unknown_field(
        self,
        inventory_item,
    ):
        with pytest.raises(ValidationError):
            inventory_service.update_inventory_item(
                inventory_item.id,
                invalid_field="value",
            )

    def test_update_inventory_item_rejects_empty_name(
        self,
        inventory_item,
    ):
        with pytest.raises(ValidationError):
            inventory_service.update_inventory_item(
                inventory_item.id,
                name="   ",
            )

    def test_update_inventory_item_rejects_negative_reorder_level(
        self,
        inventory_item,
    ):
        with pytest.raises(ValidationError):
            inventory_service.update_inventory_item(
                inventory_item.id,
                reorder_level=-1,
            )

    def test_update_inventory_item_rejects_duplicate_sku(
        self,
        inventory_item,
        second_inventory_item,
    ):
        with pytest.raises(ConflictError):
            inventory_service.update_inventory_item(
                inventory_item.id,
                sku=second_inventory_item.sku,
            )

    def test_update_inventory_item_rejects_duplicate_barcode(
        self,
        inventory_item,
        second_inventory_item,
    ):
        second_inventory_item.barcode = "SECOND-BARCODE"

        from app.extensions import db

        db.session.commit()

        with pytest.raises(ConflictError):
            inventory_service.update_inventory_item(
                inventory_item.id,
                barcode=second_inventory_item.barcode,
            )

    def test_update_inventory_item_can_clear_optional_text(
        self,
        inventory_item,
    ):
        updated = inventory_service.update_inventory_item(
            inventory_item.id,
            sku="   ",
            barcode="   ",
            unit="   ",
        )

        assert updated.sku is None
        assert updated.barcode is None
        assert updated.unit is None


class TestInventoryItemStatus:
    def test_deactivate_inventory_item(
        self,
        inventory_item,
    ):
        result = inventory_service.deactivate_inventory_item(
            inventory_item.id,
        )

        assert result.is_active is False

    def test_deactivate_inventory_item_is_idempotent(
        self,
        inventory_item,
    ):
        inventory_item.is_active = False

        from app.extensions import db

        db.session.commit()

        result = inventory_service.deactivate_inventory_item(
            inventory_item.id,
        )

        assert result.is_active is False

    def test_reactivate_inventory_item(
        self,
        inventory_item,
    ):
        inventory_item.is_active = False

        from app.extensions import db

        db.session.commit()

        result = inventory_service.reactivate_inventory_item(
            inventory_item.id,
        )

        assert result.is_active is True

    def test_reactivate_inventory_item_is_idempotent(
        self,
        inventory_item,
    ):
        result = inventory_service.reactivate_inventory_item(
            inventory_item.id,
        )

        assert result.is_active is True

    def test_reactivate_inventory_item_rejects_inactive_clinic(
        self,
        inventory_item,
        suspended_clinic,
    ):
        inventory_item.clinic_id = suspended_clinic.id
        inventory_item.is_active = False

        from app.extensions import db

        db.session.commit()

        with pytest.raises(ConflictError):
            inventory_service.reactivate_inventory_item(
                inventory_item.id,
            )


# ============================================================================
# SUPPLIERS
# ============================================================================


class TestSupplierHelpers:
    def test_get_supplier_returns_supplier(
        self,
        inventory_supplier,
    ):
        result = inventory_service.get_supplier(
            inventory_supplier.id,
        )

        assert result.id == inventory_supplier.id

    def test_get_supplier_not_found(self):
        with pytest.raises(NotFoundError):
            inventory_service.get_supplier(999999)

    def test_get_supplier_rejects_wrong_clinic(
        self,
        inventory_supplier,
        make_clinic,
    ):
        other_clinic = make_clinic(name="Other Clinic")

        with pytest.raises(ValidationError):
            inventory_service.get_supplier(
                inventory_supplier.id,
                clinic_id=other_clinic.id,
            )

    def test_get_global_supplier_allowed_for_clinic(
        self,
        global_inventory_supplier,
        clinic,
    ):
        result = inventory_service.get_supplier(
            global_inventory_supplier.id,
            clinic_id=clinic.id,
        )

        assert result.id == global_inventory_supplier.id


class TestCreateSupplier:
    def test_create_clinic_supplier(
        self,
        clinic,
    ):
        supplier = inventory_service.create_supplier(
            name="  New Supplier  ",
            clinic_id=clinic.id,
            contact_person="  Jane ",
            phone=" 08000000000 ",
            email=" supplier@test.com ",
            address=" Test Address ",
        )

        assert supplier.name == "New Supplier"
        assert supplier.clinic_id == clinic.id
        assert supplier.contact_person == "Jane"
        assert supplier.phone == "08000000000"
        assert supplier.email == "supplier@test.com"
        assert supplier.address == "Test Address"

    def test_create_global_supplier(
        self,
    ):
        supplier = inventory_service.create_supplier(
            name="Global Supplier",
        )

        assert supplier.clinic_id is None

    def test_create_supplier_requires_name(
        self,
        clinic,
    ):
        with pytest.raises(ValidationError):
            inventory_service.create_supplier(
                name="   ",
                clinic_id=clinic.id,
            )

    def test_create_supplier_rejects_unknown_fields(
        self,
        clinic,
    ):
        with pytest.raises(ValidationError):
            inventory_service.create_supplier(
                name="Supplier",
                clinic_id=clinic.id,
                unknown_field="value",
            )

    def test_create_supplier_rejects_duplicate_clinic_supplier(
        self,
        inventory_supplier,
    ):
        with pytest.raises(ConflictError):
            inventory_service.create_supplier(
                name=inventory_supplier.name,
                clinic_id=inventory_supplier.clinic_id,
            )

    def test_create_supplier_duplicate_check_is_case_insensitive(
        self,
        inventory_supplier,
    ):
        with pytest.raises(ConflictError):
            inventory_service.create_supplier(
                name=inventory_supplier.name.upper(),
                clinic_id=inventory_supplier.clinic_id,
            )

    def test_create_supplier_rejects_duplicate_global_supplier(
        self,
        global_inventory_supplier,
        clinic,
    ):
        with pytest.raises(ConflictError):
            inventory_service.create_supplier(
                name=global_inventory_supplier.name,
                clinic_id=clinic.id,
            )

    def test_create_supplier_rejects_inactive_clinic(
        self,
        suspended_clinic,
    ):
        with pytest.raises(ConflictError):
            inventory_service.create_supplier(
                name="Supplier",
                clinic_id=suspended_clinic.id,
            )


class TestListSuppliers:
    def test_list_suppliers_returns_active_suppliers(
        self,
        clinic,
        inventory_supplier,
        global_inventory_supplier,
        inactive_inventory_supplier,
    ):
        result = inventory_service.list_suppliers(
            clinic_id=clinic.id,
        )

        assert inventory_supplier in result
        assert global_inventory_supplier in result
        assert inactive_inventory_supplier not in result

    def test_list_suppliers_can_include_inactive(
        self,
        clinic,
        inactive_inventory_supplier,
    ):
        result = inventory_service.list_suppliers(
            clinic_id=clinic.id,
            include_inactive=True,
        )

        assert inactive_inventory_supplier in result

    def test_list_suppliers_without_clinic_returns_all_active(
        self,
        inventory_supplier,
        global_inventory_supplier,
        inactive_inventory_supplier,
    ):
        result = inventory_service.list_suppliers()

        assert inventory_supplier in result
        assert global_inventory_supplier in result
        assert inactive_inventory_supplier not in result

    def test_list_suppliers_sorts_by_name(
        self,
        clinic,
        inventory_supplier,
        global_inventory_supplier,
    ):
        inventory_supplier.name = "Zulu Supplier"
        global_inventory_supplier.name = "Alpha Supplier"

        from app.extensions import db

        db.session.commit()

        result = inventory_service.list_suppliers(
            clinic_id=clinic.id,
        )

        names = [supplier.name for supplier in result]

        assert names.index("Alpha Supplier") < names.index("Zulu Supplier")


class TestUpdateSupplier:
    def test_update_supplier_fields(
        self,
        inventory_supplier,
    ):
        updated = inventory_service.update_supplier(
            inventory_supplier.id,
            name=" Updated Supplier ",
            contact_person=" New Contact ",
            phone=" 08111111111 ",
            email=" new@test.com ",
            address=" New Address ",
        )

        assert updated.name == "Updated Supplier"
        assert updated.contact_person == "New Contact"
        assert updated.phone == "08111111111"
        assert updated.email == "new@test.com"
        assert updated.address == "New Address"

    def test_update_supplier_can_update_is_active(
        self,
        inventory_supplier,
    ):
        updated = inventory_service.update_supplier(
            inventory_supplier.id,
            is_active=False,
        )

        assert updated.is_active is False

    def test_update_supplier_rejects_unknown_field(
        self,
        inventory_supplier,
    ):
        with pytest.raises(ValidationError):
            inventory_service.update_supplier(
                inventory_supplier.id,
                unknown_field="value",
            )

    def test_update_supplier_rejects_empty_name(
        self,
        inventory_supplier,
    ):
        with pytest.raises(ValidationError):
            inventory_service.update_supplier(
                inventory_supplier.id,
                name="   ",
            )

    def test_update_supplier_rejects_duplicate_name(
        self,
        inventory_supplier,
        clinic,
        db,
    ):
        second_supplier = InventorySupplier(
            clinic_id=clinic.id,
            name="Second Supplier",
            is_active=True,
        )
        db.session.add(second_supplier)
        db.session.commit()

        with pytest.raises(ConflictError):
            inventory_service.update_supplier(
                inventory_supplier.id,
                name=second_supplier.name,
            )


class TestSupplierStatus:
    def test_deactivate_supplier(
        self,
        inventory_supplier,
    ):
        result = inventory_service.deactivate_supplier(
            inventory_supplier.id,
        )

        assert result.is_active is False

    def test_deactivate_supplier_is_idempotent(
        self,
        inventory_supplier,
    ):
        inventory_supplier.is_active = False

        from app.extensions import db

        db.session.commit()

        result = inventory_service.deactivate_supplier(
            inventory_supplier.id,
        )

        assert result.is_active is False

    def test_reactivate_supplier(
        self,
        inventory_supplier,
    ):
        inventory_supplier.is_active = False

        from app.extensions import db

        db.session.commit()

        result = inventory_service.reactivate_supplier(
            inventory_supplier.id,
        )

        assert result.is_active is True

    def test_reactivate_clinic_supplier_rejects_inactive_clinic(
        self,
        inventory_supplier,
        suspended_clinic,
    ):
        inventory_supplier.clinic_id = suspended_clinic.id
        inventory_supplier.is_active = False

        from app.extensions import db

        db.session.commit()

        with pytest.raises(ConflictError):
            inventory_service.reactivate_supplier(
                inventory_supplier.id,
            )


# ============================================================================
# INVENTORY BATCHES
# ============================================================================


class TestInventoryBatchHelpers:
    def test_get_inventory_batch(
        self,
        inventory_batch,
        inventory_item,
    ):
        result = inventory_service.get_inventory_batch(
            inventory_batch.id,
            item_id=inventory_item.id,
        )

        assert result.id == inventory_batch.id

    def test_get_inventory_batch_not_found(self):
        with pytest.raises(NotFoundError):
            inventory_service.get_inventory_batch(999999)

    def test_get_inventory_batch_rejects_wrong_item(
        self,
        inventory_batch,
        second_inventory_item,
    ):
        with pytest.raises(ValidationError):
            inventory_service.get_inventory_batch(
                inventory_batch.id,
                item_id=second_inventory_item.id,
            )

    def test_get_inventory_batch_rejects_wrong_clinic(
        self,
        inventory_batch,
        make_clinic,
    ):
        other_clinic = make_clinic(name="Other Clinic")

        with pytest.raises(ValidationError):
            inventory_service.get_inventory_batch(
                inventory_batch.id,
                clinic_id=other_clinic.id,
            )


class TestCreateInventoryBatch:
    def test_create_inventory_batch(
        self,
        inventory_item,
        inventory_supplier,
    ):
        batch = inventory_service.create_inventory_batch(
            item_id=inventory_item.id,
            batch_number="  NEW-BATCH ",
            unit_cost=Decimal("250.50"),
            expiry_date=date.today() + timedelta(days=90),
            supplier_id=inventory_supplier.id,
            clinic_id=inventory_item.clinic_id,
        )

        assert batch.id is not None
        assert batch.item_id == inventory_item.id
        assert batch.batch_number == "NEW-BATCH"
        assert batch.quantity_on_hand == 0
        assert batch.unit_cost == Decimal("250.50")
        assert batch.supplier_id == inventory_supplier.id

    def test_create_inventory_batch_requires_batch_number(
        self,
        inventory_item,
    ):
        with pytest.raises(ValidationError):
            inventory_service.create_inventory_batch(
                item_id=inventory_item.id,
                batch_number="   ",
            )

    def test_create_inventory_batch_rejects_duplicate_batch_number(
        self,
        inventory_item,
        inventory_batch,
    ):
        with pytest.raises(ConflictError):
            inventory_service.create_inventory_batch(
                item_id=inventory_item.id,
                batch_number=inventory_batch.batch_number,
            )

    def test_same_batch_number_allowed_for_different_item(
        self,
        inventory_item,
        second_inventory_item,
        inventory_batch,
    ):
        batch = inventory_service.create_inventory_batch(
            item_id=second_inventory_item.id,
            batch_number=inventory_batch.batch_number,
        )

        assert batch.item_id == second_inventory_item.id
        assert batch.batch_number == inventory_batch.batch_number

    def test_create_inventory_batch_rejects_negative_unit_cost(
        self,
        inventory_item,
    ):
        with pytest.raises(ValidationError):
            inventory_service.create_inventory_batch(
                item_id=inventory_item.id,
                batch_number="NEW-BATCH",
                unit_cost=Decimal("-1"),
            )

    def test_create_inventory_batch_rejects_expired_date(
        self,
        inventory_item,
    ):
        with pytest.raises(ValidationError):
            inventory_service.create_inventory_batch(
                item_id=inventory_item.id,
                batch_number="NEW-BATCH",
                expiry_date=date.today() - timedelta(days=1),
            )

    def test_create_inventory_batch_rejects_inactive_supplier(
        self,
        inventory_item,
        inactive_inventory_supplier,
    ):
        with pytest.raises(ConflictError):
            inventory_service.create_inventory_batch(
                item_id=inventory_item.id,
                batch_number="NEW-BATCH",
                supplier_id=inactive_inventory_supplier.id,
            )

    def test_create_inventory_batch_allows_global_supplier(
        self,
        inventory_item,
        global_inventory_supplier,
    ):
        batch = inventory_service.create_inventory_batch(
            item_id=inventory_item.id,
            batch_number="GLOBAL-BATCH",
            supplier_id=global_inventory_supplier.id,
        )

        assert batch.supplier_id == global_inventory_supplier.id

    def test_create_inventory_batch_rejects_supplier_from_other_clinic(
        self,
        inventory_item,
        make_clinic,
        make_user,
        db,
    ):
        other_clinic = make_clinic(name="Other Clinic")

        supplier = InventorySupplier(
            clinic_id=other_clinic.id,
            name="Other Clinic Supplier",
            is_active=True,
        )
        db.session.add(supplier)
        db.session.commit()

        with pytest.raises(ValidationError):
            inventory_service.create_inventory_batch(
                item_id=inventory_item.id,
                batch_number="NEW-BATCH",
                supplier_id=supplier.id,
            )

    def test_create_inventory_batch_rejects_inactive_item(
        self,
        inactive_inventory_item,
    ):
        with pytest.raises(ConflictError):
            inventory_service.create_inventory_batch(
                item_id=inactive_inventory_item.id,
                batch_number="NEW-BATCH",
            )


class TestListInventoryBatches:
    def test_list_inventory_batches_returns_active_batches(
        self,
        inventory_item,
        inventory_batch,
        inactive_inventory_batch,
    ):
        result = inventory_service.list_inventory_batches(
            item_id=inventory_item.id,
        )

        assert inventory_batch in result
        assert inactive_inventory_batch not in result

    def test_list_inventory_batches_can_include_inactive(
        self,
        inventory_item,
        inventory_batch,
        inactive_inventory_batch,
    ):
        result = inventory_service.list_inventory_batches(
            item_id=inventory_item.id,
            include_inactive=True,
        )

        assert inventory_batch in result
        assert inactive_inventory_batch in result

    def test_list_inventory_batches_sorts_by_expiry(
        self,
        inventory_item,
        inventory_batch,
        second_inventory_batch,
    ):
        result = inventory_service.list_inventory_batches(
            item_id=inventory_item.id,
        )

        assert result[0].id == second_inventory_batch.id
        assert result[1].id == inventory_batch.id


class TestUpdateInventoryBatch:
    def test_update_inventory_batch(
        self,
        inventory_batch,
    ):
        updated = inventory_service.update_inventory_batch(
            inventory_batch.id,
            batch_number=" UPDATED-BATCH ",
            unit_cost=Decimal("300.00"),
            expiry_date=date.today() + timedelta(days=120),
        )

        assert updated.batch_number == "UPDATED-BATCH"
        assert updated.unit_cost == Decimal("300.00")
        assert updated.expiry_date == date.today() + timedelta(days=120)

    def test_update_inventory_batch_rejects_unknown_field(
        self,
        inventory_batch,
    ):
        with pytest.raises(ValidationError):
            inventory_service.update_inventory_batch(
                inventory_batch.id,
                unknown_field="value",
            )

    def test_update_inventory_batch_rejects_empty_batch_number(
        self,
        inventory_batch,
    ):
        with pytest.raises(ValidationError):
            inventory_service.update_inventory_batch(
                inventory_batch.id,
                batch_number="   ",
            )

    def test_update_inventory_batch_rejects_duplicate_batch_number(
        self,
        inventory_batch,
        second_inventory_batch,
    ):
        with pytest.raises(ConflictError):
            inventory_service.update_inventory_batch(
                inventory_batch.id,
                batch_number=second_inventory_batch.batch_number,
            )

    def test_update_inventory_batch_rejects_negative_unit_cost(
        self,
        inventory_batch,
    ):
        with pytest.raises(ValidationError):
            inventory_service.update_inventory_batch(
                inventory_batch.id,
                unit_cost=Decimal("-1"),
            )

    def test_update_inventory_batch_rejects_expired_date(
        self,
        inventory_batch,
    ):
        with pytest.raises(ValidationError):
            inventory_service.update_inventory_batch(
                inventory_batch.id,
                expiry_date=date.today() - timedelta(days=1),
            )

    def test_update_inventory_batch_rejects_inactive_supplier(
        self,
        inventory_batch,
        inactive_inventory_supplier,
    ):
        with pytest.raises(ConflictError):
            inventory_service.update_inventory_batch(
                inventory_batch.id,
                supplier_id=inactive_inventory_supplier.id,
            )


class TestExpiringInventoryBatches:
    def test_list_expiring_inventory_batches(
        self,
        clinic,
        inventory_item,
        inventory_batch,
    ):
        inventory_batch.expiry_date = date.today() + timedelta(days=10)
        inventory_batch.quantity_on_hand = 10

        from app.extensions import db

        db.session.commit()

        result = inventory_service.list_expiring_inventory_batches(
            clinic_id=clinic.id,
            days=30,
        )

        assert inventory_batch in result

    def test_list_expiring_inventory_batches_excludes_batches_beyond_window(
        self,
        clinic,
        inventory_batch,
    ):
        inventory_batch.expiry_date = date.today() + timedelta(days=60)
        inventory_batch.quantity_on_hand = 10

        from app.extensions import db

        db.session.commit()

        result = inventory_service.list_expiring_inventory_batches(
            clinic_id=clinic.id,
            days=30,
        )

        assert inventory_batch not in result

    def test_list_expiring_inventory_batches_excludes_zero_stock(
        self,
        clinic,
        inventory_batch,
    ):
        inventory_batch.expiry_date = date.today() + timedelta(days=10)
        inventory_batch.quantity_on_hand = 0

        from app.extensions import db

        db.session.commit()

        result = inventory_service.list_expiring_inventory_batches(
            clinic_id=clinic.id,
            days=30,
        )

        assert inventory_batch not in result

    def test_list_expiring_inventory_batches_excludes_inactive_batch(
        self,
        clinic,
        inactive_inventory_batch,
    ):
        inactive_inventory_batch.expiry_date = date.today() + timedelta(days=10)
        inactive_inventory_batch.quantity_on_hand = 10

        from app.extensions import db

        db.session.commit()

        result = inventory_service.list_expiring_inventory_batches(
            clinic_id=clinic.id,
            days=30,
        )

        assert inactive_inventory_batch not in result

    def test_list_expiring_inventory_batches_rejects_negative_days(
        self,
        clinic,
    ):
        with pytest.raises(ValidationError):
            inventory_service.list_expiring_inventory_batches(
                clinic_id=clinic.id,
                days=-1,
            )


# ============================================================================
# STOCK MOVEMENTS
# ============================================================================


class TestResolveMovementDirection:
    @pytest.mark.parametrize(
        "movement_type",
        [
            StockMovementType.RESTOCK,
            StockMovementType.TRANSFER_IN,
        ],
    )
    def test_increasing_movements(
        self,
        movement_type,
    ):
        direction, quantity = inventory_service._resolve_movement_direction(
            movement_type,
            10,
        )

        assert direction == StockMovementDirection.IN
        assert quantity == 10

    @pytest.mark.parametrize(
        "movement_type",
        [
            StockMovementType.USAGE,
            StockMovementType.TRANSFER_OUT,
            StockMovementType.DAMAGED,
            StockMovementType.EXPIRED,
        ],
    )
    def test_decreasing_movements(
        self,
        movement_type,
    ):
        direction, quantity = inventory_service._resolve_movement_direction(
            movement_type,
            10,
        )

        assert direction == StockMovementDirection.OUT
        assert quantity == 10

    def test_positive_adjustment_is_in(
        self,
    ):
        direction, quantity = inventory_service._resolve_movement_direction(
            StockMovementType.ADJUSTMENT,
            10,
        )

        assert direction == StockMovementDirection.IN
        assert quantity == 10

    def test_negative_adjustment_is_out(
        self,
    ):
        direction, quantity = inventory_service._resolve_movement_direction(
            StockMovementType.ADJUSTMENT,
            -10,
        )

        assert direction == StockMovementDirection.OUT
        assert quantity == 10

    def test_zero_adjustment_rejected(
        self,
    ):
        with pytest.raises(ValidationError):
            inventory_service._resolve_movement_direction(
                StockMovementType.ADJUSTMENT,
                0,
            )

    def test_zero_non_adjustment_rejected(
        self,
    ):
        with pytest.raises(ValidationError):
            inventory_service._resolve_movement_direction(
                StockMovementType.RESTOCK,
                0,
            )

    def test_negative_non_adjustment_rejected(
        self,
    ):
        with pytest.raises(ValidationError):
            inventory_service._resolve_movement_direction(
                StockMovementType.RESTOCK,
                -1,
            )

    def test_non_integer_quantity_rejected(
        self,
    ):
        with pytest.raises(ValidationError):
            inventory_service._resolve_movement_direction(
                StockMovementType.RESTOCK,
                1.5,
            )


class TestRecordStockMovement:
    def test_record_restock_increases_item_stock(
        self,
        inventory_item,
        staff,
    ):
        original_quantity = inventory_item.quantity_on_hand

        movement = inventory_service.record_stock_movement(
            item_id=inventory_item.id,
            movement_type=StockMovementType.RESTOCK,
            quantity=20,
            performed_by_id=staff.id,
        )

        assert movement.direction == StockMovementDirection.IN
        assert movement.quantity == 20
        assert inventory_item.quantity_on_hand == original_quantity + 20

    def test_record_usage_decreases_item_stock(
        self,
        inventory_item,
        staff,
    ):
        original_quantity = inventory_item.quantity_on_hand

        movement = inventory_service.record_stock_movement(
            item_id=inventory_item.id,
            movement_type=StockMovementType.USAGE,
            quantity=20,
            performed_by_id=staff.id,
        )

        assert movement.direction == StockMovementDirection.OUT
        assert movement.quantity == 20
        assert inventory_item.quantity_on_hand == original_quantity - 20

    def test_record_positive_adjustment_increases_stock(
        self,
        inventory_item,
        staff,
    ):
        movement = inventory_service.record_stock_movement(
            item_id=inventory_item.id,
            movement_type=StockMovementType.ADJUSTMENT,
            quantity=15,
            performed_by_id=staff.id,
        )

        assert movement.direction == StockMovementDirection.IN
        assert movement.quantity == 15
        assert inventory_item.quantity_on_hand == 115

    def test_record_negative_adjustment_decreases_stock(
        self,
        inventory_item,
        staff,
    ):
        movement = inventory_service.record_stock_movement(
            item_id=inventory_item.id,
            movement_type=StockMovementType.ADJUSTMENT,
            quantity=-15,
            performed_by_id=staff.id,
        )

        assert movement.direction == StockMovementDirection.OUT
        assert movement.quantity == 15
        assert inventory_item.quantity_on_hand == 85

    def test_record_movement_normalizes_reason_and_reference_type(
        self,
        inventory_item,
        staff,
    ):
        movement = inventory_service.record_stock_movement(
            item_id=inventory_item.id,
            movement_type=StockMovementType.RESTOCK,
            quantity=5,
            performed_by_id=staff.id,
            reason="  New stock  ",
            reference_type="  purchase_order  ",
            reference_id=123,
        )

        assert movement.reason == "New stock"
        assert movement.reference_type == "purchase_order"
        assert movement.reference_id == 123

    def test_record_movement_with_batch_updates_batch_stock(
        self,
        inventory_item,
        inventory_batch,
        staff,
    ):
        original_item_quantity = inventory_item.quantity_on_hand
        original_batch_quantity = inventory_batch.quantity_on_hand

        movement = inventory_service.record_stock_movement(
            item_id=inventory_item.id,
            batch_id=inventory_batch.id,
            movement_type=StockMovementType.USAGE,
            quantity=10,
            performed_by_id=staff.id,
        )

        assert movement.batch_id == inventory_batch.id
        assert inventory_item.quantity_on_hand == original_item_quantity - 10
        assert inventory_batch.quantity_on_hand == original_batch_quantity - 10

    def test_record_movement_rejects_insufficient_item_stock(
        self,
        inventory_item,
        staff,
    ):
        with pytest.raises(ConflictError):
            inventory_service.record_stock_movement(
                item_id=inventory_item.id,
                movement_type=StockMovementType.USAGE,
                quantity=1000,
                performed_by_id=staff.id,
            )

    def test_record_movement_rejects_insufficient_batch_stock(
        self,
        inventory_item,
        inventory_batch,
        staff,
    ):
        with pytest.raises(ConflictError):
            inventory_service.record_stock_movement(
                item_id=inventory_item.id,
                batch_id=inventory_batch.id,
                movement_type=StockMovementType.USAGE,
                quantity=1000,
                performed_by_id=staff.id,
            )

    def test_record_movement_rejects_wrong_batch(
        self,
        inventory_item,
        second_inventory_item,
        db,
        staff,
    ):
        batch = InventoryBatch(
            item_id=second_inventory_item.id,
            batch_number="OTHER-BATCH",
            quantity_on_hand=100,
            is_active=True,
        )
        db.session.add(batch)
        db.session.commit()

        with pytest.raises(ValidationError):
            inventory_service.record_stock_movement(
                item_id=inventory_item.id,
                batch_id=batch.id,
                movement_type=StockMovementType.RESTOCK,
                quantity=10,
                performed_by_id=staff.id,
            )

    def test_record_movement_rejects_inactive_batch(
        self,
        inventory_item,
        inactive_inventory_batch,
        staff,
    ):
        with pytest.raises(ConflictError):
            inventory_service.record_stock_movement(
                item_id=inventory_item.id,
                batch_id=inactive_inventory_batch.id,
                movement_type=StockMovementType.RESTOCK,
                quantity=10,
                performed_by_id=staff.id,
            )

    def test_record_movement_rejects_inactive_staff(
        self,
        inventory_item,
        make_staff,
        clinic,
    ):
        suspended_staff = make_staff(
            clinic,
            status=StaffStatus.SUSPENDED,
        )

        with pytest.raises(ConflictError):
            inventory_service.record_stock_movement(
                item_id=inventory_item.id,
                movement_type=StockMovementType.RESTOCK,
                quantity=10,
                performed_by_id=suspended_staff.id,
            )

    def test_record_movement_rejects_staff_from_other_clinic(
        self,
        inventory_item,
        make_clinic,
        make_staff,
    ):
        other_clinic = make_clinic(name="Other Clinic")
        other_staff = make_staff(other_clinic)

        with pytest.raises(ValidationError):
            inventory_service.record_stock_movement(
                item_id=inventory_item.id,
                movement_type=StockMovementType.RESTOCK,
                quantity=10,
                performed_by_id=other_staff.id,
            )

    def test_record_movement_rejects_inactive_item(
        self,
        inactive_inventory_item,
        staff,
    ):
        with pytest.raises(ConflictError):
            inventory_service.record_stock_movement(
                item_id=inactive_inventory_item.id,
                movement_type=StockMovementType.RESTOCK,
                quantity=10,
                performed_by_id=staff.id,
            )


class TestGetStockMovements:
    def test_get_stock_movements_returns_newest_first(
        self,
        inventory_item,
        staff,
        db,
    ):
        first = inventory_service.record_stock_movement(
            item_id=inventory_item.id,
            movement_type=StockMovementType.RESTOCK,
            quantity=10,
            performed_by_id=staff.id,
        )

        second = inventory_service.record_stock_movement(
            item_id=inventory_item.id,
            movement_type=StockMovementType.USAGE,
            quantity=5,
            performed_by_id=staff.id,
        )

        # Make ordering deterministic instead of relying on timestamp
        # precision when both rows are created within the same clock tick.
        second.created_at = first.created_at + timedelta(seconds=1)
        db.session.commit()

        result = inventory_service.get_stock_movements(
            inventory_item.id,
        )

        assert result[0].id == second.id
        assert result[1].id == first.id


# ============================================================================
# INVENTORY TRANSFERS
# ============================================================================


@pytest.fixture()
def transfer_source_item(db, source_clinic):
    item = InventoryItem(
        clinic_id=source_clinic.id,
        name="Transfer Item",
        category=InventoryCategory.MEDICAL_SUPPLY,
        unit="box",
        quantity_on_hand=100,
        reorder_level=10,
        is_active=True,
    )
    db.session.add(item)
    db.session.commit()
    return item


@pytest.fixture()
def transfer_source_batch(db, transfer_source_item):
    batch = InventoryBatch(
        item_id=transfer_source_item.id,
        batch_number="TRANSFER-BATCH",
        quantity_on_hand=50,
        unit_cost=Decimal("200.00"),
        expiry_date=date.today() + timedelta(days=90),
        is_active=True,
    )

    from app.extensions import db

    db.session.add(batch)
    db.session.commit()

    return batch


@pytest.fixture()
def pending_transfer(
    transfer_source_item,
    source_clinic,
    destination_clinic,
    source_staff,
):
    return inventory_service.create_inventory_transfer(
        item_id=transfer_source_item.id,
        source_clinic_id=source_clinic.id,
        destination_clinic_id=destination_clinic.id,
        quantity=20,
        requested_by_id=source_staff.id,
        reason="  Transfer request  ",
    )


@pytest.fixture()
def approved_transfer(
    pending_transfer,
    second_source_staff,
):
    return inventory_service.approve_inventory_transfer(
        transfer_id=pending_transfer.id,
        approved_by_id=second_source_staff.id,
    )


class TestInventoryTransferHelpers:
    def test_get_inventory_transfer(
        self,
        pending_transfer,
    ):
        result = inventory_service.get_inventory_transfer(
            pending_transfer.id,
        )

        assert result.id == pending_transfer.id

    def test_get_inventory_transfer_not_found(self):
        with pytest.raises(NotFoundError):
            inventory_service.get_inventory_transfer(999999)

    def test_get_inventory_transfer_allows_source_clinic(
        self,
        pending_transfer,
        source_clinic,
    ):
        result = inventory_service.get_inventory_transfer(
            pending_transfer.id,
            clinic_id=source_clinic.id,
        )

        assert result.id == pending_transfer.id

    def test_get_inventory_transfer_allows_destination_clinic(
        self,
        pending_transfer,
        destination_clinic,
    ):
        result = inventory_service.get_inventory_transfer(
            pending_transfer.id,
            clinic_id=destination_clinic.id,
        )

        assert result.id == pending_transfer.id

    def test_get_inventory_transfer_rejects_unrelated_clinic(
        self,
        pending_transfer,
        make_clinic,
    ):
        other_clinic = make_clinic(name="Other Clinic")

        with pytest.raises(ValidationError):
            inventory_service.get_inventory_transfer(
                pending_transfer.id,
                clinic_id=other_clinic.id,
            )


class TestCreateInventoryTransfer:
    def test_create_inventory_transfer(
        self,
        transfer_source_item,
        source_clinic,
        destination_clinic,
        source_staff,
    ):
        transfer = inventory_service.create_inventory_transfer(
            item_id=transfer_source_item.id,
            source_clinic_id=source_clinic.id,
            destination_clinic_id=destination_clinic.id,
            quantity=20,
            requested_by_id=source_staff.id,
            reason="  Emergency transfer  ",
        )

        assert transfer.id is not None
        assert transfer.item_id == transfer_source_item.id
        assert transfer.source_clinic_id == source_clinic.id
        assert transfer.destination_clinic_id == destination_clinic.id
        assert transfer.quantity == 20
        assert transfer.status == InventoryTransferStatus.PENDING
        assert transfer.reason == "Emergency transfer"
        assert transfer.requested_by_id == source_staff.id

    def test_create_inventory_transfer_rejects_zero_quantity(
        self,
        transfer_source_item,
        source_clinic,
        destination_clinic,
        source_staff,
    ):
        with pytest.raises(ValidationError):
            inventory_service.create_inventory_transfer(
                item_id=transfer_source_item.id,
                source_clinic_id=source_clinic.id,
                destination_clinic_id=destination_clinic.id,
                quantity=0,
                requested_by_id=source_staff.id,
            )

    def test_create_inventory_transfer_rejects_negative_quantity(
        self,
        transfer_source_item,
        source_clinic,
        destination_clinic,
        source_staff,
    ):
        with pytest.raises(ValidationError):
            inventory_service.create_inventory_transfer(
                item_id=transfer_source_item.id,
                source_clinic_id=source_clinic.id,
                destination_clinic_id=destination_clinic.id,
                quantity=-1,
                requested_by_id=source_staff.id,
            )

    def test_create_inventory_transfer_rejects_same_clinic(
        self,
        transfer_source_item,
        source_clinic,
        source_staff,
    ):
        with pytest.raises(ValidationError):
            inventory_service.create_inventory_transfer(
                item_id=transfer_source_item.id,
                source_clinic_id=source_clinic.id,
                destination_clinic_id=source_clinic.id,
                quantity=10,
                requested_by_id=source_staff.id,
            )

    def test_create_inventory_transfer_rejects_insufficient_stock(
        self,
        transfer_source_item,
        source_clinic,
        destination_clinic,
        source_staff,
    ):
        with pytest.raises(ConflictError):
            inventory_service.create_inventory_transfer(
                item_id=transfer_source_item.id,
                source_clinic_id=source_clinic.id,
                destination_clinic_id=destination_clinic.id,
                quantity=1000,
                requested_by_id=source_staff.id,
            )

    def test_create_inventory_transfer_rejects_item_from_wrong_clinic(
        self,
        transfer_source_item,
        destination_clinic,
        source_staff,
    ):
        with pytest.raises(ValidationError):
            inventory_service.create_inventory_transfer(
                item_id=transfer_source_item.id,
                source_clinic_id=destination_clinic.id,
                destination_clinic_id=source_staff.clinic_id,
                quantity=10,
                requested_by_id=source_staff.id,
            )

    def test_create_inventory_transfer_rejects_requester_from_wrong_clinic(
        self,
        transfer_source_item,
        source_clinic,
        destination_clinic,
        destination_staff,
    ):
        with pytest.raises(ValidationError):
            inventory_service.create_inventory_transfer(
                item_id=transfer_source_item.id,
                source_clinic_id=source_clinic.id,
                destination_clinic_id=destination_clinic.id,
                quantity=10,
                requested_by_id=destination_staff.id,
            )

    def test_create_inventory_transfer_with_batch(
        self,
        transfer_source_item,
        transfer_source_batch,
        source_clinic,
        destination_clinic,
        source_staff,
    ):
        transfer = inventory_service.create_inventory_transfer(
            item_id=transfer_source_item.id,
            source_clinic_id=source_clinic.id,
            destination_clinic_id=destination_clinic.id,
            quantity=20,
            requested_by_id=source_staff.id,
            batch_id=transfer_source_batch.id,
        )

        assert transfer.batch_id == transfer_source_batch.id

    def test_create_inventory_transfer_rejects_insufficient_batch_stock(
        self,
        transfer_source_item,
        transfer_source_batch,
        source_clinic,
        destination_clinic,
        source_staff,
    ):
        with pytest.raises(ConflictError):
            inventory_service.create_inventory_transfer(
                item_id=transfer_source_item.id,
                source_clinic_id=source_clinic.id,
                destination_clinic_id=destination_clinic.id,
                quantity=100,
                requested_by_id=source_staff.id,
                batch_id=transfer_source_batch.id,
            )

    def test_create_inventory_transfer_rejects_inactive_batch(
        self,
        transfer_source_item,
        source_clinic,
        destination_clinic,
        source_staff,
        db,
    ):
        batch = InventoryBatch(
            item_id=transfer_source_item.id,
            batch_number="INACTIVE-TRANSFER-BATCH",
            quantity_on_hand=100,
            is_active=False,
        )
        db.session.add(batch)
        db.session.commit()

        with pytest.raises(ConflictError):
            inventory_service.create_inventory_transfer(
                item_id=transfer_source_item.id,
                source_clinic_id=source_clinic.id,
                destination_clinic_id=destination_clinic.id,
                quantity=10,
                requested_by_id=source_staff.id,
                batch_id=batch.id,
            )


class TestApproveInventoryTransfer:
    def test_approve_inventory_transfer(
        self,
        pending_transfer,
        second_source_staff,
    ):
        result = inventory_service.approve_inventory_transfer(
            transfer_id=pending_transfer.id,
            approved_by_id=second_source_staff.id,
        )

        assert result.status == InventoryTransferStatus.APPROVED
        assert result.approved_by_id == second_source_staff.id
        assert result.approved_at is not None

    def test_requester_cannot_approve_same_transfer(
        self,
        pending_transfer,
        source_staff,
    ):
        with pytest.raises(ValidationError):
            inventory_service.approve_inventory_transfer(
                transfer_id=pending_transfer.id,
                approved_by_id=source_staff.id,
            )

    def test_approve_transfer_rejects_non_pending(
        self,
        approved_transfer,
        second_source_staff,
    ):
        with pytest.raises(ConflictError):
            inventory_service.approve_inventory_transfer(
                transfer_id=approved_transfer.id,
                approved_by_id=second_source_staff.id,
            )

    def test_approve_transfer_rejects_staff_from_wrong_clinic(
        self,
        pending_transfer,
        destination_staff,
    ):
        with pytest.raises(ValidationError):
            inventory_service.approve_inventory_transfer(
                transfer_id=pending_transfer.id,
                approved_by_id=destination_staff.id,
            )

    def test_approve_transfer_rejects_inactive_staff(
        self,
        pending_transfer,
        make_staff,
        source_clinic,
    ):
        suspended_staff = make_staff(
            source_clinic,
            status=StaffStatus.SUSPENDED,
            first_name="Suspended",
            last_name="Approver",
        )

        with pytest.raises(ConflictError):
            inventory_service.approve_inventory_transfer(
                transfer_id=pending_transfer.id,
                approved_by_id=suspended_staff.id,
            )


class TestCompleteInventoryTransfer:
    def test_complete_transfer_moves_item_stock(
        self,
        approved_transfer,
        transfer_source_item,
        source_clinic,
        destination_clinic,
        second_source_staff,
        db,
    ):
        source_original_quantity = transfer_source_item.quantity_on_hand

        result = inventory_service.complete_inventory_transfer(
            transfer_id=approved_transfer.id,
            performed_by_id=second_source_staff.id,
        )

        assert result.status == InventoryTransferStatus.COMPLETED
        assert result.completed_at is not None

        db.session.refresh(transfer_source_item)

        assert (
            transfer_source_item.quantity_on_hand
            == source_original_quantity - approved_transfer.quantity
        )

        destination_item = InventoryItem.query.filter_by(
            clinic_id=destination_clinic.id,
            name=transfer_source_item.name,
            category=transfer_source_item.category,
        ).one()

        assert destination_item.quantity_on_hand == approved_transfer.quantity

    def test_complete_transfer_creates_source_and_destination_movements(
        self,
        approved_transfer,
        second_source_staff,
        db,
    ):
        inventory_service.complete_inventory_transfer(
            transfer_id=approved_transfer.id,
            performed_by_id=second_source_staff.id,
        )

        movements = StockMovement.query.filter_by(
            reference_type="inventory_transfer",
            reference_id=approved_transfer.id,
        ).all()

        assert len(movements) == 2

        movement_types = {
            movement.movement_type
            for movement in movements
        }

        assert StockMovementType.TRANSFER_OUT in movement_types
        assert StockMovementType.TRANSFER_IN in movement_types

    def test_complete_transfer_creates_destination_batch(
        self,
        transfer_source_item,
        transfer_source_batch,
        source_clinic,
        destination_clinic,
        source_staff,
        second_source_staff,
        db,
    ):
        transfer = inventory_service.create_inventory_transfer(
            item_id=transfer_source_item.id,
            source_clinic_id=source_clinic.id,
            destination_clinic_id=destination_clinic.id,
            quantity=20,
            requested_by_id=source_staff.id,
            batch_id=transfer_source_batch.id,
        )

        inventory_service.approve_inventory_transfer(
            transfer_id=transfer.id,
            approved_by_id=second_source_staff.id,
        )

        inventory_service.complete_inventory_transfer(
            transfer_id=transfer.id,
            performed_by_id=second_source_staff.id,
        )

        destination_item = InventoryItem.query.filter_by(
            clinic_id=destination_clinic.id,
            name=transfer_source_item.name,
            category=transfer_source_item.category,
        ).one()

        destination_batch = InventoryBatch.query.filter_by(
            item_id=destination_item.id,
            batch_number=transfer_source_batch.batch_number,
        ).one()

        assert destination_batch.quantity_on_hand == 20
        assert destination_batch.unit_cost == transfer_source_batch.unit_cost
        assert destination_batch.expiry_date == transfer_source_batch.expiry_date

    def test_complete_pending_transfer_rejected(
        self,
        pending_transfer,
        source_staff,
    ):
        with pytest.raises(ConflictError):
            inventory_service.complete_inventory_transfer(
                transfer_id=pending_transfer.id,
                performed_by_id=source_staff.id,
            )

    def test_complete_transfer_rejects_insufficient_source_stock_after_approval(
        self,
        approved_transfer,
        transfer_source_item,
        second_source_staff,
        db,
    ):
        transfer_source_item.quantity_on_hand = 0
        db.session.commit()

        with pytest.raises(ConflictError):
            inventory_service.complete_inventory_transfer(
                transfer_id=approved_transfer.id,
                performed_by_id=second_source_staff.id,
            )

    def test_complete_transfer_rejects_insufficient_source_batch_stock(
        self,
        transfer_source_item,
        transfer_source_batch,
        source_clinic,
        destination_clinic,
        source_staff,
        second_source_staff,
        db,
    ):
        transfer = inventory_service.create_inventory_transfer(
            item_id=transfer_source_item.id,
            source_clinic_id=source_clinic.id,
            destination_clinic_id=destination_clinic.id,
            quantity=20,
            requested_by_id=source_staff.id,
            batch_id=transfer_source_batch.id,
        )

        inventory_service.approve_inventory_transfer(
            transfer_id=transfer.id,
            approved_by_id=second_source_staff.id,
        )

        transfer_source_batch.quantity_on_hand = 0
        db.session.commit()

        with pytest.raises(ConflictError):
            inventory_service.complete_inventory_transfer(
                transfer_id=transfer.id,
                performed_by_id=second_source_staff.id,
            )

    def test_complete_transfer_rejects_inactive_performer(
        self,
        approved_transfer,
        make_staff,
        source_clinic,
    ):
        suspended_staff = make_staff(
            source_clinic,
            status=StaffStatus.SUSPENDED,
            first_name="Suspended",
            last_name="Performer",
        )

        with pytest.raises(ConflictError):
            inventory_service.complete_inventory_transfer(
                transfer_id=approved_transfer.id,
                performed_by_id=suspended_staff.id,
            )


class TestCancelInventoryTransfer:
    def test_cancel_pending_transfer(
        self,
        pending_transfer,
        source_staff,
    ):
        result = inventory_service.cancel_inventory_transfer(
            transfer_id=pending_transfer.id,
            cancelled_by_id=source_staff.id,
            reason="  No longer required  ",
        )

        assert result.status == InventoryTransferStatus.CANCELLED
        assert result.cancelled_at is not None
        assert result.reason == "No longer required"

    def test_cancel_transfer_without_new_reason(
        self,
        pending_transfer,
        source_staff,
    ):
        original_reason = pending_transfer.reason

        result = inventory_service.cancel_inventory_transfer(
            transfer_id=pending_transfer.id,
            cancelled_by_id=source_staff.id,
        )

        assert result.status == InventoryTransferStatus.CANCELLED
        assert result.reason == original_reason

    def test_cancel_transfer_rejects_completed_transfer(
        self,
        approved_transfer,
        second_source_staff,
    ):
        inventory_service.complete_inventory_transfer(
            transfer_id=approved_transfer.id,
            performed_by_id=second_source_staff.id,
        )

        with pytest.raises(ConflictError):
            inventory_service.cancel_inventory_transfer(
                transfer_id=approved_transfer.id,
                cancelled_by_id=second_source_staff.id,
            )

    def test_cancel_transfer_rejects_already_cancelled_transfer(
        self,
        pending_transfer,
        source_staff,
    ):
        inventory_service.cancel_inventory_transfer(
            transfer_id=pending_transfer.id,
            cancelled_by_id=source_staff.id,
        )

        with pytest.raises(ConflictError):
            inventory_service.cancel_inventory_transfer(
                transfer_id=pending_transfer.id,
                cancelled_by_id=source_staff.id,
            )

    def test_cancel_transfer_rejects_staff_from_wrong_clinic(
        self,
        pending_transfer,
        destination_staff,
    ):
        with pytest.raises(ValidationError):
            inventory_service.cancel_inventory_transfer(
                transfer_id=pending_transfer.id,
                cancelled_by_id=destination_staff.id,
            )


class TestListInventoryTransfers:
    def test_list_inventory_transfers_returns_source_transfers(
        self,
        pending_transfer,
        source_clinic,
    ):
        result = inventory_service.list_inventory_transfers(
            clinic_id=source_clinic.id,
        )

        assert pending_transfer in result

    def test_list_inventory_transfers_returns_destination_transfers(
        self,
        pending_transfer,
        destination_clinic,
    ):
        result = inventory_service.list_inventory_transfers(
            clinic_id=destination_clinic.id,
        )

        assert pending_transfer in result

    def test_list_inventory_transfers_filters_status(
        self,
        pending_transfer,
        source_clinic,
    ):
        result = inventory_service.list_inventory_transfers(
            clinic_id=source_clinic.id,
            status=InventoryTransferStatus.APPROVED,
        )

        assert pending_transfer not in result

    def test_list_inventory_transfers_can_filter_approved(
        self,
        approved_transfer,
        source_clinic,
    ):
        result = inventory_service.list_inventory_transfers(
            clinic_id=source_clinic.id,
            status=InventoryTransferStatus.APPROVED,
        )

        assert approved_transfer in result

    def test_list_inventory_transfers_sorts_newest_first(
        self,
        transfer_source_item,
        source_clinic,
        destination_clinic,
        source_staff,
        db,
    ):
        first = inventory_service.create_inventory_transfer(
            item_id=transfer_source_item.id,
            source_clinic_id=source_clinic.id,
            destination_clinic_id=destination_clinic.id,
            quantity=10,
            requested_by_id=source_staff.id,
        )

        second = inventory_service.create_inventory_transfer(
            item_id=transfer_source_item.id,
            source_clinic_id=source_clinic.id,
            destination_clinic_id=destination_clinic.id,
            quantity=15,
            requested_by_id=source_staff.id,
        )

        # Make ordering deterministic instead of relying on timestamp
        # precision when both rows are created within the same clock tick.
        second.created_at = first.created_at + timedelta(seconds=1)
        db.session.commit()

        result = inventory_service.list_inventory_transfers(
            clinic_id=source_clinic.id,
        )

        assert result[0].id == second.id
        assert result[1].id == first.id

    def test_list_inventory_transfers_rejects_inactive_clinic(
        self,
        suspended_clinic,
    ):
        with pytest.raises(ConflictError):
            inventory_service.list_inventory_transfers(
                clinic_id=suspended_clinic.id,
            )