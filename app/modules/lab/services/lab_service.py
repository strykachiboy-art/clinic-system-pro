import re
from decimal import Decimal, InvalidOperation
from app.extensions import db
from app.core.utils.decorators import transactional
from app.core.utils.qrcode_util import generate_tracking_code
from app.core.exceptions import NotFoundError, ValidationError, ConflictError
from app.core.audit.services.audit_services import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.lab_enums import LabOrderStatus, LabResultFlag
from app.modules.lab.models.lab_model import LabTest, LabOrder, LabOrderItem


# ---------------------------------------------------------------------
# Lab test catalog
# ---------------------------------------------------------------------

def get_lab_test(test_id: int) -> LabTest:
    test = LabTest.query.get(test_id)
    if test is None:
        raise NotFoundError(f"Lab test {test_id} not found")
    return test


def list_lab_tests(clinic_id: int | None = None, active_only: bool = True) -> list[LabTest]:
    """
    clinic_id=None returns the global catalog only. Pass a clinic_id to
    get that clinic's own tests PLUS the global catalog (clinic_id IS NULL),
    since a clinic-specific order screen should show both.
    """
    query = LabTest.query
    if clinic_id is not None:
        query = query.filter(db.or_(LabTest.clinic_id == clinic_id, LabTest.clinic_id.is_(None)))
    if active_only:
        query = query.filter_by(is_active=True)
    return query.order_by(LabTest.name).all()


@transactional
def create_lab_test(name: str, **fields) -> LabTest:
    if not name or not name.strip():
        raise ValidationError("Lab test name is required")

    code = fields.get("code")
    if code and LabTest.query.filter_by(code=code).first():
        raise ConflictError(f"Lab test code '{code}' already exists")

    critical_low = fields.get("critical_low")
    critical_high = fields.get("critical_high")
    if critical_low is not None and critical_high is not None and critical_low >= critical_high:
        raise ValidationError("critical_low must be less than critical_high")

    test = LabTest(name=name.strip(), **fields)
    db.session.add(test)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="LabTest",
        entity_id=test.id,
        description=f"Lab test '{test.name}' added to catalog",
        new_value={"name": test.name, "code": test.code},
    )
    return test


@transactional
def update_lab_test(test_id: int, **fields) -> LabTest:
    test = get_lab_test(test_id)

    # Validate the resulting critical thresholds make sense even when
    # only one side of the pair is being changed in this call.
    new_low = fields.get("critical_low", test.critical_low)
    new_high = fields.get("critical_high", test.critical_high)
    if new_low is not None and new_high is not None and new_low >= new_high:
        raise ValidationError("critical_low must be less than critical_high")

    old_value, new_value = {}, {}
    for key, new_val in fields.items():
        current_val = getattr(test, key)
        if current_val != new_val:
            old_value[key] = current_val.value if hasattr(current_val, "value") else current_val
            new_value[key] = new_val.value if hasattr(new_val, "value") else new_val
            setattr(test, key, new_val)

    if new_value:
        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="LabTest",
            entity_id=test.id,
            description=f"Lab test '{test.name}' updated",
            old_value=old_value,
            new_value=new_value,
        )
    return test


# ---------------------------------------------------------------------
# Lab orders
# ---------------------------------------------------------------------

def get_lab_order(order_id: int) -> LabOrder:
    order = LabOrder.query.get(order_id)
    if order is None:
        raise NotFoundError(f"Lab order {order_id} not found")
    return order


def list_orders_for_patient(patient_id: int) -> list[LabOrder]:
    return (
        LabOrder.query.filter_by(patient_id=patient_id)
        .order_by(LabOrder.created_at.desc())
        .all()
    )


def _generate_qr_code() -> str:
    return generate_tracking_code(prefix="LAB")


@transactional
def create_lab_order(clinic_id: int, patient_id: int, ordered_by_id: int,
                      test_ids: list[int], consultation_id: int | None = None) -> LabOrder:
    if not test_ids:
        raise ValidationError("A lab order must include at least one test")

    tests = LabTest.query.filter(LabTest.id.in_(test_ids)).all()
    found_ids = {t.id for t in tests}
    missing = set(test_ids) - found_ids
    if missing:
        raise NotFoundError(f"Lab test(s) not found: {sorted(missing)}")

    invalid_clinic = [t.id for t in tests if t.clinic_id is not None and t.clinic_id != clinic_id]
    if invalid_clinic:
        raise ValidationError(f"Test(s) {invalid_clinic} do not belong to clinic {clinic_id}")

    inactive = [t.id for t in tests if not t.is_active]
    if inactive:
        raise ValidationError(f"Test(s) {inactive} are inactive and cannot be ordered")

    # qr_code has a unique constraint — retry on the rare collision
    # rather than trusting a single random draw.
    qr_code = _generate_qr_code()
    for _ in range(5):
        if not LabOrder.query.filter_by(qr_code=qr_code).first():
            break
        qr_code = _generate_qr_code()
    else:
        raise ConflictError("Could not generate a unique QR code, try again")

    order = LabOrder(
        clinic_id=clinic_id,
        patient_id=patient_id,
        consultation_id=consultation_id,
        ordered_by_id=ordered_by_id,
        status=LabOrderStatus.ORDERED,
        qr_code=qr_code,
    )
    db.session.add(order)
    db.session.flush()

    for test in tests:
        db.session.add(LabOrderItem(order_id=order.id, test_id=test.id))

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="LabOrder",
        entity_id=order.id,
        description=f"Lab order created for patient {patient_id} ({len(tests)} test(s))",
        new_value={"test_ids": sorted(found_ids), "qr_code": qr_code},
    )
    return order


