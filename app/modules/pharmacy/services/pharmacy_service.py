from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func

from app.extensions import db
from app.core.audit.services.audit_services import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.pharmacy_enums import DispenseStatus
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import transactional

from app.modules.clinic.services.clinic_service import ensure_clinic_active
from app.modules.inventory.models.inventory_model import InventorySupplier
from app.modules.pharmacy.models.pharmacy_model import (
    DispenseItem,
    DispenseRecord,
    Drug,
    DrugBatch,
)
from app.modules.prescription.models.prescription_model import (
    Prescription,
    PrescriptionItem,
)
from app.modules.staff.models.staff_model import Staff


def _utcnow():
    return datetime.now(timezone.utc)


# ============================================================================
# GETTERS
# ============================================================================

def _get_drug_or_404(drug_id: int) -> Drug:
    drug = db.session.get(Drug, drug_id)

    if drug is None:
        raise NotFoundError(
            f"Drug {drug_id} not found"
        )

    return drug


def _get_batch_or_404(batch_id: int) -> DrugBatch:
    batch = db.session.get(DrugBatch, batch_id)

    if batch is None:
        raise NotFoundError(
            f"Drug batch {batch_id} not found"
        )

    return batch


def _get_prescription_or_404(
    prescription_id: int,
) -> Prescription:
    prescription = db.session.get(
        Prescription,
        prescription_id,
    )

    if prescription is None:
        raise NotFoundError(
            f"Prescription {prescription_id} not found"
        )

    return prescription


def _get_prescription_item_or_404(
    prescription_item_id: int,
) -> PrescriptionItem:
    item = db.session.get(
        PrescriptionItem,
        prescription_item_id,
    )

    if item is None:
        raise NotFoundError(
            f"Prescription item {prescription_item_id} not found"
        )

    return item


def _get_dispense_record_or_404(
    dispense_record_id: int,
) -> DispenseRecord:
    record = db.session.get(
        DispenseRecord,
        dispense_record_id,
    )

    if record is None:
        raise NotFoundError(
            f"Dispense record {dispense_record_id} not found"
        )

    return record


# ============================================================================
# VALIDATION
# ============================================================================

def _validate_drug_catalog_scope(
    drug: Drug,
    clinic_id: int | None,
) -> None:
    """
    Global drugs may be used by any clinic.

    Clinic-specific drugs may only be used by their owning clinic.
    """

    if drug.clinic_id is None:
        return

    if clinic_id is None:
        raise ValidationError(
            "Clinic-specific drug requires a clinic context"
        )

    if drug.clinic_id != clinic_id:
        raise ValidationError(
            f"Drug {drug.id} does not belong to clinic {clinic_id}"
        )


def _validate_active_drug(drug: Drug) -> None:
    if not drug.is_active:
        raise ValidationError(
            f"Drug {drug.id} is inactive"
        )


def _validate_staff_for_pharmacy(
    staff_id: int,
    clinic_id: int,
) -> Staff:
    staff = db.session.get(
        Staff,
        staff_id,
    )

    if staff is None:
        raise NotFoundError(
            f"Staff {staff_id} not found"
        )

    if staff.clinic_id != clinic_id:
        raise ValidationError(
            f"Staff {staff_id} does not belong to clinic {clinic_id}"
        )

    if staff.status != StaffStatus.ACTIVE:
        raise ValidationError(
            f"Staff {staff_id} is not active"
        )

    if staff.user is None:
        raise ValidationError(
            f"Staff {staff_id} has no linked user account"
        )

    if not staff.user.is_active:
        raise ValidationError(
            f"User account for staff {staff_id} is inactive"
        )

    allowed_roles = {
        Role.PHARMACIST,
        Role.ADMIN,
    }

    if staff.user.role not in allowed_roles:
        raise ValidationError(
            "Staff member is not authorized for pharmacy operations"
        )

    return staff


