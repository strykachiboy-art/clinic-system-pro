from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.enums.clinic_enums import ClinicStatus
from app.core.enums.inventory_enums import (
    InventoryCategory,
    InventoryTransferStatus,
    StockMovementDirection,
    StockMovementType,
)
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.inventory.models.inventory_model import (
    InventoryBatch,
    InventoryItem,
    InventorySupplier,
    InventoryTransfer,
)
import app.modules.inventory.services.inventory_service as service


@pytest.fixture(autouse=True)
def app_context(app):
    with app.app_context():
        yield


def item(**overrides):
    data = dict(id=1, clinic_id=10, name="Gloves", category=InventoryCategory.MEDICAL_SUPPLY,
                sku="SKU-1", barcode="BAR-1", unit="box", quantity_on_hand=100,
                reorder_level=10, is_active=True)
    data.update(overrides)
    return SimpleNamespace(**data)


def supplier(**overrides):
    data = dict(id=1, clinic_id=10, name="Supplier One", contact_person="John",
                phone="08000000000", email="supplier@example.com", address="Address",
                is_active=True)
    data.update(overrides)
    return SimpleNamespace(**data)


def batch(**overrides):
    data = dict(id=1, item_id=1, supplier_id=None, batch_number="BATCH-1",
                quantity_on_hand=40, unit_cost=Decimal("12.50"),
                expiry_date=date.today() + timedelta(days=30), is_active=True)
    data.update(overrides)
    return SimpleNamespace(**data)


def transfer(**overrides):
    data = dict(id=1, item_id=1, batch_id=None, source_clinic_id=10,
                destination_clinic_id=20, quantity=10, status=InventoryTransferStatus.PENDING,
                reason="Transfer", requested_by_id=5, approved_by_id=None,
                requested_at=None, approved_at=None, completed_at=None, cancelled_at=None)
    data.update(overrides)
    return SimpleNamespace(**data)


# ============================================================================
# HELPERS
# ============================================================================

def test_normalize_optional_text():
    assert service._normalize_optional_text(None) is None
    assert service._normalize_optional_text("  gloves  ") == "gloves"
    assert service._normalize_optional_text("   ") is None


def test_normalize_optional_text_rejects_non_string():
    with pytest.raises(ValidationError):
        service._normalize_optional_text(123)


@pytest.mark.parametrize("value", [0, -1, "1"])
def test_validate_positive_quantity(value):
    with pytest.raises(ValidationError):
        service._validate_positive_quantity(value)


def test_validate_positive_quantity_accepts_positive_integer():
    service._validate_positive_quantity(1)


@pytest.mark.parametrize("value", [-1, "1"])
def test_validate_non_negative(value):
    with pytest.raises(ValidationError):
        service._validate_non_negative(value, "Reorder level")


def test_validate_batch_expiry_rejects_past():
    with pytest.raises(ValidationError):
        service._validate_batch_expiry(date.today() - timedelta(days=1))


def test_validate_batch_expiry_accepts_future():
    service._validate_batch_expiry(date.today() + timedelta(days=1))


def test_get_active_clinic_missing(monkeypatch):
    monkeypatch.setattr(service.db.session, "get", Mock(return_value=None))
    with pytest.raises(NotFoundError):
        service._get_active_clinic(10)


def test_get_active_clinic_rejects_inactive(monkeypatch):
    monkeypatch.setattr(service.db.session, "get", Mock(return_value=SimpleNamespace(id=10, status=ClinicStatus.SUSPENDED)))
    with pytest.raises(ConflictError):
        service._get_active_clinic(10)


def test_get_staff_missing(monkeypatch):
    monkeypatch.setattr(service.db.session, "get", Mock(return_value=None))
    with pytest.raises(NotFoundError):
        service._get_staff(1)


def test_validate_staff_rejects_wrong_clinic(monkeypatch):
    monkeypatch.setattr(service, "_get_staff", Mock(return_value=SimpleNamespace(id=1, clinic_id=20, status=StaffStatus.ACTIVE)))
    with pytest.raises(ValidationError):
        service._validate_staff_for_clinic(staff_id=1, clinic_id=10)


def test_validate_staff_rejects_inactive(monkeypatch):
    monkeypatch.setattr(service, "_get_staff", Mock(return_value=SimpleNamespace(id=1, clinic_id=10, status=object())))
    with pytest.raises(ConflictError):
        service._validate_staff_for_clinic(staff_id=1, clinic_id=10)