def _assert_status(order: LabOrder, *allowed: LabOrderStatus):
    if order.status not in allowed:
        raise ConflictError(
            f"Lab order {order.id} is '{order.status.value}', "
            f"expected one of {[s.value for s in allowed]}"
        )


@transactional
def collect_sample(order_id: int, scanned_qr_code: str | None = None) -> LabOrder:
    order = get_lab_order(order_id)
    _assert_status(order, LabOrderStatus.ORDERED)

    if scanned_qr_code and order.qr_code and scanned_qr_code != order.qr_code:
        raise ConflictError("Scanned QR code does not match this lab order")

    order.status = LabOrderStatus.SAMPLE_COLLECTED
    order.sample_collected_at = db.func.now()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="LabOrder",
        entity_id=order.id,
        description="Sample collected",
        old_value={"status": LabOrderStatus.ORDERED.value},
        new_value={"status": order.status.value},
    )
    return order


@transactional
def link_equipment(order_id: int, equipment_reference_id: str) -> LabOrder:
    """Called when the sample is loaded onto/processed by lab equipment."""
    order = get_lab_order(order_id)
    _assert_status(order, LabOrderStatus.SAMPLE_COLLECTED)

    order.equipment_reference_id = equipment_reference_id
    order.status = LabOrderStatus.IN_PROGRESS

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="LabOrder",
        entity_id=order.id,
        description=f"Linked to equipment reference '{equipment_reference_id}'",
        old_value={"status": LabOrderStatus.SAMPLE_COLLECTED.value},
        new_value={"status": order.status.value, "equipment_reference_id": equipment_reference_id},
    )
    return order


@transactional
def cancel_order(order_id: int, reason: str | None = None) -> LabOrder:
    order = get_lab_order(order_id)
    if order.status in (LabOrderStatus.COMPLETED, LabOrderStatus.CANCELLED):
        raise ConflictError(f"Cannot cancel a lab order that is already {order.status.value}")

    old_status = order.status.value
    order.status = LabOrderStatus.CANCELLED
    order.cancellation_reason = reason

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="LabOrder",
        entity_id=order.id,
        description="Lab order cancelled" + (f": {reason}" if reason else ""),
        old_value={"status": old_status},
        new_value={"status": order.status.value, "cancellation_reason": reason},
    )
    return order


# ---------------------------------------------------------------------
# Result entry + auto-flagging
# ---------------------------------------------------------------------

_RANGE_PATTERN = re.compile(
    r"^\s*(?P<low>-?\d+(\.\d+)?)\s*-\s*(?P<high>-?\d+(\.\d+)?)\s*$"
)
_BOUND_PATTERN = re.compile(
    r"^\s*(?P<op><=|>=|<|>)\s*(?P<bound>-?\d+(\.\d+)?)\s*$"
)


def _auto_flag(test: LabTest, result_value: str) -> LabResultFlag | None:
    """
    Priority: CRITICAL (if thresholds are set and breached) >
    NORMAL/ABNORMAL (if reference_range is numeric and parseable) >
    None (leave it to a human — e.g. non-numeric results like "reactive").
    Never guesses: any value or range this can't parse returns None
    rather than assuming NORMAL.
    """
    try:
        value = float(Decimal(result_value.strip()))
    except (InvalidOperation, ValueError, AttributeError):
        return None  # non-numeric result — leave to human

    if test.critical_low is not None and value <= float(test.critical_low):
        return LabResultFlag.CRITICAL
    if test.critical_high is not None and value >= float(test.critical_high):
        return LabResultFlag.CRITICAL

    reference_range = test.reference_range
    if not reference_range:
        return None

    range_match = _RANGE_PATTERN.match(reference_range)
    if range_match:
        low, high = float(range_match["low"]), float(range_match["high"])
        return LabResultFlag.NORMAL if low <= value <= high else LabResultFlag.ABNORMAL

    bound_match = _BOUND_PATTERN.match(reference_range)
    if bound_match:
        op, bound = bound_match["op"], float(bound_match["bound"])
        in_range = {
            "<": value < bound, "<=": value <= bound,
            ">": value > bound, ">=": value >= bound,
        }[op]
        return LabResultFlag.NORMAL if in_range else LabResultFlag.ABNORMAL

    return None  # unrecognized format — leave to human


@transactional
def enter_result(order_item_id: int, result_value: str, flag: LabResultFlag | None = None,
                  result_notes: str | None = None, result_file_url: str | None = None) -> LabOrderItem:
    item = LabOrderItem.query.get(order_item_id)
    if item is None:
        raise NotFoundError(f"Lab order item {order_item_id} not found")

    order = item.order
    _assert_status(order, LabOrderStatus.SAMPLE_COLLECTED, LabOrderStatus.IN_PROGRESS)

    # Explicit flag from the caller (e.g. a lab tech overriding, or
    # setting CRITICAL manually) always wins over auto-detection.
    resolved_flag = flag or _auto_flag(item.test, result_value)

    item.result_value = result_value
    item.flag = resolved_flag
    item.result_notes = result_notes
    item.result_file_url = result_file_url
    item.resulted_at = db.func.now()

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="LabOrderItem",
        entity_id=item.id,
        description=f"Result entered for test '{item.test.name}'"
        + (" [AUTO-FLAGGED]" if flag is None and resolved_flag else ""),
        new_value={"result_value": result_value, "flag": resolved_flag.value if resolved_flag else None},
    )

    # If every item on the order now has a result, the order is complete.
    db.session.flush()
    remaining = [i for i in order.items if i.resulted_at is None]
    if not remaining:
        order.status = LabOrderStatus.COMPLETED
        order.completed_at = db.func.now()
        create_audit_log(
            action=AuditAction.STATUS_CHANGE,
            entity_type="LabOrder",
            entity_id=order.id,
            description="All results entered — order completed",
            new_value={"status": order.status.value},
        )

    return item