def _validate_supplier(
    supplier_id: int | None,
) -> InventorySupplier | None:
    if supplier_id is None:
        return None

    supplier = db.session.get(
        InventorySupplier,
        supplier_id,
    )

    if supplier is None:
        raise NotFoundError(
            f"Inventory supplier {supplier_id} not found"
        )

    return supplier


def _validate_prescription_scope(
    prescription: Prescription,
    clinic_id: int,
) -> None:
    if prescription.clinic_id != clinic_id:
        raise ValidationError(
            f"Prescription {prescription.id} does not belong "
            f"to clinic {clinic_id}"
        )

    if prescription.patient is None:
        raise ValidationError(
            f"Prescription {prescription.id} has no patient"
        )

    if prescription.patient.clinic_id != clinic_id:
        raise ValidationError(
            f"Prescription {prescription.id} patient does not "
            f"belong to clinic {clinic_id}"
        )


def _validate_prescription_item_scope(
    prescription_item: PrescriptionItem,
    prescription: Prescription,
) -> None:
    if prescription_item.prescription_id != prescription.id:
        raise ValidationError(
            f"Prescription item {prescription_item.id} does not "
            f"belong to prescription {prescription.id}"
        )

    if prescription_item.drug is None:
        raise ValidationError(
            f"Prescription item {prescription_item.id} has no drug"
        )


def _validate_prescription_for_dispensing(
    prescription: Prescription,
) -> None:
    """
    Pharmacy may only dispense a prescription that is still valid.

    We intentionally inspect the enum value rather than inventing
    additional prescription states.
    """

    if prescription.status.value != "active":
        raise ValidationError(
            f"Prescription {prescription.id} is not active"
        )

    if (
        prescription.expires_at is not None
        and prescription.expires_at <= _utcnow()
    ):
        raise ValidationError(
            f"Prescription {prescription.id} has expired"
        )


def _get_dispensed_quantity_for_prescription_item(
    prescription_item_id: int,
) -> int:
    """
    Sum all non-cancelled dispensing transactions for one
    prescription item.
    """

    total = (
        db.session.query(
            func.coalesce(
                func.sum(
                    DispenseItem.quantity_dispensed
                ),
                0,
            )
        )
        .join(
            DispenseRecord,
            DispenseItem.dispense_record_id
            == DispenseRecord.id,
        )
        .filter(
            DispenseItem.prescription_item_id
            == prescription_item_id,
            DispenseRecord.status
            != DispenseStatus.CANCELLED,
        )
        .scalar()
    )

    return int(total or 0)


def _get_remaining_prescription_quantity(
    prescription_item: PrescriptionItem,
) -> int:
    if prescription_item.quantity is None:
        raise ValidationError(
            f"Prescription item {prescription_item.id} "
            f"does not specify a quantity"
        )

    if prescription_item.quantity <= 0:
        raise ValidationError(
            f"Prescription item {prescription_item.id} "
            f"has an invalid quantity"
        )

    dispensed = _get_dispensed_quantity_for_prescription_item(
        prescription_item.id
    )

    return max(
        prescription_item.quantity - dispensed,
        0,
    )


# ============================================================================
# DRUG CATALOG
# ============================================================================

def get_drug(
    drug_id: int,
) -> Drug:
    """
    Historical retrieval remains available even when the owning
    clinic is inactive or suspended.
    """

    return _get_drug_or_404(drug_id)


def list_drugs(
    clinic_id: int | None = None,
    include_inactive: bool = False,
) -> list[Drug]:
    """
    With a clinic_id:

        - global drugs are included
        - that clinic's private drugs are included
        - other clinics' private drugs are excluded

    Without a clinic_id:

        - only global drugs are returned
    """

    query = db.session.query(Drug)

    if clinic_id is None:
        query = query.filter(
            Drug.clinic_id.is_(None)
        )
    else:
        query = query.filter(
            db.or_(
                Drug.clinic_id.is_(None),
                Drug.clinic_id == clinic_id,
            )
        )

    if not include_inactive:
        query = query.filter(
            Drug.is_active.is_(True)
        )

    return (
        query
        .order_by(
            Drug.name.asc(),
            Drug.id.asc(),
        )
        .all()
    )


