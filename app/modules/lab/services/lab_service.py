import re
from decimal import Decimal, InvalidOperation

from app.extensions import db
from app.core.utils.decorators import transactional
from app.core.utils.qrcode_util import generate_tracking_code
from app.core.exceptions import (
    NotFoundError,
    ValidationError,
    ConflictError,
)
from app.core.audit.services.audit_services import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.lab_enums import LabOrderStatus, LabResultFlag

from app.modules.lab.models.lab_model import (
    LabTest,
    LabOrder,
    LabOrderItem,
)

from app.modules.clinic.services.clinic_service import ensure_clinic_active
from app.modules.patient.models.patient_model import Patient
from app.modules.staff.models.staff_model import Staff


_EDITABLE_LAB_TEST_FIELDS = {
    "loinc_code",
    "code",
    "sample_type",
    "reference_range",
    "unit",
    "price",
    "critical_low",
    "critical_high",
    "is_active",
}


# ---------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------


def _get_patient(patient_id: int) -> Patient:
    patient = Patient.query.get(patient_id)

    if patient is None:
        raise NotFoundError(
            f"Patient {patient_id} not found"
        )

    return patient


def _get_staff(staff_id: int) -> Staff:
    staff = Staff.query.get(staff_id)

    if staff is None:
        raise NotFoundError(
            f"Staff {staff_id} not found"
        )

    return staff


def _validate_patient_clinic(
    patient: Patient,
    clinic_id: int,
) -> None:
    if patient.clinic_id != clinic_id:
        raise ValidationError(
            f"Patient {patient.id} does not belong to clinic {clinic_id}"
        )


def _validate_staff_clinic(
    staff: Staff,
    clinic_id: int,
) -> None:
    if staff.clinic_id != clinic_id:
        raise ValidationError(
            f"Staff {staff.id} does not belong to clinic {clinic_id}"
        )


def _validate_staff_active(staff: Staff) -> None:
    # Keep this deliberately limited to ACTIVE because the exact
    # StaffStatus enum is the project's source of truth.
    from app.core.enums.staff_enums import StaffStatus

    if staff.status != StaffStatus.ACTIVE:
        raise ValidationError(
            f"Staff {staff.id} is not active"
        )


def _get_consultation(consultation_id: int):
    """
    Import lazily so the Lab service does not create an unnecessary
    import-cycle risk during application startup.
    """
    from app.modules.consultation.models.consultation_model import Consultation

    consultation = Consultation.query.get(consultation_id)

    if consultation is None:
        raise NotFoundError(
            f"Consultation {consultation_id} not found"
        )

    return consultation


def _validate_consultation(
    consultation,
    clinic_id: int,
    patient_id: int,
) -> None:
    if consultation.clinic_id != clinic_id:
        raise ValidationError(
            f"Consultation {consultation.id} does not belong "
            f"to clinic {clinic_id}"
        )

    if consultation.patient_id != patient_id:
        raise ValidationError(
            f"Consultation {consultation.id} does not belong "
            f"to patient {patient_id}"
        )


# ---------------------------------------------------------------------
# Lab test catalog
# ---------------------------------------------------------------------


def get_lab_test(test_id: int) -> LabTest:
    test = LabTest.query.get(test_id)

    if test is None:
        raise NotFoundError(
            f"Lab test {test_id} not found"
        )

    return test


def list_lab_tests(
    clinic_id: int | None = None,
    active_only: bool = True,
) -> list[LabTest]:
    """
    clinic_id=None returns the global catalog only.

    When clinic_id is supplied, return:
        - clinic-specific tests
        - global tests where clinic_id IS NULL
    """

    query = LabTest.query

    if clinic_id is not None:
        query = query.filter(
            db.or_(
                LabTest.clinic_id == clinic_id,
                LabTest.clinic_id.is_(None),
            )
        )
    else:
        query = query.filter(
            LabTest.clinic_id.is_(None)
        )

    if active_only:
        query = query.filter(
            LabTest.is_active.is_(True)
        )

    return (
        query
        .order_by(LabTest.name)
        .all()
    )


