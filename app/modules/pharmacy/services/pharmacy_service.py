from datetime import date
from app.extensions import db
from app.core.utils.decorators import transactional
from app.core.exceptions import NotFoundError, ValidationError, ConflictError
from app.core.audit.services.audit_services import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.pharmacy_enums import DispenseStatus
from app.modules.pharmacy.models.pharmacy_model import Drug, DrugBatch, DispenseRecord, DispenseItem


# ---------------------------------------------------------------------
# Drug catalog
# ---------------------------------------------------------------------

def get_drug(drug_id: int) -> Drug:
    drug = Drug.query.get(drug_id)
    if drug is None:
        raise NotFoundError(f"Drug {drug_id} not found")
    return drug


def list_drugs(clinic_id: int | None = None, active_only: bool = True, search: str | None = None) -> list[Drug]:
    query = Drug.query
    if clinic_id is not None:
        query = query.filter(db.or_(Drug.clinic_id == clinic_id, Drug.clinic_id.is_(None)))
    if active_only:
        query = query.filter_by(is_active=True)
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(db.or_(Drug.name.ilike(like), Drug.generic_name.ilike(like)))
    return query.order_by(Drug.name).all()


@transactional
def create_drug(name: str, **fields) -> Drug:
    if not name or not name.strip():
        raise ValidationError("Drug name is required")

    barcode = fields.get("barcode")
    if barcode and Drug.query.filter_by(barcode=barcode).first():
        raise ConflictError(f"Drug barcode '{barcode}' already exists")

    drug = Drug(name=name.strip(), **fields)
    db.session.add(drug)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Drug",
        entity_id=drug.id,
        description=f"Drug '{drug.name}' added to catalog",
        new_value={"name": drug.name, "category": drug.category.value, "is_controlled": drug.is_controlled},
    )
    return drug


@transactional
def update_drug(drug_id: int, **fields) -> Drug:
    drug = get_drug(drug_id)

    old_value, new_value = {}, {}
    for key, new_val in fields.items():
        current_val = getattr(drug, key)
        if current_val != new_val:
            old_value[key] = current_val.value if hasattr(current_val, "value") else current_val
            new_value[key] = new_val.value if hasattr(new_val, "value") else new_val
            setattr(drug, key, new_val)

    if new_value:
        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="Drug",
            entity_id=drug.id,
            description=f"Drug '{drug.name}' updated",
            old_value=old_value,
            new_value=new_value,
        )
    return drug


# ---------------------------------------------------------------------
# Batch / stock management
# ---------------------------------------------------------------------

def get_batch(batch_id: int) -> DrugBatch:
    batch = DrugBatch.query.get(batch_id)
    if batch is None:
        raise NotFoundError(f"Drug batch {batch_id} not found")
    return batch


def list_batches(drug_id: int, include_expired: bool = True) -> list[DrugBatch]:
    get_drug(drug_id)
    query = DrugBatch.query.filter_by(drug_id=drug_id)
    if not include_expired:
        query = query.filter(DrugBatch.expiry_date >= date.today())
    return query.order_by(DrugBatch.expiry_date).all()


def list_expiring_batches(clinic_id: int | None, within_days: int = 30) -> list[DrugBatch]:
    """For expiry-alert reporting — batches expiring soon but not yet expired."""
    from datetime import timedelta
    cutoff = date.today() + timedelta(days=within_days)
    query = DrugBatch.query.join(Drug).filter(
        DrugBatch.expiry_date >= date.today(),
        DrugBatch.expiry_date <= cutoff,
        DrugBatch.quantity_on_hand > 0,
    )
    if clinic_id is not None:
        query = query.filter(db.or_(Drug.clinic_id == clinic_id, Drug.clinic_id.is_(None)))
    return query.order_by(DrugBatch.expiry_date).all()


@transactional
def add_batch(drug_id: int, batch_number: str, quantity_on_hand: int, expiry_date: date, **fields) -> DrugBatch:
    get_drug(drug_id)

    if not batch_number or not batch_number.strip():
        raise ValidationError("Batch number is required")
    if quantity_on_hand < 0:
        raise ValidationError("Quantity on hand cannot be negative")
    if expiry_date < date.today():
        raise ValidationError("Cannot receive a batch that is already expired")

    # Python-side check for a clean error message — the DB-level
    # UniqueConstraint on (drug_id, batch_number) is the real backstop
    # against races or direct writes bypassing this.
    duplicate = DrugBatch.query.filter_by(drug_id=drug_id, batch_number=batch_number.strip()).first()
    if duplicate:
        raise ConflictError(f"Batch '{batch_number}' already exists for this drug")

    batch = DrugBatch(
        drug_id=drug_id,
        batch_number=batch_number.strip(),
        quantity_on_hand=quantity_on_hand,
        expiry_date=expiry_date,
        **fields,
    )
    db.session.add(batch)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="DrugBatch",
        entity_id=batch.id,
        description=f"Batch '{batch.batch_number}' received for drug {drug_id} (qty {quantity_on_hand})",
        new_value={"quantity_on_hand": quantity_on_hand, "expiry_date": expiry_date.isoformat()},
    )
    return batch


def get_stock_summary(drug_id: int) -> dict:
    """Total on-hand across non-expired batches — what's actually dispensable right now."""
    get_drug(drug_id)
    today = date.today()
    batches = DrugBatch.query.filter_by(drug_id=drug_id).all()
    usable = [b for b in batches if b.expiry_date >= today]
    expired = [b for b in batches if b.expiry_date < today]
    return {
        "drug_id": drug_id,
        "total_usable_quantity": sum(b.quantity_on_hand for b in usable),
        "total_expired_quantity": sum(b.quantity_on_hand for b in expired),
        "batch_count": len(batches),
    }