@transactional
def create_drug(
    name: str,
    generic_name: str | None = None,
    category=None,
    rxnorm_code: str | None = None,
    barcode: str | None = None,
    manufacturer: str | None = None,
    dosage_form: str | None = None,
    strength: str | None = None,
    unit_price=None,
    is_controlled: bool = False,
    clinic_id: int | None = None,
) -> Drug:
    """
    Create a global or clinic-specific drug.

    clinic_id=None:
        Global/shared catalog entry.

    clinic_id=<id>:
        Clinic-specific catalog entry.
    """

    if not name or not name.strip():
        raise ValidationError(
            "Drug name is required"
        )

    name = name.strip()

    if clinic_id is not None:
        ensure_clinic_active(clinic_id)

    if unit_price is not None and unit_price < 0:
        raise ValidationError(
            "Unit price cannot be negative"
        )

    if barcode:
        existing = (
            db.session.query(Drug)
            .filter(
                Drug.barcode == barcode
            )
            .first()
        )

        if existing:
            raise ConflictError(
                f"Drug barcode {barcode} already exists"
            )

    drug = Drug(
        clinic_id=clinic_id,
        name=name,
        generic_name=generic_name,
        category=category,
        rxnorm_code=rxnorm_code,
        barcode=barcode,
        manufacturer=manufacturer,
        dosage_form=dosage_form,
        strength=strength,
        unit_price=unit_price,
        is_controlled=is_controlled,
        is_active=True,
    )

    db.session.add(drug)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Drug",
        entity_id=drug.id,
        details={
            "clinic_id": clinic_id,
            "name": drug.name,
            "is_controlled": drug.is_controlled,
        },
    )

    return drug


@transactional
def update_drug(
    drug_id: int,
    **updates,
) -> Drug:
    drug = _get_drug_or_404(
        drug_id
    )

    if drug.clinic_id is not None:
        ensure_clinic_active(
            drug.clinic_id
        )

    allowed_fields = {
        "name",
        "generic_name",
        "category",
        "rxnorm_code",
        "barcode",
        "manufacturer",
        "dosage_form",
        "strength",
        "unit_price",
        "is_controlled",
    }

    unknown_fields = (
        set(updates) - allowed_fields
    )

    if unknown_fields:
        raise ValidationError(
            "Unknown drug fields: "
            + ", ".join(
                sorted(unknown_fields)
            )
        )

    if "name" in updates:
        name = updates["name"]

        if not name or not name.strip():
            raise ValidationError(
                "Drug name cannot be empty"
            )

        updates["name"] = name.strip()

    if "unit_price" in updates:
        unit_price = updates["unit_price"]

        if unit_price is not None and unit_price < 0:
            raise ValidationError(
                "Unit price cannot be negative"
            )

    if "barcode" in updates:
        barcode = updates["barcode"]

        if barcode:
            existing = (
                db.session.query(Drug)
                .filter(
                    Drug.barcode == barcode,
                    Drug.id != drug.id,
                )
                .first()
            )

            if existing:
                raise ConflictError(
                    f"Drug barcode {barcode} already exists"
                )

    for field, value in updates.items():
        setattr(
            drug,
            field,
            value,
        )

    db.session.flush()

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Drug",
        entity_id=drug.id,
        details={
            "clinic_id": drug.clinic_id,
            "updated_fields": list(
                updates.keys()
            ),
        },
    )

    return drug