def test_get_item_supplier_batch_missing(monkeypatch):
    monkeypatch.setattr(service.db.session, "get", Mock(return_value=None))
    with pytest.raises(NotFoundError):
        service._get_item(1)
    with pytest.raises(NotFoundError):
        service._get_supplier(1)
    with pytest.raises(NotFoundError):
        service._get_batch(1)


# ============================================================================
# MODERN SQLALCHEMY LOCKING
# ============================================================================

@pytest.mark.parametrize(
    "helper",
    [service._get_locked_item, service._get_locked_supplier, service._get_locked_batch, service._get_locked_transfer],
)
def test_locked_helpers_use_session_execute(monkeypatch, helper):
    row = SimpleNamespace(id=1)
    scalars = Mock(first=Mock(return_value=row))
    result = Mock(scalars=Mock(return_value=scalars))
    execute = Mock(return_value=result)
    monkeypatch.setattr(service.db.session, "execute", execute)

    assert helper(1) is row
    execute.assert_called_once()
    scalars.first.assert_called_once_with()


def test_locked_item_missing(monkeypatch):
    scalars = Mock(first=Mock(return_value=None))
    result = Mock(scalars=Mock(return_value=scalars))
    monkeypatch.setattr(service.db.session, "execute", Mock(return_value=result))
    with pytest.raises(NotFoundError):
        service._get_locked_item(1)


# ============================================================================
# ITEMS
# ============================================================================

def test_get_inventory_item_enforces_clinic(monkeypatch):
    monkeypatch.setattr(service, "_get_item", Mock(return_value=item(clinic_id=10)))
    assert service.get_inventory_item(1, clinic_id=10).clinic_id == 10
    with pytest.raises(ValidationError):
        service.get_inventory_item(1, clinic_id=20)


def test_list_inventory_items_uses_modern_select(monkeypatch):
    monkeypatch.setattr(service, "_get_active_clinic", Mock())
    scalars = Mock(all=Mock(return_value=[item()]))
    result = Mock(scalars=Mock(return_value=scalars))
    execute = Mock(return_value=result)
    monkeypatch.setattr(service.db.session, "execute", execute)

    rows = service.list_inventory_items(10, low_stock_only=True)
    assert rows == [rows[0]]
    execute.assert_called_once()


def test_low_stock_delegates():
    # Directly exercise the delegation contract without touching SQL.
    original = service.list_inventory_items
    try:
        service.list_inventory_items = Mock(return_value=[item(quantity_on_hand=1)])
        assert service.get_low_stock_items(10)[0].quantity_on_hand == 1
        service.list_inventory_items.assert_called_once_with(
            clinic_id=10, low_stock_only=True, include_inactive=False
        )
    finally:
        service.list_inventory_items = original


def test_create_item_rejects_unknown_field(monkeypatch):
    monkeypatch.setattr(service, "_get_active_clinic", Mock())
    with pytest.raises(ValidationError):
        service.create_inventory_item(10, "Gloves", bad="x")


def test_create_item_requires_actor_for_initial_stock(monkeypatch):
    monkeypatch.setattr(service, "_get_active_clinic", Mock())
    monkeypatch.setattr(service.db.session, "add", Mock())
    monkeypatch.setattr(service.db.session, "flush", Mock())
    monkeypatch.setattr(service, "create_audit_log", Mock())
    monkeypatch.setattr(service, "InventoryItem", Mock(id=1))

    with pytest.raises(ValidationError):
        service.create_inventory_item(10, "Gloves", initial_quantity=5)


def test_update_item_rejects_unknown_field(monkeypatch):
    monkeypatch.setattr(service, "_get_locked_item", Mock(return_value=item()))
    monkeypatch.setattr(service, "_get_active_clinic", Mock())
    with pytest.raises(ValidationError):
        service.update_inventory_item(1, clinic_id=10, bad="x")


def test_update_item_changes_value_and_audits(monkeypatch):
    row = item(name="Old")
    monkeypatch.setattr(service, "_get_locked_item", Mock(return_value=row))
    monkeypatch.setattr(service, "_get_active_clinic", Mock())
    audit = Mock()
    monkeypatch.setattr(service, "create_audit_log", audit)

    result = service.update_inventory_item(1, clinic_id=10, name="New")
    assert result.name == "New"
    audit.assert_called_once()


def test_deactivate_and_reactivate_item(monkeypatch):
    row = item(is_active=True)
    monkeypatch.setattr(service, "_get_locked_item", Mock(return_value=row))
    monkeypatch.setattr(service, "_get_active_clinic", Mock())
    monkeypatch.setattr(service, "create_audit_log", Mock())
    assert service.deactivate_inventory_item(1, clinic_id=10).is_active is False

    row.is_active = False
    assert service.reactivate_inventory_item(1, clinic_id=10).is_active is True


