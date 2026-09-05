from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.core.enums.role_enums import Role
from app.core.utils.decorators import role_required

from app.modules.lab.schemas.lab_schema import (
    LabEquipmentLinkSchema,
    LabOrderCancelSchema,
    LabOrderCreateSchema,
    LabOrderListQuerySchema,
    LabResultCreateSchema,
    LabSampleCollectionSchema,
    LabTestCreateSchema,
    LabTestListQuerySchema,
    LabTestUpdateSchema,
)

from app.modules.lab.services.lab_service import (
    cancel_order,
    collect_sample,
    create_lab_order,
    create_lab_test,
    enter_result,
    get_lab_order,
    get_lab_test,
    link_equipment,
    list_lab_tests,
    list_orders_for_patient,
    update_lab_test,
)


lab_bp = Blueprint(
    "lab",
    __name__,
    url_prefix="/api/lab",
)


# ---------------------------------------------------------------------
# Role groups
# ---------------------------------------------------------------------

LAB_MANAGEMENT_ROLES = (
    Role.ADMIN,
)

LAB_CLINICAL_ROLES = (
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
)

LAB_TECHNICIAN_ROLES = (
    Role.ADMIN,
    Role.LAB_TECHNICIAN,
)

LAB_VIEW_ROLES = (
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
    Role.RECEPTIONIST,
    Role.LAB_TECHNICIAN,
)


# ---------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------


def _serialize_lab_test(test):
    return {
        "id": test.id,
        "clinic_id": test.clinic_id,
        "loinc_code": test.loinc_code,
        "name": test.name,
        "code": test.code,
        "sample_type": (
            test.sample_type.value
            if test.sample_type
            else None
        ),
        "reference_range": test.reference_range,
        "unit": test.unit,
        "price": (
            str(test.price)
            if test.price is not None
            else None
        ),
        "critical_low": (
            str(test.critical_low)
            if test.critical_low is not None
            else None
        ),
        "critical_high": (
            str(test.critical_high)
            if test.critical_high is not None
            else None
        ),
        "is_active": test.is_active,
        "created_at": (
            test.created_at.isoformat()
            if test.created_at
            else None
        ),
        "updated_at": (
            test.updated_at.isoformat()
            if test.updated_at
            else None
        ),
    }


def _serialize_lab_order_item(item):
    return {
        "id": item.id,
        "order_id": item.order_id,
        "test_id": item.test_id,
        "test": (
            _serialize_lab_test(item.test)
            if item.test
            else None
        ),
        "result_value": item.result_value,
        "flag": (
            item.flag.value
            if item.flag
            else None
        ),
        "result_notes": item.result_notes,
        "result_file_url": item.result_file_url,
        "resulted_at": (
            item.resulted_at.isoformat()
            if item.resulted_at
            else None
        ),
    }


def _serialize_lab_order(order):
    return {
        "id": order.id,
        "clinic_id": order.clinic_id,
        "patient_id": order.patient_id,
        "consultation_id": order.consultation_id,
        "ordered_by_id": order.ordered_by_id,
        "status": (
            order.status.value
            if order.status
            else None
        ),
        "qr_code": order.qr_code,
        "sample_collected_at": (
            order.sample_collected_at.isoformat()
            if order.sample_collected_at
            else None
        ),
        "equipment_reference_id": order.equipment_reference_id,
        "cancellation_reason": order.cancellation_reason,
        "completed_at": (
            order.completed_at.isoformat()
            if order.completed_at
            else None
        ),
        "created_at": (
            order.created_at.isoformat()
            if order.created_at
            else None
        ),
        "updated_at": (
            order.updated_at.isoformat()
            if order.updated_at
            else None
        ),
        "items": [
            _serialize_lab_order_item(item)
            for item in order.items
        ],
    }


# ---------------------------------------------------------------------
# Lab test catalog
# ---------------------------------------------------------------------


@lab_bp.post("/tests")
@role_required(*LAB_MANAGEMENT_ROLES)
def create_lab_test_route():
    data = LabTestCreateSchema.model_validate(
        request.get_json(silent=True) or {}
    )

    test = create_lab_test(
        name=data.name,
        loinc_code=data.loinc_code,
        code=data.code,
        sample_type=data.sample_type,
        reference_range=data.reference_range,
        unit=data.unit,
        price=data.price,
        critical_low=data.critical_low,
        critical_high=data.critical_high,
        is_active=data.is_active,
    )

    return jsonify({
        "success": True,
        "message": "Lab test created successfully",
        "data": _serialize_lab_test(test),
    }), 201


@lab_bp.get("/tests")
@role_required(*LAB_VIEW_ROLES)
def list_lab_tests_route():
    data = LabTestListQuerySchema.model_validate(
        request.args.to_dict()
    )

    tests = list_lab_tests(
        clinic_id=data.clinic_id,
        active_only=data.active_only,
    )

    return jsonify({
        "success": True,
        "data": [
            _serialize_lab_test(test)
            for test in tests
        ],
    }), 200


