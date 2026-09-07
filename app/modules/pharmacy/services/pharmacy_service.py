from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func

from app.extensions import db

from app.core.audit.services.audit_service import create_audit_log
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


# ============================================================================
# TIME HELPERS
# ============================================================================


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utc_today() -> date:
    return _utcnow().date()


# ============================================================================
# TENANT-SCOPED GETTERS
# ============================================================================


def _get_drug_or_404(
    drug_id: int,
    clinic_id: int | None = None,
) -> Drug:
    query = db.session.query(Drug).filter(
        Drug.id == drug_id,
    )

    if clinic_id is not None:
        query = query.filter(
            db.or_(
                Drug.clinic_id.is_(None),
                Drug.clinic_id == clinic_id,
            )
        )
    else:
        query = query.filter(
            Drug.clinic_id.is_(None)
        )

    drug = query.first()

    if drug is None:
        raise NotFoundError(
            f"Drug {drug_id} not found"
        )

    return drug


def _get_batch_or_404(
    batch_id: int,
    clinic_id: int,
) -> DrugBatch:
    batch = (
        db.session.query(DrugBatch)
        .filter(
            DrugBatch.id == batch_id,
            DrugBatch.clinic_id == clinic_id,
        )
        .first()
    )

    if batch is None:
        raise NotFoundError(
            f"Drug batch {batch_id} not found"
        )

    return batch


def _get_prescription_or_404(
    prescription_id: int,
    clinic_id: int,
) -> Prescription:
    prescription = (
        db.session.query(Prescription)
        .filter(
            Prescription.id == prescription_id,
            Prescription.clinic_id == clinic_id,
        )
        .first()
    )

    if prescription is None:
        raise NotFoundError(
            f"Prescription {prescription_id} not found"
        )

    return prescription


def _get_prescription_item_or_404(
    prescription_item_id: int,
    prescription: Prescription,
) -> PrescriptionItem:
    item = (
        db.session.query(PrescriptionItem)
        .filter(
            PrescriptionItem.id == prescription_item_id,
            PrescriptionItem.prescription_id == prescription.id,
        )
        .first()
    )

    if item is None:
        raise NotFoundError(
            f"Prescription item {prescription_item_id} "
            f"not found on prescription {prescription.id}"
        )

    return item


def _get_dispense_record_or_404(
    dispense_record_id: int,
    clinic_id: int,
) -> DispenseRecord:
    record = (
        db.session.query(DispenseRecord)
        .join(
            Prescription,
            DispenseRecord.prescription_id
            == Prescription.id,
        )
        .filter(
            DispenseRecord.id == dispense_record_id,
            Prescription.clinic_id == clinic_id,
        )
        .first()
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
    clinic_id: int,
) -> None:
    """
    Global drugs are readable/usable by every clinic.

    Clinic-specific drugs may only be used by their owning clinic.
    """

    if drug.clinic_id is None:
        return

    if drug.clinic_id != clinic_id:
        raise ValidationError(
            f"Drug {drug.id} does not belong to clinic {clinic_id}"
        )


def _validate_clinic_specific_drug_for_management(
    drug: Drug,
    clinic_id: int,
) -> None:
    """
    Clinic users may manage only clinic-specific drugs belonging
    to their own clinic.

    Global catalog drugs may be read and used, but cannot be
    modified by ordinary clinic-scoped pharmacy operations.
    """

    if drug.clinic_id is None:
        raise ValidationError(
            "Global catalog drugs cannot be modified "
            "through clinic-scoped pharmacy operations"
        )

    if drug.clinic_id != clinic_id:
        raise ValidationError(
            f"Drug {drug.id} does not belong to clinic {clinic_id}"
        )


def _validate_active_drug(
    drug: Drug,
) -> None:
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
    clinic_id: int,
) -> InventorySupplier | None:
    """
    Suppliers may be:

    - global/shared: clinic_id IS NULL
    - clinic-specific: clinic_id == authenticated clinic

    Suppliers belonging to another clinic are rejected.
    """

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

    if not supplier.is_active:
        raise ValidationError(
            f"Inventory supplier {supplier_id} is inactive"
        )

    if (
        supplier.clinic_id is not None
        and supplier.clinic_id != clinic_id
    ):
        raise ValidationError(
            f"Inventory supplier {supplier_id} does not belong "
            f"to clinic {clinic_id}"
        )

    return supplier