@transactional
def set_drug_active_status(
    drug_id: int,
    is_active: bool,
) -> Drug:
    drug = _get_drug_or_404(
        drug_id
    )

    if drug.clinic_id is not None:
        ensure_clinic_active(
            drug.clinic_id
        )

    drug.is_active = is_active

    db.session.flush()

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Drug",
        entity_id=drug.id,
        details={
            "clinic_id": drug.clinic_id,
            "is_active": is_active,
        },
    )

    return drug


# ============================================================================
# BATCHES / INVENTORY
# ============================================================================

def get_batch(
    batch_id: int,
) -> DrugBatch:
    return _get_batch_or_404(
        batch_id
    )


def list_batches(
    drug_id: int,
    clinic_id: int | None = None,
    include_expired: bool = True,
) -> list[DrugBatch]:
    drug = _get_drug_or_404(
        drug_id
    )

    _validate_drug_catalog_scope(
        drug,
        clinic_id,
    )

    query = (
        db.session.query(DrugBatch)
        .filter(
            DrugBatch.drug_id == drug_id
        )
    )

    if clinic_id is not None:
        query = query.filter(
            DrugBatch.clinic_id == clinic_id
        )

    if not include_expired:
        query = query.filter(
            DrugBatch.expiry_date >= date.today()
        )

    return (
        query
        .order_by(
            DrugBatch.expiry_date.asc(),
            DrugBatch.id.asc(),
        )
        .all()
    )


def list_expiring_batches(
    clinic_id: int,
    days: int = 30,
) -> list[DrugBatch]:
    if days < 0:
        raise ValidationError(
            "Days cannot be negative"
        )

    today = date.today()
    expiry_limit = today + timedelta(
        days=days
    )

    return (
        db.session.query(DrugBatch)
        .filter(
            DrugBatch.clinic_id == clinic_id,
            DrugBatch.expiry_date >= today,
            DrugBatch.expiry_date <= expiry_limit,
            DrugBatch.quantity_on_hand > 0,
        )
        .order_by(
            DrugBatch.expiry_date.asc(),
            DrugBatch.id.asc(),
        )
        .all()
    )


@transactional
def add_batch(
    clinic_id: int,
    drug_id: int,
    batch_number: str,
    quantity_on_hand: int,
    expiry_date: date,
    reorder_level: int = 20,
    supplier_id: int | None = None,
) -> DrugBatch:
    ensure_clinic_active(
        clinic_id
    )

    drug = _get_drug_or_404(
        drug_id
    )

    _validate_drug_catalog_scope(
        drug,
        clinic_id,
    )

    _validate_active_drug(
        drug
    )

    if not batch_number or not batch_number.strip():
        raise ValidationError(
            "Batch number is required"
        )

    batch_number = batch_number.strip()

    if quantity_on_hand < 0:
        raise ValidationError(
            "Quantity on hand cannot be negative"
        )

    if reorder_level < 0:
        raise ValidationError(
            "Reorder level cannot be negative"
        )

    if expiry_date < date.today():
        raise ValidationError(
            "Cannot receive an already expired drug batch"
        )

    supplier = _validate_supplier(
        supplier_id
    )

    existing = (
        db.session.query(DrugBatch)
        .filter(
            DrugBatch.clinic_id == clinic_id,
            DrugBatch.drug_id == drug_id,
            DrugBatch.batch_number == batch_number,
        )
        .first()
    )

    if existing:
        raise ConflictError(
            f"Batch {batch_number} already exists for "
            f"drug {drug_id} in clinic {clinic_id}"
        )

    batch = DrugBatch(
        clinic_id=clinic_id,
        drug_id=drug_id,
        supplier_id=(
            supplier.id
            if supplier
            else None
        ),
        batch_number=batch_number,
        quantity_on_hand=quantity_on_hand,
        reorder_level=reorder_level,
        expiry_date=expiry_date,
    )

    db.session.add(batch)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="DrugBatch",
        entity_id=batch.id,
        details={
            "clinic_id": clinic_id,
            "drug_id": drug_id,
            "batch_number": batch.batch_number,
            "quantity": quantity_on_hand,
        },
    )

    return batch