# ---------------------------------------------------------------------
# Dispensing — FEFO (First-Expiry-First-Out) allocation
# ---------------------------------------------------------------------

def _allocate_fefo(drug_id: int, quantity_needed: int) -> tuple[list[tuple[DrugBatch, int]], int]:
    """
    Locks and allocates stock across non-expired batches, earliest
    expiry first. Returns (allocations, quantity_short) where
    allocations is [(batch, qty_taken), ...] and quantity_short is
    how much could NOT be covered (0 if fully allocated).
    Expired batches are never allocated from, even as a last resort.
    """
    today = date.today()
    batches = (
        DrugBatch.query.filter(
            DrugBatch.drug_id == drug_id,
            DrugBatch.expiry_date >= today,
            DrugBatch.quantity_on_hand > 0,
        )
        .order_by(DrugBatch.expiry_date)
        .with_for_update()  # prevents two concurrent dispenses over-allocating the same batch
        .all()
    )

    allocations = []
    remaining = quantity_needed
    for batch in batches:
        if remaining <= 0:
            break
        take = min(batch.quantity_on_hand, remaining)
        allocations.append((batch, take))
        remaining -= take

    return allocations, remaining


@transactional
def create_dispense_record(prescription_id: int, dispensed_by_id: int,
                            items: list[dict], notes: str | None = None) -> DispenseRecord:
    """
    items = [{'drug_id': int, 'quantity': int, 'prescription_item_id': int | None}, ...]

    Dispensing happens immediately on creation (matches the
    record_payment pattern in billing_service — no separate confirm
    step). Allocates FEFO per drug; if stock across all non-expired
    batches can't cover a line, dispenses what's available and the
    record status reflects the shortfall rather than silently under-
    or over-delivering.

    prescription_item_id is optional and currently unused for
    validation — prescription_service doesn't exist as usable code
    yet. It's threaded through so records created today are already
    linkable once that module lands, instead of needing a backfill.
    Once prescription_service exists, this should validate the
    dispensed quantity against what was actually prescribed instead
    of trusting the caller's 'quantity' outright.
    """
    if not items:
        raise ValidationError("A dispense record must include at least one item")

    record = DispenseRecord(
        prescription_id=prescription_id,
        dispensed_by_id=dispensed_by_id,
        status=DispenseStatus.PENDING,
        notes=notes,
    )
    db.session.add(record)
    db.session.flush()

    any_shortfall = False
    dispensed_summary = []

    for entry in items:
        drug_id = entry["drug_id"]
        quantity = entry["quantity"]
        prescription_item_id = entry.get("prescription_item_id")

        if quantity <= 0:
            raise ValidationError(f"Quantity for drug {drug_id} must be positive")

        get_drug(drug_id)  # 404s if drug doesn't exist
        allocations, short = _allocate_fefo(drug_id, quantity)

        if short > 0:
            any_shortfall = True

        for batch, taken in allocations:
            batch.quantity_on_hand -= taken
            db.session.add(DispenseItem(
                dispense_record_id=record.id,
                batch_id=batch.id,
                prescription_item_id=prescription_item_id,
                quantity_dispensed=taken,
            ))

        dispensed_summary.append({
            "drug_id": drug_id,
            "prescription_item_id": prescription_item_id,
            "requested": quantity,
            "dispensed": quantity - short,
            "short": short,
        })

    record.status = DispenseStatus.PARTIALLY_DISPENSED if any_shortfall else DispenseStatus.DISPENSED

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="DispenseRecord",
        entity_id=record.id,
        description=f"Dispense record created for prescription {prescription_id}"
        + (" [SHORTFALL — insufficient stock]" if any_shortfall else ""),
        new_value={"status": record.status.value, "items": dispensed_summary},
    )
    return record


def get_dispense_record(record_id: int) -> DispenseRecord:
    record = DispenseRecord.query.get(record_id)
    if record is None:
        raise NotFoundError(f"Dispense record {record_id} not found")
    return record


def list_dispense_records_for_prescription(prescription_id: int) -> list[DispenseRecord]:
    return (
        DispenseRecord.query.filter_by(prescription_id=prescription_id)
        .order_by(DispenseRecord.dispensed_at.desc())
        .all()
    )


@transactional
def cancel_dispense_record(record_id: int, reason: str | None = None) -> DispenseRecord:
    """
    Reverses stock deductions and returns quantity to the originating
    batches. Only allowed while PENDING or PARTIALLY_DISPENSED — a
    fully DISPENSED record represents drugs that have physically left
    the pharmacy, which this service has no way to verify were
    actually returned, so that reversal has to be a deliberate
    separate "returns" workflow, not a same-function cancel.
    """
    record = get_dispense_record(record_id)
    if record.status in (DispenseStatus.DISPENSED, DispenseStatus.CANCELLED):
        raise ConflictError(f"Cannot cancel a dispense record that is already {record.status.value}")

    for item in record.items:
        item.batch.quantity_on_hand += item.quantity_dispensed

    old_status = record.status.value
    record.status = DispenseStatus.CANCELLED
    if reason:
        record.notes = f"{record.notes or ''}\nCancelled: {reason}".strip()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="DispenseRecord",
        entity_id=record.id,
        description="Dispense record cancelled, stock reversed to originating batches"
        + (f": {reason}" if reason else ""),
        old_value={"status": old_status},
        new_value={"status": record.status.value},
    )
    return record