def _validate_batch_scope(
    batch: DrugBatch,
    clinic_id: int,
) -> None:
    if batch.clinic_id != clinic_id:
        raise ValidationError(
            f"Drug batch {batch.id} does not belong "
            f"to clinic {clinic_id}"
        )


def _validate_batch_for_dispensing(
    *,
    batch: DrugBatch,
    clinic_id: int,
    drug_id: int,
) -> None:
    _validate_batch_scope(
        batch,
        clinic_id,
    )

    if batch.drug_id != drug_id:
        raise ValidationError(
            f"Drug batch {batch.id} does not belong "
            f"to drug {drug_id}"
        )

    if batch.expiry_date <= _utc_today():
        raise ValidationError(
            f"Drug batch {batch.id} has expired "
            f"or expires today"
        )

    if batch.quantity_on_hand < 0:
        raise ValidationError(
            f"Drug batch {batch.id} has invalid stock"
        )


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

    dispensed_quantity = (
        _get_dispensed_quantity_for_prescription_item(
            prescription_item.id
        )
    )

    remaining_quantity = (
        prescription_item.quantity
        - dispensed_quantity
    )

    if remaining_quantity < 0:
        raise ConflictError(
            f"Prescription item {prescription_item.id} "
            f"has already been dispensed beyond its prescribed quantity"
        )

    return remaining_quantity


def _validate_expiry_date(
    expiry_date: date,
) -> None:
    if expiry_date <= _utc_today():
        raise ValidationError(
            "Drug batch expiry date must be in the future"
        )


# ============================================================================
# DRUG CATALOG
# ============================================================================


def get_drug(
    drug_id: int,
    clinic_id: int,
) -> Drug:
    """
    Clinic-scoped drug retrieval.

    Global drugs are visible to the clinic.
    Other clinics' private drugs are invisible.
    """

    return _get_drug_or_404(
        drug_id,
        clinic_id,
    )