def get_stock_summary(
    clinic_id: int,
    drug_id: int,
) -> dict:
    drug = _get_drug_or_404(
        drug_id
    )

    _validate_drug_catalog_scope(
        drug,
        clinic_id,
    )

    today = date.today()

    quantity, batch_count = (
        db.session.query(
            func.coalesce(
                func.sum(
                    DrugBatch.quantity_on_hand
                ),
                0,
            ),
            func.count(
                DrugBatch.id
            ),
        )
        .filter(
            DrugBatch.clinic_id == clinic_id,
            DrugBatch.drug_id == drug_id,
            DrugBatch.expiry_date >= today,
        )
        .one()
    )

    return {
        "clinic_id": clinic_id,
        "drug_id": drug_id,
        "drug_name": drug.name,
        "quantity_on_hand": int(
            quantity or 0
        ),
        "batch_count": int(
            batch_count or 0
        ),
    }


def _allocate_fefo(
    clinic_id: int,
    drug_id: int,
    quantity_needed: int,
) -> list[tuple[DrugBatch, int]]:
    """
    Allocate stock using FEFO:

        First Expiry, First Out.

    Eligible batches are row-locked before their quantities
    are modified.
    """

    if quantity_needed <= 0:
        raise ValidationError(
            "Quantity needed must be greater than zero"
        )

    today = date.today()

    batches = (
        db.session.query(DrugBatch)
        .filter(
            DrugBatch.clinic_id == clinic_id,
            DrugBatch.drug_id == drug_id,
            DrugBatch.expiry_date >= today,
            DrugBatch.quantity_on_hand > 0,
        )
        .order_by(
            DrugBatch.expiry_date.asc(),
            DrugBatch.id.asc(),
        )
        .with_for_update()
        .all()
    )

    remaining = quantity_needed
    allocations: list[
        tuple[DrugBatch, int]
    ] = []

    for batch in batches:
        if remaining <= 0:
            break

        allocated = min(
            batch.quantity_on_hand,
            remaining,
        )

        if allocated <= 0:
            continue

        batch.quantity_on_hand -= allocated

        allocations.append(
            (
                batch,
                allocated,
            )
        )

        remaining -= allocated

    if remaining > 0:
        available = (
            quantity_needed - remaining
        )

        raise ConflictError(
            f"Insufficient stock for drug {drug_id} "
            f"in clinic {clinic_id}. "
            f"Requested {quantity_needed}, "
            f"available {available}."
        )

    return allocations


# ============================================================================
# DISPENSING
# ============================================================================

def _validate_dispense_entry(
    clinic_id: int,
    prescription: Prescription,
    prescription_item: PrescriptionItem,
    requested_quantity: int,
) -> None:
    _validate_prescription_item_scope(
        prescription_item,
        prescription,
    )

    if not isinstance(
        requested_quantity,
        int,
    ) or isinstance(
        requested_quantity,
        bool,
    ):
        raise ValidationError(
            "Dispense quantity must be an integer"
        )

    if requested_quantity <= 0:
        raise ValidationError(
            "Dispense quantity must be greater than zero"
        )

    drug = _get_drug_or_404(
        prescription_item.drug_id
    )

    _validate_drug_catalog_scope(
        drug,
        clinic_id,
    )

    _validate_active_drug(
        drug
    )

    remaining = _get_remaining_prescription_quantity(
        prescription_item
    )

    if remaining <= 0:
        raise ConflictError(
            f"Prescription item {prescription_item.id} "
            f"has already been fully dispensed"
        )

    if requested_quantity > remaining:
        raise ValidationError(
            f"Cannot dispense {requested_quantity} units "
            f"for prescription item {prescription_item.id}. "
            f"Only {remaining} remain."
        )