@lab_bp.get("/tests/<int:test_id>")
@role_required(*LAB_VIEW_ROLES)
def get_lab_test_route(test_id: int):
    test = get_lab_test(test_id)

    return jsonify({
        "success": True,
        "data": _serialize_lab_test(test),
    }), 200


@lab_bp.patch("/tests/<int:test_id>")
@role_required(*LAB_MANAGEMENT_ROLES)
def update_lab_test_route(test_id: int):
    data = LabTestUpdateSchema.model_validate(
        request.get_json(silent=True) or {}
    )

    fields = data.model_dump(
        exclude_unset=True,
    )

    test = update_lab_test(
        test_id=test_id,
        **fields,
    )

    return jsonify({
        "success": True,
        "message": "Lab test updated successfully",
        "data": _serialize_lab_test(test),
    }), 200


# ---------------------------------------------------------------------
# Lab orders
# ---------------------------------------------------------------------


@lab_bp.post("/orders")
@role_required(*LAB_CLINICAL_ROLES)
def create_lab_order_route():
    data = LabOrderCreateSchema.model_validate(
        request.get_json(silent=True) or {}
    )

    order = create_lab_order(
        clinic_id=data.clinic_id,
        patient_id=data.patient_id,
        ordered_by_id=data.ordered_by_id,
        test_ids=data.test_ids,
        consultation_id=data.consultation_id,
    )

    return jsonify({
        "success": True,
        "message": "Lab order created successfully",
        "data": _serialize_lab_order(order),
    }), 201


@lab_bp.get("/orders/<int:order_id>")
@role_required(*LAB_VIEW_ROLES)
def get_lab_order_route(order_id: int):
    order = get_lab_order(order_id)

    return jsonify({
        "success": True,
        "data": _serialize_lab_order(order),
    }), 200


@lab_bp.get("/orders")
@role_required(*LAB_VIEW_ROLES)
def list_orders_for_patient_route():
    data = LabOrderListQuerySchema.model_validate(
        request.args.to_dict()
    )

    orders = list_orders_for_patient(
        patient_id=data.patient_id,
    )

    return jsonify({
        "success": True,
        "data": [
            _serialize_lab_order(order)
            for order in orders
        ],
    }), 200


# ---------------------------------------------------------------------
# Sample collection
# ---------------------------------------------------------------------


@lab_bp.post("/orders/<int:order_id>/collect-sample")
@role_required(*LAB_TECHNICIAN_ROLES)
def collect_sample_route(order_id: int):
    data = LabSampleCollectionSchema.model_validate(
        request.get_json(silent=True) or {}
    )

    order = collect_sample(
        order_id=order_id,
        scanned_qr_code=data.scanned_qr_code,
    )

    return jsonify({
        "success": True,
        "message": "Lab sample collected successfully",
        "data": _serialize_lab_order(order),
    }), 200


# ---------------------------------------------------------------------
# Equipment
# ---------------------------------------------------------------------


@lab_bp.post("/orders/<int:order_id>/equipment")
@role_required(*LAB_TECHNICIAN_ROLES)
def link_equipment_route(order_id: int):
    data = LabEquipmentLinkSchema.model_validate(
        request.get_json(silent=True) or {}
    )

    order = link_equipment(
        order_id=order_id,
        equipment_reference_id=data.equipment_reference_id,
    )

    return jsonify({
        "success": True,
        "message": "Lab order linked to equipment successfully",
        "data": _serialize_lab_order(order),
    }), 200


# ---------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------


@lab_bp.post("/order-items/<int:order_item_id>/result")
@role_required(*LAB_TECHNICIAN_ROLES)
def enter_result_route(order_item_id: int):
    data = LabResultCreateSchema.model_validate(
        request.get_json(silent=True) or {}
    )

    item = enter_result(
        order_item_id=order_item_id,
        result_value=data.result_value,
        flag=data.flag,
        result_notes=data.result_notes,
        result_file_url=data.result_file_url,
    )

    return jsonify({
        "success": True,
        "message": "Lab result entered successfully",
        "data": _serialize_lab_order_item(item),
    }), 200


# ---------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------


@lab_bp.post("/orders/<int:order_id>/cancel")
@role_required(*LAB_CLINICAL_ROLES)
def cancel_order_route(order_id: int):
    data = LabOrderCancelSchema.model_validate(
        request.get_json(silent=True) or {}
    )

    order = cancel_order(
        order_id=order_id,
        reason=data.reason,
    )

    return jsonify({
        "success": True,
        "message": "Lab order cancelled successfully",
        "data": _serialize_lab_order(order),
    }), 200