@transactional
def create_lab_test(
    name: str,
    **fields,
) -> LabTest:
    if not name or not name.strip():
        raise ValidationError(
            "Lab test name is required"
        )

    unknown = set(fields) - _EDITABLE_LAB_TEST_FIELDS

    if unknown:
        raise ValidationError(
            "Unknown lab test field(s): "
            f"{', '.join(sorted(unknown))}"
        )

    code = fields.get("code")

    if code:
        code = code.strip()

        existing = LabTest.query.filter_by(
            code=code
        ).first()

        if existing:
            raise ConflictError(
                f"Lab test code '{code}' already exists"
            )

        fields["code"] = code

    critical_low = fields.get("critical_low")
    critical_high = fields.get("critical_high")

    if (
        critical_low is not None
        and critical_high is not None
        and critical_low >= critical_high
    ):
        raise ValidationError(
            "critical_low must be less than critical_high"
        )

    test = LabTest(
        name=name.strip(),
        **fields,
    )

    db.session.add(test)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="LabTest",
        entity_id=test.id,
        description=(
            f"Lab test '{test.name}' added to catalog"
        ),
        new_value={
            "name": test.name,
            "code": test.code,
        },
    )

    return test


@transactional
def update_lab_test(
    test_id: int,
    **fields,
) -> LabTest:
    test = get_lab_test(test_id)

    unknown = set(fields) - _EDITABLE_LAB_TEST_FIELDS

    if unknown:
        raise ValidationError(
            "Unknown lab test field(s): "
            f"{', '.join(sorted(unknown))}"
        )

    if "code" in fields and fields["code"]:
        fields["code"] = fields["code"].strip()

        existing = (
            LabTest.query
            .filter(
                LabTest.code == fields["code"],
                LabTest.id != test.id,
            )
            .first()
        )

        if existing:
            raise ConflictError(
                f"Lab test code '{fields['code']}' already exists"
            )

    # Validate resulting critical thresholds.
    new_low = fields.get(
        "critical_low",
        test.critical_low,
    )

    new_high = fields.get(
        "critical_high",
        test.critical_high,
    )

    if (
        new_low is not None
        and new_high is not None
        and new_low >= new_high
    ):
        raise ValidationError(
            "critical_low must be less than critical_high"
        )

    old_value = {}
    new_value = {}

    for key, new_val in fields.items():
        current_val = getattr(test, key)

        if current_val != new_val:
            old_value[key] = (
                current_val.value
                if hasattr(current_val, "value")
                else current_val
            )

            new_value[key] = (
                new_val.value
                if hasattr(new_val, "value")
                else new_val
            )

            setattr(test, key, new_val)

    if new_value:
        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="LabTest",
            entity_id=test.id,
            description=(
                f"Lab test '{test.name}' updated"
            ),
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
        raise NotFoundError(
            f"Lab order {order_id} not found"
        )

    return order


def list_orders_for_patient(
    patient_id: int,
) -> list[LabOrder]:
    return (
        LabOrder.query
        .filter_by(patient_id=patient_id)
        .order_by(LabOrder.created_at.desc())
        .all()
    )


def _generate_qr_code() -> str:
    return generate_tracking_code(
        prefix="LAB"
    )


@transactional
def create_lab_order(
    clinic_id: int,
    patient_id: int,
    ordered_by_id: int,
    test_ids: list[int],
    consultation_id: int | None = None,
) -> LabOrder:

    # -------------------------------------------------------------
    # Clinic lifecycle
    # -------------------------------------------------------------

    ensure_clinic_active(clinic_id)

    # -------------------------------------------------------------
    # Basic validation
    # -------------------------------------------------------------

    if not test_ids:
        raise ValidationError(
            "A lab order must include at least one test"
        )

    if len(test_ids) != len(set(test_ids)):
        raise ValidationError(
            "Duplicate test IDs are not allowed"
        )

    # -------------------------------------------------------------
    # Patient validation
    # -------------------------------------------------------------

    patient = _get_patient(patient_id)

    _validate_patient_clinic(
        patient,
        clinic_id,
    )

    # -------------------------------------------------------------
    # Ordering staff validation
    # -------------------------------------------------------------

    staff = _get_staff(ordered_by_id)

    _validate_staff_clinic(
        staff,
        clinic_id,
    )

    _validate_staff_active(staff)

    # -------------------------------------------------------------
    # Consultation validation
    # -------------------------------------------------------------

    if consultation_id is not None:
        consultation = _get_consultation(
            consultation_id
        )

        _validate_consultation(
            consultation,
            clinic_id,
            patient_id,
        )

    # -------------------------------------------------------------
    # Test validation
    # -------------------------------------------------------------

    tests = (
        LabTest.query
        .filter(LabTest.id.in_(test_ids))
        .all()
    )

    found_ids = {
        test.id
        for test in tests
    }

    missing = set(test_ids) - found_ids

    if missing:
        raise NotFoundError(
            f"Lab test(s) not found: "
            f"{sorted(missing)}"
        )

    invalid_clinic = [
        test.id
        for test in tests
        if (
            test.clinic_id is not None
            and test.clinic_id != clinic_id
        )
    ]

    if invalid_clinic:
        raise ValidationError(
            f"Test(s) {invalid_clinic} do not belong "
            f"to clinic {clinic_id}"
        )

    inactive = [
        test.id
        for test in tests
        if not test.is_active
    ]

    if inactive:
        raise ValidationError(
            f"Test(s) {inactive} are inactive "
            "and cannot be ordered"
        )

    # -------------------------------------------------------------
    # QR code generation
    # -------------------------------------------------------------

    qr_code = _generate_qr_code()

    for _ in range(5):
        if not LabOrder.query.filter_by(
            qr_code=qr_code
        ).first():
            break

        qr_code = _generate_qr_code()

    else:
        raise ConflictError(
            "Could not generate a unique QR code, "
            "try again"
        )

    # -------------------------------------------------------------
    # Create order
    # -------------------------------------------------------------

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
        db.session.add(
            LabOrderItem(
                order_id=order.id,
                test_id=test.id,
            )
        )

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="LabOrder",
        entity_id=order.id,
        description=(
            f"Lab order created for patient "
            f"{patient_id} ({len(tests)} test(s))"
        ),
        new_value={
            "clinic_id": clinic_id,
            "patient_id": patient_id,
            "ordered_by_id": ordered_by_id,
            "test_ids": sorted(found_ids),
            "qr_code": qr_code,
        },
    )

    return order