@transactional
def create_dispense_record(
    clinic_id: int,
    prescription_id: int,
    dispensed_by_id: int,
    items: list[dict],
    notes: str | None = None,
) -> DispenseRecord:
    """
    Dispense one or more prescription items.

    Expected item structure:

        {
            "prescription_item_id": 123,
            "quantity": 10,
        }

    Each drug is allocated independently using FEFO.

    The transaction is atomic. If any requested medication cannot
    be fulfilled, the entire transaction rolls back.
    """

    ensure_clinic_active(
        clinic_id
    )

    prescription = (
        db.session.query(Prescription)
        .filter(
            Prescription.id == prescription_id
        )
        .with_for_update()
        .first()
    )

    if prescription is None:
        raise NotFoundError(
            f"Prescription {prescription_id} not found"
        )

    _validate_prescription_scope(
        prescription,
        clinic_id,
    )

    _validate_prescription_for_dispensing(
        prescription
    )

    staff = _validate_staff_for_pharmacy(
        dispensed_by_id,
        clinic_id,
    )

    if not items:
        raise ValidationError(
            "At least one dispensing item is required"
        )

    seen_item_ids: set[int] = set()

    prepared_items: list[
        tuple[PrescriptionItem, int]
    ] = []

    for entry in items:
        if not isinstance(entry, dict):
            raise ValidationError(
                "Each dispensing item must be an object"
            )

        prescription_item_id = entry.get(
            "prescription_item_id"
        )

        quantity = entry.get(
            "quantity"
        )

        if prescription_item_id is None:
            raise ValidationError(
                "Each dispensing item requires "
                "prescription_item_id"
            )

        if prescription_item_id in seen_item_ids:
            raise ValidationError(
                f"Duplicate prescription item "
                f"{prescription_item_id}"
            )

        seen_item_ids.add(
            prescription_item_id
        )

        prescription_item = (
            db.session.query(PrescriptionItem)
            .filter(
                PrescriptionItem.id
                == prescription_item_id,
                PrescriptionItem.prescription_id
                == prescription.id,
            )
            .with_for_update()
            .first()
        )

        if prescription_item is None:
            raise NotFoundError(
                f"Prescription item "
                f"{prescription_item_id} not found "
                f"on prescription {prescription.id}"
            )

        _validate_dispense_entry(
            clinic_id=clinic_id,
            prescription=prescription,
            prescription_item=prescription_item,
            requested_quantity=quantity,
        )

        prepared_items.append(
            (
                prescription_item,
                quantity,
            )
        )

    record = DispenseRecord(
        prescription_id=prescription.id,
        dispensed_by_id=staff.id,
        status=DispenseStatus.PENDING,
        notes=notes,
    )

    db.session.add(record)
    db.session.flush()

    total_dispensed = 0

    for prescription_item, quantity in prepared_items:
        allocations = _allocate_fefo(
            clinic_id=clinic_id,
            drug_id=prescription_item.drug_id,
            quantity_needed=quantity,
        )

        for batch, allocated_quantity in allocations:
            dispense_item = DispenseItem(
                dispense_record_id=record.id,
                batch_id=batch.id,
                prescription_item_id=prescription_item.id,
                quantity_dispensed=allocated_quantity,
            )

            db.session.add(
                dispense_item
            )

            total_dispensed += (
                allocated_quantity
            )

    db.session.flush()

    requested_total = sum(
        quantity
        for _, quantity in prepared_items
    )

    if total_dispensed != requested_total:
        raise ConflictError(
            "Dispensing transaction did not "
            "fulfill the requested quantities"
        )

    all_requested_items_fulfilled = True

    for prescription_item, _ in prepared_items:
        remaining = (
            _get_remaining_prescription_quantity(
                prescription_item
            )
        )

        if remaining > 0:
            all_requested_items_fulfilled = False
            break

    record.status = (
        DispenseStatus.DISPENSED
        if all_requested_items_fulfilled
        else DispenseStatus.PARTIALLY_DISPENSED
    )

    record.dispensed_at = _utcnow()

    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="DispenseRecord",
        entity_id=record.id,
        details={
            "clinic_id": clinic_id,
            "prescription_id": prescription.id,
            "dispensed_by_id": staff.id,
            "status": record.status.value,
            "quantity_dispensed": total_dispensed,
        },
    )

    return record