# ============================================================================
# SUPPLIERS
# ============================================================================

def test_list_suppliers_uses_modern_select(monkeypatch):
    monkeypatch.setattr(service, "_get_active_clinic", Mock())
    scalars = Mock(all=Mock(return_value=[supplier()]))
    result = Mock(scalars=Mock(return_value=scalars))
    execute = Mock(return_value=result)
    monkeypatch.setattr(service.db.session, "execute", execute)

    assert len(service.list_suppliers(10)) == 1
    execute.assert_called_once()


def test_create_supplier_rejects_duplicate(monkeypatch):
    monkeypatch.setattr(service, "_get_active_clinic", Mock())
    scalars = Mock(first=Mock(return_value=supplier()))
    result = Mock(scalars=Mock(return_value=scalars))
    monkeypatch.setattr(service.db.session, "execute", Mock(return_value=result))

    with pytest.raises(ConflictError):
        service.create_supplier("Supplier One", clinic_id=10)


def test_update_supplier_rejects_unknown_field(monkeypatch):
    monkeypatch.setattr(service, "_get_locked_supplier", Mock(return_value=supplier()))
    monkeypatch.setattr(service, "_ensure_supplier_mutation_clinic", Mock(return_value=10))
    with pytest.raises(ValidationError):
        service.update_supplier(1, clinic_id=10, bad="x")


def test_supplier_mutation_requires_clinic_for_global_supplier(monkeypatch):
    row = supplier(clinic_id=None)
    with pytest.raises(ValidationError):
        service._ensure_supplier_mutation_clinic(supplier=row, clinic_id=None)


def test_supplier_deactivate_reactivate(monkeypatch):
    row = supplier(is_active=True)
    monkeypatch.setattr(service, "_get_locked_supplier", Mock(return_value=row))
    monkeypatch.setattr(service, "_ensure_supplier_mutation_clinic", Mock(return_value=10))
    monkeypatch.setattr(service, "create_audit_log", Mock())
    assert service.deactivate_supplier(1, clinic_id=10).is_active is False
    row.is_active = False
    assert service.reactivate_supplier(1, clinic_id=10).is_active is True


# ============================================================================
# BATCHES
# ============================================================================

def test_list_batches_uses_modern_select(monkeypatch):
    monkeypatch.setattr(service, "get_inventory_item", Mock(return_value=item()))
    scalars = Mock(all=Mock(return_value=[batch()]))
    result = Mock(scalars=Mock(return_value=scalars))
    execute = Mock(return_value=result)
    monkeypatch.setattr(service.db.session, "execute", execute)

    assert len(service.list_inventory_batches(1, clinic_id=10)) == 1
    execute.assert_called_once()


def test_create_batch_rejects_duplicate(monkeypatch):
    monkeypatch.setattr(service, "_get_locked_active_item", Mock(return_value=item()))
    monkeypatch.setattr(service, "_get_active_clinic", Mock())
    scalars = Mock(first=Mock(return_value=batch()))
    result = Mock(scalars=Mock(return_value=scalars))
    monkeypatch.setattr(service.db.session, "execute", Mock(return_value=result))
    with pytest.raises(ConflictError):
        service.create_inventory_batch(1, "BATCH-1", clinic_id=10)


def test_update_batch_rejects_unknown_field(monkeypatch):
    monkeypatch.setattr(service, "_get_locked_batch", Mock(return_value=batch()))
    monkeypatch.setattr(service, "_get_locked_item", Mock(return_value=item()))
    monkeypatch.setattr(service, "_get_active_clinic", Mock())
    with pytest.raises(ValidationError):
        service.update_inventory_batch(1, clinic_id=10, bad="x")


def test_expiring_batches_uses_modern_select(monkeypatch):
    monkeypatch.setattr(service, "_get_active_clinic", Mock())
    scalars = Mock(all=Mock(return_value=[batch()]))
    result = Mock(scalars=Mock(return_value=scalars))
    execute = Mock(return_value=result)
    monkeypatch.setattr(service.db.session, "execute", execute)
    assert len(service.list_expiring_inventory_batches(10, days=30)) == 1
    execute.assert_called_once()


# ============================================================================
# STOCK MOVEMENTS
# ============================================================================

def test_adjustment_positive_is_in():
    assert service._resolve_movement_direction(StockMovementType.ADJUSTMENT, 5) == (
        StockMovementDirection.IN, 5
    )


def test_adjustment_negative_is_out():
    assert service._resolve_movement_direction(StockMovementType.ADJUSTMENT, -5) == (
        StockMovementDirection.OUT, 5
    )