def _assert_status(
    order: LabOrder,
    *allowed: LabOrderStatus,
):
    if order.status not in allowed:
        raise ConflictError(
            f"Lab order {order.id} is "
            f"'{order.status.value}', "
            f"expected one of "
            f"{[status.value for status in allowed]}"
        )


# ---------------------------------------------------------------------
# Sample collection
# ---------------------------------------------------------------------


@transactional
def collect_sample(
    order_id: int,
    scanned_qr_code: str | None = None,
) -> LabOrder:

    order = get_lab_order(order_id)

    # The order belongs to a clinic, so operational changes require
    # that clinic to still be active.
    ensure_clinic_active(order.clinic_id)

    _assert_status(
        order,
        LabOrderStatus.ORDERED,
    )

    if (
        scanned_qr_code
        and order.qr_code
        and scanned_qr_code != order.qr_code
    ):
        raise ConflictError(
            "Scanned QR code does not match "
            "this lab order"
        )

    order.status = LabOrderStatus.SAMPLE_COLLECTED
    order.sample_collected_at = db.func.now()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="LabOrder",
        entity_id=order.id,
        description="Sample collected",
        old_value={
            "status": LabOrderStatus.ORDERED.value
        },
        new_value={
            "status": order.status.value
        },
    )

    return order


# ---------------------------------------------------------------------
# Equipment processing
# ---------------------------------------------------------------------


@transactional
def link_equipment(
    order_id: int,
    equipment_reference_id: str,
) -> LabOrder:
    """Link a collected sample to laboratory equipment."""

    order = get_lab_order(order_id)

    ensure_clinic_active(order.clinic_id)

    if (
        not equipment_reference_id
        or not equipment_reference_id.strip()
    ):
        raise ValidationError(
            "Equipment reference ID is required"
        )

    equipment_reference_id = (
        equipment_reference_id.strip()
    )

    _assert_status(
        order,
        LabOrderStatus.SAMPLE_COLLECTED,
    )

    order.equipment_reference_id = (
        equipment_reference_id
    )

    order.status = LabOrderStatus.IN_PROGRESS

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="LabOrder",
        entity_id=order.id,
        description=(
            "Linked to equipment reference "
            f"'{equipment_reference_id}'"
        ),
        old_value={
            "status": LabOrderStatus.SAMPLE_COLLECTED.value
        },
        new_value={
            "status": order.status.value,
            "equipment_reference_id": (
                equipment_reference_id
            ),
        },
    )

    return order


# ---------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------


@transactional
def cancel_order(
    order_id: int,
    reason: str | None = None,
) -> LabOrder:

    order = get_lab_order(order_id)

    ensure_clinic_active(order.clinic_id)

    if order.status in (
        LabOrderStatus.COMPLETED,
        LabOrderStatus.CANCELLED,
    ):
        raise ConflictError(
            "Cannot cancel a lab order that is already "
            f"{order.status.value}"
        )

    if reason is not None:
        reason = reason.strip()

        if not reason:
            reason = None

    old_status = order.status.value

    order.status = LabOrderStatus.CANCELLED
    order.cancellation_reason = reason

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="LabOrder",
        entity_id=order.id,
        description=(
            "Lab order cancelled"
            + (f": {reason}" if reason else "")
        ),
        old_value={
            "status": old_status
        },
        new_value={
            "status": order.status.value,
            "cancellation_reason": reason,
        },
    )

    return order