def get_dispense_record(
    dispense_record_id: int,
) -> DispenseRecord:
    """
    Historical retrieval.

    No clinic-active check is performed.
    """

    return _get_dispense_record_or_404(
        dispense_record_id
    )


def list_dispense_records_for_prescription(
    prescription_id: int,
) -> list[DispenseRecord]:
    """
    Historical retrieval.

    No clinic-active check is performed.
    """

    _get_prescription_or_404(
        prescription_id
    )

    return (
        db.session.query(DispenseRecord)
        .filter(
            DispenseRecord.prescription_id
            == prescription_id
        )
        .order_by(
            DispenseRecord.created_at.desc(),
            DispenseRecord.id.desc(),
        )
        .all()
    )


@transactional
def cancel_dispense_record(
    clinic_id: int,
    dispense_record_id: int,
) -> DispenseRecord:
    """
    Cancel a dispensing transaction and restore every quantity
    deducted by that transaction.

    PENDING:
        Can be cancelled.

    PARTIALLY_DISPENSED:
        Can be cancelled and stock restored.

    DISPENSED:
        Cannot be cancelled.

    CANCELLED:
        Cannot be cancelled again.
    """

    ensure_clinic_active(
        clinic_id
    )

    record = (
        db.session.query(DispenseRecord)
        .filter(
            DispenseRecord.id
            == dispense_record_id
        )
        .with_for_update()
        .first()
    )

    if record is None:
        raise NotFoundError(
            f"Dispense record {dispense_record_id} not found"
        )

    _validate_prescription_scope(
        record.prescription,
        clinic_id,
    )

    if record.status == DispenseStatus.CANCELLED:
        raise ConflictError(
            f"Dispense record {record.id} "
            f"is already cancelled"
        )

    if record.status == DispenseStatus.DISPENSED:
        raise ConflictError(
            f"Dispense record {record.id} "
            f"is fully dispensed and cannot be cancelled"
        )

    if record.status not in {
        DispenseStatus.PENDING,
        DispenseStatus.PARTIALLY_DISPENSED,
    }:
        raise ValidationError(
            f"Dispense record {record.id} "
            f"cannot be cancelled from status "
            f"{record.status.value}"
        )

    items = (
        db.session.query(DispenseItem)
        .filter(
            DispenseItem.dispense_record_id
            == record.id
        )
        .all()
    )

    batch_ids = {
        item.batch_id
        for item in items
    }

    locked_batches: dict[
        int,
        DrugBatch,
    ] = {}

    if batch_ids:
        batches = (
            db.session.query(DrugBatch)
            .filter(
                DrugBatch.id.in_(batch_ids),
                DrugBatch.clinic_id == clinic_id,
            )
            .with_for_update()
            .all()
        )

        locked_batches = {
            batch.id: batch
            for batch in batches
        }

    for item in items:
        batch = locked_batches.get(
            item.batch_id
        )

        if batch is None:
            raise ValidationError(
                f"Dispense item {item.id} references "
                f"a batch outside clinic {clinic_id}"
            )

        batch.quantity_on_hand += (
            item.quantity_dispensed
        )

    record.status = (
        DispenseStatus.CANCELLED
    )

    record.dispensed_at = None

    db.session.flush()

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="DispenseRecord",
        entity_id=record.id,
        details={
            "clinic_id": clinic_id,
            "status": DispenseStatus.CANCELLED.value,
            "restored_items": len(items),
        },
    )

    return record