def list_drugs(
    clinic_id: int,
    include_inactive: bool = False,
) -> list[Drug]:
    query = (
        db.session.query(Drug)
        .filter(
            db.or_(
                Drug.clinic_id.is_(None),
                Drug.clinic_id == clinic_id,
            )
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
    Create a clinic-specific drug.

    The route must provide the authenticated clinic_id.

    clinic_id=None is retained only for compatibility with the
    underlying service/API design and should not be supplied by
    ordinary clinic-scoped routes.
    """

    if clinic_id is None:
        raise ValidationError(
            "Clinic context is required to create a drug"
        )

    ensure_clinic_active(
        clinic_id
    )

    if not isinstance(name, str) or not name.strip():
        raise ValidationError(
            "Drug name is required"
        )

    name = name.strip()

    if unit_price is not None and unit_price < 0:
        raise ValidationError(
            "Unit price cannot be negative"
        )

    if barcode:
        barcode = barcode.strip()

        existing = (
            db.session.query(Drug)
            .filter(
                Drug.barcode == barcode,
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

    db.session.add(
        drug
    )

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
    clinic_id: int,
    **updates,
) -> Drug:
    ensure_clinic_active(
        clinic_id
    )

    drug = _get_drug_or_404(
        drug_id,
        clinic_id,
    )

    _validate_clinic_specific_drug_for_management(
        drug,
        clinic_id,
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
        set(updates)
        - allowed_fields
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

        if not isinstance(name, str) or not name.strip():
            raise ValidationError(
                "Drug name cannot be empty"
            )

        updates["name"] = name.strip()

    if "unit_price" in updates:
        unit_price = updates["unit_price"]

        if (
            unit_price is not None
            and unit_price < 0
        ):
            raise ValidationError(
                "Unit price cannot be negative"
            )

    if "barcode" in updates:
        barcode = updates["barcode"]

        if isinstance(barcode, str):
            barcode = barcode.strip()

        updates["barcode"] = barcode

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
            "clinic_id": clinic_id,
            "updated_fields": list(
                updates.keys()
            ),
        },
    )

    return drug


@transactional
def set_drug_active_status(
    drug_id: int,
    clinic_id: int,
    is_active: bool,
) -> Drug:
    ensure_clinic_active(
        clinic_id
    )

    drug = _get_drug_or_404(
        drug_id,
        clinic_id,
    )

    _validate_clinic_specific_drug_for_management(
        drug,
        clinic_id,
    )

    if not isinstance(is_active, bool):
        raise ValidationError(
            "is_active must be a boolean"
        )

    previous_status = drug.is_active

    drug.is_active = is_active

    db.session.flush()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Drug",
        entity_id=drug.id,
        details={
            "clinic_id": clinic_id,
            "previous_status": previous_status,
            "new_status": is_active,
        },
    )

    return drug


# ============================================================================
# BATCHES / STOCK
# ============================================================================


def get_batch(
    batch_id: int,
    clinic_id: int,
) -> DrugBatch:
    return _get_batch_or_404(
        batch_id,
        clinic_id,
    )


def list_batches(
    drug_id: int,
    clinic_id: int,
    include_expired: bool = True,
) -> list[DrugBatch]:
    drug = _get_drug_or_404(
        drug_id,
        clinic_id,
    )

    _validate_drug_catalog_scope(
        drug,
        clinic_id,
    )

    query = (
        db.session.query(DrugBatch)
        .filter(
            DrugBatch.drug_id == drug_id,
            DrugBatch.clinic_id == clinic_id,
        )
    )

    if not include_expired:
        query = query.filter(
            DrugBatch.expiry_date > _utc_today()
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

    today = _utc_today()

    expiry_limit = (
        today
        + timedelta(days=days)
    )

    return (
        db.session.query(DrugBatch)
        .filter(
            DrugBatch.clinic_id == clinic_id,
            DrugBatch.expiry_date > today,
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
        drug_id,
        clinic_id,
    )

    _validate_drug_catalog_scope(
        drug,
        clinic_id,
    )

    _validate_active_drug(
        drug
    )

    if (
        not isinstance(batch_number, str)
        or not batch_number.strip()
    ):
        raise ValidationError(
            "Batch number is required"
        )

    batch_number = batch_number.strip()

    if (
        not isinstance(quantity_on_hand, int)
        or isinstance(quantity_on_hand, bool)
    ):
        raise ValidationError(
            "Quantity on hand must be an integer"
        )

    if quantity_on_hand < 0:
        raise ValidationError(
            "Quantity on hand cannot be negative"
        )

    if (
        not isinstance(reorder_level, int)
        or isinstance(reorder_level, bool)
    ):
        raise ValidationError(
            "Reorder level must be an integer"
        )

    if reorder_level < 0:
        raise ValidationError(
            "Reorder level cannot be negative"
        )

    if not isinstance(expiry_date, date):
        raise ValidationError(
            "Expiry date must be a valid date"
        )

    _validate_expiry_date(
        expiry_date
    )

    supplier = _validate_supplier(
        supplier_id,
        clinic_id,
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

    db.session.add(
        batch
    )

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
            "expiry_date": batch.expiry_date.isoformat(),
            "supplier_id": batch.supplier_id,
        },
    )

    return batch


def get_stock_summary(
    clinic_id: int,
    drug_id: int,
) -> dict:
    drug = _get_drug_or_404(
        drug_id,
        clinic_id,
    )

    _validate_drug_catalog_scope(
        drug,
        clinic_id,
    )

    today = _utc_today()

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
            DrugBatch.expiry_date > today,
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


# ============================================================================
# DISPENSING VALIDATION
# ============================================================================


def _validate_dispense_entry(
    *,
    clinic_id: int,
    prescription: Prescription,
    prescription_item: PrescriptionItem,
    requested_quantity: int,
) -> None:
    _validate_prescription_item_scope(
        prescription_item,
        prescription,
    )

    if (
        not isinstance(requested_quantity, int)
        or isinstance(requested_quantity, bool)
    ):
        raise ValidationError(
            "Dispense quantity must be an integer"
        )

    if requested_quantity <= 0:
        raise ValidationError(
            "Dispense quantity must be greater than zero"
        )

    remaining_quantity = (
        _get_remaining_prescription_quantity(
            prescription_item
        )
    )

    if requested_quantity > remaining_quantity:
        raise ConflictError(
            f"Requested quantity {requested_quantity} for "
            f"prescription item {prescription_item.id} exceeds "
            f"the remaining quantity of {remaining_quantity}"
        )

    drug = _get_drug_or_404(
        prescription_item.drug_id,
        clinic_id,
    )

    _validate_drug_catalog_scope(
        drug,
        clinic_id,
    )

    _validate_active_drug(
        drug
    )


# ============================================================================
# PRESCRIPTION ACCESS FOR PHARMACY
# ============================================================================


def get_prescription_for_pharmacy(
    prescription_id: int,
    clinic_id: int,
) -> Prescription:
    """
    Public pharmacy-facing prescription getter.

    This prevents routes from importing private prescription
    service helpers merely to perform tenant validation.
    """

    prescription = _get_prescription_or_404(
        prescription_id,
        clinic_id,
    )

    _validate_prescription_scope(
        prescription,
        clinic_id,
    )

    return prescription


# ============================================================================
# DISPENSING
# ============================================================================


@transactional
def create_dispense_record(
    clinic_id: int,
    prescription_id: int,
    dispensed_by_id: int,
    items: list[dict],
    notes: str | None = None,
) -> DispenseRecord:
    ensure_clinic_active(
        clinic_id
    )

    if not items:
        raise ValidationError(
            "At least one dispensing item is required"
        )

    # ------------------------------------------------------------------------
    # Lock prescription first.
    # ------------------------------------------------------------------------

    prescription = (
        db.session.query(Prescription)
        .filter(
            Prescription.id == prescription_id,
            Prescription.clinic_id == clinic_id,
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

    # ------------------------------------------------------------------------
    # Validate dispensing pharmacist.
    # ------------------------------------------------------------------------

    staff = _validate_staff_for_pharmacy(
        dispensed_by_id,
        clinic_id,
    )

    # ------------------------------------------------------------------------
    # Normalize request entries.
    # ------------------------------------------------------------------------

    normalized_entries: list[dict] = []

    seen_pairs: set[tuple[int, int]] = set()

    prescription_item_ids: set[int] = set()

    for entry in items:
        if not isinstance(entry, dict):
            raise ValidationError(
                "Each dispensing item must be an object"
            )

        prescription_item_id = entry.get(
            "prescription_item_id"
        )

        batch_id = entry.get(
            "batch_id"
        )

        quantity = entry.get(
            "quantity"
        )

        if prescription_item_id is None:
            raise ValidationError(
                "Each dispensing item requires "
                "prescription_item_id"
            )

        if batch_id is None:
            raise ValidationError(
                "Each dispensing item requires "
                "batch_id"
            )

        if (
            not isinstance(prescription_item_id, int)
            or isinstance(prescription_item_id, bool)
            or prescription_item_id <= 0
        ):
            raise ValidationError(
                "Prescription item ID must be a positive integer"
            )

        if (
            not isinstance(batch_id, int)
            or isinstance(batch_id, bool)
            or batch_id <= 0
        ):
            raise ValidationError(
                "Batch ID must be a positive integer"
            )

        if (
            not isinstance(quantity, int)
            or isinstance(quantity, bool)
            or quantity <= 0
        ):
            raise ValidationError(
                "Dispense quantity must be a positive integer"
            )

        pair = (
            prescription_item_id,
            batch_id,
        )

        if pair in seen_pairs:
            raise ValidationError(
                f"Duplicate batch {batch_id} for "
                f"prescription item {prescription_item_id}"
            )

        seen_pairs.add(pair)

        prescription_item_ids.add(
            prescription_item_id
        )

        normalized_entries.append(
            {
                "prescription_item_id": prescription_item_id,
                "batch_id": batch_id,
                "quantity": quantity,
            }
        )

    # ------------------------------------------------------------------------
    # Lock prescription items in deterministic order.
    # ------------------------------------------------------------------------

    locked_items = (
        db.session.query(PrescriptionItem)
        .filter(
            PrescriptionItem.prescription_id
            == prescription.id,
            PrescriptionItem.id.in_(
                prescription_item_ids
            ),
        )
        .order_by(
            PrescriptionItem.id.asc()
        )
        .with_for_update()
        .all()
    )

    items_by_id = {
        item.id: item
        for item in locked_items
    }

    if len(items_by_id) != len(
        prescription_item_ids
    ):
        missing_ids = (
            prescription_item_ids
            - set(items_by_id)
        )

        missing_text = ", ".join(
            str(item_id)
            for item_id in sorted(
                missing_ids
            )
        )

        raise NotFoundError(
            f"Prescription item(s) {missing_text} "
            f"not found on prescription {prescription.id}"
        )

    # ------------------------------------------------------------------------
    # Aggregate request by prescription item.
    # ------------------------------------------------------------------------

    requested_by_item: dict[int, int] = {}

    for entry in normalized_entries:
        prescription_item_id = entry[
            "prescription_item_id"
        ]

        quantity = entry[
            "quantity"
        ]

        requested_by_item[
            prescription_item_id
        ] = (
            requested_by_item.get(
                prescription_item_id,
                0,
            )
            + quantity
        )

    # ------------------------------------------------------------------------
    # Validate prescribed quantities.
    # ------------------------------------------------------------------------

    for (
        prescription_item_id,
        requested_quantity,
    ) in requested_by_item.items():

        prescription_item = items_by_id[
            prescription_item_id
        ]

        _validate_dispense_entry(
            clinic_id=clinic_id,
            prescription=prescription,
            prescription_item=prescription_item,
            requested_quantity=requested_quantity,
        )

    # ------------------------------------------------------------------------
    # Lock selected batches in deterministic order.
    # ------------------------------------------------------------------------

    batch_ids = {
        entry["batch_id"]
        for entry in normalized_entries
    }

    locked_batches = (
        db.session.query(DrugBatch)
        .filter(
            DrugBatch.id.in_(
                batch_ids
            ),
            DrugBatch.clinic_id == clinic_id,
        )
        .order_by(
            DrugBatch.id.asc()
        )
        .with_for_update()
        .all()
    )

    batches_by_id = {
        batch.id: batch
        for batch in locked_batches
    }

    if len(batches_by_id) != len(
        batch_ids
    ):
        missing_batch_ids = (
            batch_ids
            - set(batches_by_id)
        )

        missing_text = ", ".join(
            str(batch_id)
            for batch_id in sorted(
                missing_batch_ids
            )
        )

        raise NotFoundError(
            f"Drug batch(es) {missing_text} "
            f"not found in clinic {clinic_id}"
        )

    # ------------------------------------------------------------------------
    # Validate selected batches.
    # ------------------------------------------------------------------------

    requested_by_batch: dict[int, int] = {}

    for entry in normalized_entries:
        prescription_item = items_by_id[
            entry["prescription_item_id"]
        ]

        batch = batches_by_id[
            entry["batch_id"]
        ]

        _validate_batch_for_dispensing(
            batch=batch,
            clinic_id=clinic_id,
            drug_id=prescription_item.drug_id,
        )

        batch_id = batch.id
        quantity = entry["quantity"]

        requested_by_batch[
            batch_id
        ] = (
            requested_by_batch.get(
                batch_id,
                0,
            )
            + quantity
        )

    # ------------------------------------------------------------------------
    # Verify stock after locks.
    # ------------------------------------------------------------------------

    for (
        batch_id,
        requested_quantity,
    ) in requested_by_batch.items():

        batch = batches_by_id[
            batch_id
        ]

        if requested_quantity > batch.quantity_on_hand:
            raise ConflictError(
                f"Insufficient stock in drug batch {batch.id}. "
                f"Requested {requested_quantity}, "
                f"available {batch.quantity_on_hand}"
            )

    # ------------------------------------------------------------------------
    # Create dispense record.
    # ------------------------------------------------------------------------

    dispense_record = DispenseRecord(
        prescription_id=prescription.id,
        dispensed_by_id=staff.id,
        status=DispenseStatus.PENDING,
        notes=notes,
    )

    db.session.add(
        dispense_record
    )

    db.session.flush()

    # ------------------------------------------------------------------------
    # Deduct selected stock.
    # ------------------------------------------------------------------------

    for entry in normalized_entries:
        prescription_item = items_by_id[
            entry["prescription_item_id"]
        ]

        batch = batches_by_id[
            entry["batch_id"]
        ]

        quantity = entry["quantity"]

        batch.quantity_on_hand -= quantity

        dispense_item = DispenseItem(
            dispense_record_id=dispense_record.id,
            batch_id=batch.id,
            prescription_item_id=prescription_item.id,
            quantity_dispensed=quantity,
        )

        db.session.add(
            dispense_item
        )

    db.session.flush()

    # ------------------------------------------------------------------------
    # Determine fulfillment status.
    # ------------------------------------------------------------------------

    all_fulfilled = True

    for prescription_item in prescription.items:
        if prescription_item.quantity is None:
            all_fulfilled = False
            break

        dispensed_quantity = (
            _get_dispensed_quantity_for_prescription_item(
                prescription_item.id
            )
        )

        if (
            dispensed_quantity
            < prescription_item.quantity
        ):
            all_fulfilled = False
            break

    if all_fulfilled:
        dispense_record.status = (
            DispenseStatus.DISPENSED
        )
    else:
        dispense_record.status = (
            DispenseStatus.PARTIALLY_DISPENSED
        )

    dispense_record.dispensed_at = _utcnow()

    db.session.flush()

    # ------------------------------------------------------------------------
    # Audit.
    # ------------------------------------------------------------------------

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="DispenseRecord",
        entity_id=dispense_record.id,
        user_id=(
            staff.user.id
            if staff.user is not None
            else None
        ),
        details={
            "clinic_id": clinic_id,
            "prescription_id": prescription.id,
            "dispensed_by_id": staff.id,
            "status": dispense_record.status.value,
            "items": [
                {
                    "prescription_item_id": entry[
                        "prescription_item_id"
                    ],
                    "batch_id": entry[
                        "batch_id"
                    ],
                    "quantity": entry[
                        "quantity"
                    ],
                }
                for entry in normalized_entries
            ],
        },
    )

    return dispense_record


# ============================================================================
# DISPENSE RECORD RETRIEVAL
# ============================================================================


def get_dispense_record(
    dispense_record_id: int,
    clinic_id: int,
) -> DispenseRecord:
    return _get_dispense_record_or_404(
        dispense_record_id,
        clinic_id,
    )


def list_dispense_records_for_prescription(
    prescription_id: int,
    clinic_id: int,
) -> list[DispenseRecord]:
    prescription = _get_prescription_or_404(
        prescription_id,
        clinic_id,
    )

    _validate_prescription_scope(
        prescription,
        clinic_id,
    )

    return (
        db.session.query(DispenseRecord)
        .filter(
            DispenseRecord.prescription_id
            == prescription.id
        )
        .order_by(
            DispenseRecord.created_at.asc(),
            DispenseRecord.id.asc(),
        )
        .all()
    )


# ============================================================================
# DISPENSE CANCELLATION
# ============================================================================


@transactional
def cancel_dispense_record(
    dispense_record_id: int,
    clinic_id: int,
) -> DispenseRecord:
    """
    Cancel a pharmacy dispensing transaction.

    The operation is clinic-scoped and transactional.

    Every DispenseItem stores the exact DrugBatch and quantity
    deducted during dispensing. Cancellation restores those
    exact quantities.

    A fully DISPENSED transaction cannot be cancelled.
    """

    ensure_clinic_active(
        clinic_id
    )

    record = (
        db.session.query(DispenseRecord)
        .join(
            Prescription,
            DispenseRecord.prescription_id
            == Prescription.id,
        )
        .filter(
            DispenseRecord.id == dispense_record_id,
            Prescription.clinic_id == clinic_id,
        )
        .with_for_update()
        .first()
    )

    if record is None:
        raise NotFoundError(
            f"Dispense record {dispense_record_id} not found"
        )

    prescription = (
        db.session.query(Prescription)
        .filter(
            Prescription.id == record.prescription_id,
            Prescription.clinic_id == clinic_id,
        )
        .first()
    )

    if prescription is None:
        raise NotFoundError(
            f"Prescription {record.prescription_id} not found"
        )

    _validate_prescription_scope(
        prescription,
        clinic_id,
    )

    if record.status == DispenseStatus.CANCELLED:
        raise ConflictError(
            f"Dispense record {record.id} is already cancelled"
        )

    if record.status == DispenseStatus.DISPENSED:
        raise ConflictError(
            f"Dispense record {record.id} has already been fully "
            f"dispensed and cannot be cancelled"
        )

    if record.status not in {
        DispenseStatus.PENDING,
        DispenseStatus.PARTIALLY_DISPENSED,
    }:
        raise ConflictError(
            f"Dispense record {record.id} cannot be cancelled "
            f"from status {record.status.value}"
        )

    previous_status = record.status.value

    dispense_items = (
        db.session.query(DispenseItem)
        .filter(
            DispenseItem.dispense_record_id
            == record.id
        )
        .order_by(
            DispenseItem.id.asc()
        )
        .all()
    )

    if not dispense_items:
        raise ConflictError(
            f"Dispense record {record.id} has no dispensing items"
        )

    # ------------------------------------------------------------------------
    # Lock affected batches in deterministic order.
    # ------------------------------------------------------------------------

    batch_ids = {
        item.batch_id
        for item in dispense_items
    }

    locked_batches = (
        db.session.query(DrugBatch)
        .filter(
            DrugBatch.id.in_(
                batch_ids
            ),
            DrugBatch.clinic_id == clinic_id,
        )
        .order_by(
            DrugBatch.id.asc()
        )
        .with_for_update()
        .all()
    )

    batches_by_id = {
        batch.id: batch
        for batch in locked_batches
    }

    if len(batches_by_id) != len(
        batch_ids
    ):
        missing_batch_ids = (
            batch_ids
            - set(batches_by_id)
        )

        missing_text = ", ".join(
            str(batch_id)
            for batch_id in sorted(
                missing_batch_ids
            )
        )

        raise NotFoundError(
            f"Drug batch(es) {missing_text} "
            f"not found in clinic {clinic_id}"
        )

    # ------------------------------------------------------------------------
    # Restore exact quantities.
    # ------------------------------------------------------------------------

    restored_quantity = 0

    for dispense_item in dispense_items:
        batch = batches_by_id[
            dispense_item.batch_id
        ]

        batch.quantity_on_hand += (
            dispense_item.quantity_dispensed
        )

        restored_quantity += (
            dispense_item.quantity_dispensed
        )

    record.status = (
        DispenseStatus.CANCELLED
    )

    record.dispensed_at = None

    db.session.flush()

    # ------------------------------------------------------------------------
    # Audit cancellation.
    # ------------------------------------------------------------------------

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="DispenseRecord",
        entity_id=record.id,
        details={
            "clinic_id": clinic_id,
            "prescription_id": prescription.id,
            "previous_status": previous_status,
            "new_status": DispenseStatus.CANCELLED.value,
            "restored_quantity": restored_quantity,
            "restored_batches": [
                {
                    "batch_id": item.batch_id,
                    "quantity": item.quantity_dispensed,
                }
                for item in dispense_items
            ],
        },
    )

    return record