def test_adjustment_zero_rejected():
    with pytest.raises(ValidationError):
        service._resolve_movement_direction(StockMovementType.ADJUSTMENT, 0)


def test_get_stock_movements_uses_modern_select(monkeypatch):
    monkeypatch.setattr(service, "get_inventory_item", Mock(return_value=item()))
    scalars = Mock(all=Mock(return_value=[SimpleNamespace(id=1)]))
    result = Mock(scalars=Mock(return_value=scalars))
    execute = Mock(return_value=result)
    monkeypatch.setattr(service.db.session, "execute", execute)
    assert len(service.get_stock_movements(1, clinic_id=10)) == 1
    execute.assert_called_once()


def test_record_stock_movement_rejects_insufficient_stock(monkeypatch):
    monkeypatch.setattr(service, "_get_locked_active_item", Mock(return_value=item(quantity_on_hand=2)))
    monkeypatch.setattr(service, "_get_active_clinic", Mock())
    monkeypatch.setattr(service, "_validate_staff_for_clinic", Mock())
    with pytest.raises(ConflictError):
        service.record_stock_movement(
            item_id=1,
            movement_type=next(iter(service.DECREASING_MOVEMENTS)),
            quantity=5,
            performed_by_id=7,
            clinic_id=10,
        )


# ============================================================================
# TRANSFERS
# ============================================================================

def test_get_transfer_missing(monkeypatch):
    monkeypatch.setattr(service.db.session, "get", Mock(return_value=None))
    with pytest.raises(NotFoundError):
        service.get_inventory_transfer(1, clinic_id=10)


def test_get_transfer_rejects_unrelated_clinic(monkeypatch):
    monkeypatch.setattr(service.db.session, "get", Mock(return_value=transfer()))
    with pytest.raises(ValidationError):
        service.get_inventory_transfer(1, clinic_id=99)


def test_list_transfers_uses_modern_select(monkeypatch):
    monkeypatch.setattr(service, "_get_active_clinic", Mock())
    scalars = Mock(all=Mock(return_value=[transfer()]))
    result = Mock(scalars=Mock(return_value=scalars))
    execute = Mock(return_value=result)
    monkeypatch.setattr(service.db.session, "execute", execute)
    assert len(service.list_inventory_transfers(10)) == 1
    execute.assert_called_once()


def test_create_transfer_rejects_same_clinic():
    with pytest.raises(ValidationError):
        service.create_inventory_transfer(
            item_id=1,
            source_clinic_id=10,
            destination_clinic_id=10,
            quantity=1,
            requested_by_id=5,
        )


def test_create_transfer_rejects_insufficient_stock(monkeypatch):
    monkeypatch.setattr(service, "_get_active_clinic", Mock(return_value=SimpleNamespace(id=10)))
    monkeypatch.setattr(service, "_get_locked_active_item", Mock(return_value=item(quantity_on_hand=2)))
    monkeypatch.setattr(service, "_validate_staff_for_clinic", Mock())
    with pytest.raises(ConflictError):
        service.create_inventory_transfer(
            item_id=1,
            source_clinic_id=10,
            destination_clinic_id=20,
            quantity=5,
            requested_by_id=5,
        )


def test_approve_transfer_rejects_non_pending(monkeypatch):
    monkeypatch.setattr(service, "_get_locked_transfer", Mock(return_value=transfer(status=InventoryTransferStatus.COMPLETED)))
    monkeypatch.setattr(service, "_get_active_clinic", Mock())
    with pytest.raises(ConflictError):
        service.approve_inventory_transfer(1, approved_by_id=7, clinic_id=10)


def test_approve_transfer_rejects_requester_as_approver(monkeypatch):
    monkeypatch.setattr(service, "_get_locked_transfer", Mock(return_value=transfer(requested_by_id=7)))
    monkeypatch.setattr(service, "_get_active_clinic", Mock())
    monkeypatch.setattr(service, "_validate_staff_for_clinic", Mock())
    with pytest.raises(ValidationError):
        service.approve_inventory_transfer(1, approved_by_id=7, clinic_id=10)


def test_cancel_transfer_rejects_completed(monkeypatch):
    monkeypatch.setattr(service, "_get_locked_transfer", Mock(return_value=transfer(status=InventoryTransferStatus.COMPLETED)))
    monkeypatch.setattr(service, "_get_active_clinic", Mock())
    with pytest.raises(ConflictError):
        service.cancel_inventory_transfer(1, cancelled_by_id=7, clinic_id=10)