# ---------------------------------------------------------------------
# Result entry + automatic flagging
# ---------------------------------------------------------------------


_RANGE_PATTERN = re.compile(
    r"^\s*"
    r"(?P<low>-?\d+(\.\d+)?)"
    r"\s*-\s*"
    r"(?P<high>-?\d+(\.\d+)?)"
    r"\s*$"
)

_BOUND_PATTERN = re.compile(
    r"^\s*"
    r"(?P<op><=|>=|<|>)"
    r"\s*"
    r"(?P<bound>-?\d+(\.\d+)?)"
    r"\s*$"
)


def _auto_flag(
    test: LabTest,
    result_value: str,
) -> LabResultFlag | None:
    """
    Determine a result flag automatically.

    Priority:

        CRITICAL
            ↓
        NORMAL / ABNORMAL
            ↓
        None

    Critical thresholds take precedence over the normal reference
    range.

    Non-numeric results or unsupported reference-range formats are
    deliberately left unflagged rather than guessed.
    """

    try:
        value = float(
            Decimal(result_value.strip())
        )

    except (
        InvalidOperation,
        ValueError,
        AttributeError,
    ):
        return None

    # Critical thresholds.
    if (
        test.critical_low is not None
        and value <= float(test.critical_low)
    ):
        return LabResultFlag.CRITICAL

    if (
        test.critical_high is not None
        and value >= float(test.critical_high)
    ):
        return LabResultFlag.CRITICAL

    reference_range = test.reference_range

    if not reference_range:
        return None

    # Numeric range: "10 - 20"
    range_match = _RANGE_PATTERN.match(
        reference_range
    )

    if range_match:
        low = float(
            range_match["low"]
        )

        high = float(
            range_match["high"]
        )

        return (
            LabResultFlag.NORMAL
            if low <= value <= high
            else LabResultFlag.ABNORMAL
        )

    # Numeric bound: "< 10", ">= 5", etc.
    bound_match = _BOUND_PATTERN.match(
        reference_range
    )

    if bound_match:
        op = bound_match["op"]

        bound = float(
            bound_match["bound"]
        )

        in_range = {
            "<": value < bound,
            "<=": value <= bound,
            ">": value > bound,
            ">=": value >= bound,
        }[op]

        return (
            LabResultFlag.NORMAL
            if in_range
            else LabResultFlag.ABNORMAL
        )

    # Unsupported/non-numeric reference range.
    return None


@transactional
def enter_result(
    order_item_id: int,
    result_value: str,
    flag: LabResultFlag | None = None,
    result_notes: str | None = None,
    result_file_url: str | None = None,
) -> LabOrderItem:

    if not result_value or not result_value.strip():
        raise ValidationError(
            "Result value is required"
        )

    item = LabOrderItem.query.get(
        order_item_id
    )

    if item is None:
        raise NotFoundError(
            f"Lab order item {order_item_id} not found"
        )

    order = item.order

    ensure_clinic_active(
        order.clinic_id
    )

    _assert_status(
        order,
        LabOrderStatus.SAMPLE_COLLECTED,
        LabOrderStatus.IN_PROGRESS,
    )

    result_value = result_value.strip()

    if result_notes is not None:
        result_notes = result_notes.strip()

    if result_file_url is not None:
        result_file_url = result_file_url.strip()

    # Explicit caller flag always wins over automatic detection.
    resolved_flag = (
        flag
        or _auto_flag(
            item.test,
            result_value,
        )
    )

    item.result_value = result_value
    item.flag = resolved_flag
    item.result_notes = result_notes
    item.result_file_url = result_file_url
    item.resulted_at = db.func.now()

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="LabOrderItem",
        entity_id=item.id,
        description=(
            f"Result entered for test "
            f"'{item.test.name}'"
            + (
                " [AUTO-FLAGGED]"
                if flag is None and resolved_flag
                else ""
            )
        ),
        new_value={
            "result_value": result_value,
            "flag": (
                resolved_flag.value
                if resolved_flag
                else None
            ),
        },
    )

    # -------------------------------------------------------------
    # Automatically complete the order once every item has a result.
    # -------------------------------------------------------------

    db.session.flush()

    remaining = [
        order_item
        for order_item in order.items
        if order_item.resulted_at is None
    ]

    if not remaining:
        order.status = LabOrderStatus.COMPLETED
        order.completed_at = db.func.now()

        create_audit_log(
            action=AuditAction.STATUS_CHANGE,
            entity_type="LabOrder",
            entity_id=order.id,
            description=(
                "All results entered — order completed"
            ),
            new_value={
                "status": (
                    order.status.value
                )
            },
        )

    return item