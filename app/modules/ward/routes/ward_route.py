from flask import Blueprint, jsonify, request

from app.core.enums.role_enums import Role
from app.core.enums.ward_enums import BedStatus
from app.core.utils.decorators import role_required

from app.modules.ward.schemas.ward_schema import (
    WardCreateSchema,
)
from app.modules.ward.schemas.bed_schema import (
    BedCreateSchema,
    BedMaintenanceSchema,
    BedReservationCancelSchema,
    BedReservationCreateSchema,
)
from app.modules.ward.schemas.admission_schema import (
    AdmissionCreateSchema,
    AdmissionDischargeSchema,
    AdmissionFromReservationSchema,
    AdmissionTransferSchema,
)

from app.modules.ward.services.ward_service import (
    create_ward,
    get_ward,
    list_wards,
    get_ward_occupancy,
    add_bed,
    get_bed,
    list_beds,
    set_bed_maintenance,
    admit_patient,
    get_admission,
    list_admissions_for_patient,
    transfer_bed,
    discharge_patient,
    get_bed_reservation,
    list_bed_reservations,
    get_active_bed_reservation_for_patient,
    get_active_bed_reservation_for_bed,
    reserve_bed,
    cancel_bed_reservation,
    admit_patient_from_reservation,
)


ward_bp = Blueprint(
    "ward",
    __name__,
    url_prefix="/api/wards",
)


# ---------------------------------------------------------------------------
# ROLE GROUPS
# ---------------------------------------------------------------------------

MANAGEMENT_ROLES = (
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
)

CLINICAL_ROLES = (
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
)

VIEW_ROLES = (
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
    Role.RECEPTIONIST,
)


# ---------------------------------------------------------------------------
# SERIALIZERS
# ---------------------------------------------------------------------------

def _serialize_ward(ward):
    return {
        "id": ward.id,
        "clinic_id": ward.clinic_id,
        "name": ward.name,
        "ward_type": ward.ward_type.value,
        "capacity": ward.capacity,
        "created_at": (
            ward.created_at.isoformat()
            if ward.created_at
            else None
        ),
        "updated_at": (
            ward.updated_at.isoformat()
            if ward.updated_at
            else None
        ),
    }


def _serialize_bed(bed):
    return {
        "id": bed.id,
        "ward_id": bed.ward_id,
        "bed_number": bed.bed_number,
        "status": bed.status.value,
        "created_at": (
            bed.created_at.isoformat()
            if bed.created_at
            else None
        ),
        "updated_at": (
            bed.updated_at.isoformat()
            if bed.updated_at
            else None
        ),
    }


def _serialize_reservation(reservation):
    return {
        "id": reservation.id,
        "patient_id": reservation.patient_id,
        "bed_id": reservation.bed_id,
        "reserved_by_id": reservation.reserved_by_id,
        "status": reservation.status.value,
        "reason": reservation.reason,
        "reserved_at": (
            reservation.reserved_at.isoformat()
            if reservation.reserved_at
            else None
        ),
        "expires_at": (
            reservation.expires_at.isoformat()
            if reservation.expires_at
            else None
        ),
        "cancelled_at": (
            reservation.cancelled_at.isoformat()
            if reservation.cancelled_at
            else None
        ),
        "fulfilled_at": (
            reservation.fulfilled_at.isoformat()
            if reservation.fulfilled_at
            else None
        ),
    }


def _serialize_admission(admission):
    return {
        "id": admission.id,
        "patient_id": admission.patient_id,
        "bed_id": admission.bed_id,
        "admitted_by_id": admission.admitted_by_id,
        "reservation_id": admission.reservation_id,
        "status": admission.status.value,
        "reason": admission.reason,
        "admitted_at": (
            admission.admitted_at.isoformat()
            if admission.admitted_at
            else None
        ),
        "discharged_at": (
            admission.discharged_at.isoformat()
            if admission.discharged_at
            else None
        ),
        "created_at": (
            admission.created_at.isoformat()
            if admission.created_at
            else None
        ),
        "updated_at": (
            admission.updated_at.isoformat()
            if admission.updated_at
            else None
        ),
    }


def _serialize_transfer(transfer):
    return {
        "id": transfer.id,
        "admission_id": transfer.admission_id,
        "from_bed_id": transfer.from_bed_id,
        "to_bed_id": transfer.to_bed_id,
        "reason": transfer.reason,
        "created_at": (
            transfer.created_at.isoformat()
            if transfer.created_at
            else None
        ),
        "transferred_at": (
            transfer.transferred_at.isoformat()
            if transfer.transferred_at
            else None
        ),
    }


# ---------------------------------------------------------------------------
# WARDS
# ---------------------------------------------------------------------------

@ward_bp.post("")
@role_required(*MANAGEMENT_ROLES)
def create_ward_route():
    payload = WardCreateSchema.model_validate(
        request.get_json() or {}
    )

    ward = create_ward(
        clinic_id=payload.clinic_id,
        name=payload.name,
        ward_type=payload.ward_type,
        capacity=payload.capacity,
    )

    return jsonify({
        "message": "Ward created successfully",
        "data": _serialize_ward(ward),
    }), 201


@ward_bp.get("")
@role_required(*VIEW_ROLES)
def list_wards_route():
    clinic_id = request.args.get(
        "clinic_id",
        type=int,
    )

    wards = list_wards(
        clinic_id=clinic_id,
    )

    return jsonify({
        "data": [
            _serialize_ward(ward)
            for ward in wards
        ],
    }), 200


@ward_bp.get("/<int:ward_id>")
@role_required(*VIEW_ROLES)
def get_ward_route(ward_id: int):
    ward = get_ward(ward_id)

    return jsonify({
        "data": _serialize_ward(ward),
    }), 200


@ward_bp.get("/<int:ward_id>/occupancy")
@role_required(*VIEW_ROLES)
def get_ward_occupancy_route(ward_id: int):
    occupancy = get_ward_occupancy(ward_id)

    return jsonify({
        "data": occupancy,
    }), 200


# ---------------------------------------------------------------------------
# BEDS
# ---------------------------------------------------------------------------

@ward_bp.post("/<int:ward_id>/beds")
@role_required(*MANAGEMENT_ROLES)
def add_bed_route(ward_id: int):
    payload = BedCreateSchema.model_validate({
        **(request.get_json() or {}),
        "ward_id": ward_id,
    })

    bed = add_bed(
        ward_id=payload.ward_id,
        bed_number=payload.bed_number,
    )

    return jsonify({
        "message": "Bed added successfully",
        "data": _serialize_bed(bed),
    }), 201


@ward_bp.get("/<int:ward_id>/beds")
@role_required(*VIEW_ROLES)
def list_beds_route(ward_id: int):
    status = request.args.get("status")

    parsed_status = None

    if status:
        parsed_status = BedStatus(status)

    beds = list_beds(
        ward_id=ward_id,
        status=parsed_status,
    )

    return jsonify({
        "data": [
            _serialize_bed(bed)
            for bed in beds
        ],
    }), 200


@ward_bp.get("/beds/<int:bed_id>")
@role_required(*VIEW_ROLES)
def get_bed_route(bed_id: int):
    bed = get_bed(bed_id)

    return jsonify({
        "data": _serialize_bed(bed),
    }), 200


@ward_bp.patch("/beds/<int:bed_id>/maintenance")
@role_required(*MANAGEMENT_ROLES)
def set_bed_maintenance_route(bed_id: int):
    payload = BedMaintenanceSchema.model_validate(
        request.get_json() or {}
    )

    bed = set_bed_maintenance(
        bed_id=bed_id,
        under_maintenance=payload.under_maintenance,
    )

    return jsonify({
        "message": "Bed maintenance status updated",
        "data": _serialize_bed(bed),
    }), 200


# ---------------------------------------------------------------------------
# BED RESERVATIONS
# ---------------------------------------------------------------------------

@ward_bp.post("/reservations")
@role_required(*CLINICAL_ROLES)
def reserve_bed_route():
    payload = BedReservationCreateSchema.model_validate(
        request.get_json() or {}
    )

    reservation = reserve_bed(
        patient_id=payload.patient_id,
        bed_id=payload.bed_id,
        reserved_by_id=payload.reserved_by_id,
        reason=payload.reason,
        expires_at=payload.expires_at,
    )

    return jsonify({
        "message": "Bed reserved successfully",
        "data": _serialize_reservation(reservation),
    }), 201


@ward_bp.get("/reservations")
@role_required(*VIEW_ROLES)
def list_bed_reservations_route():
    clinic_id = request.args.get(
        "clinic_id",
        type=int,
    )

    patient_id = request.args.get(
        "patient_id",
        type=int,
    )

    bed_id = request.args.get(
        "bed_id",
        type=int,
    )

    reservations = list_bed_reservations(
        clinic_id=clinic_id,
        patient_id=patient_id,
        bed_id=bed_id,
    )

    return jsonify({
        "data": [
            _serialize_reservation(reservation)
            for reservation in reservations
        ],
    }), 200


@ward_bp.get("/reservations/<int:reservation_id>")
@role_required(*VIEW_ROLES)
def get_bed_reservation_route(reservation_id: int):
    reservation = get_bed_reservation(
        reservation_id,
    )

    return jsonify({
        "data": _serialize_reservation(reservation),
    }), 200


@ward_bp.get(
    "/patients/<int:patient_id>/reservation"
)
@role_required(*VIEW_ROLES)
def get_patient_active_reservation_route(patient_id: int):
    reservation = get_active_bed_reservation_for_patient(
        patient_id,
    )

    return jsonify({
        "data": (
            _serialize_reservation(reservation)
            if reservation
            else None
        ),
    }), 200


@ward_bp.get(
    "/beds/<int:bed_id>/reservation"
)
@role_required(*VIEW_ROLES)
def get_bed_active_reservation_route(bed_id: int):
    reservation = get_active_bed_reservation_for_bed(
        bed_id,
    )

    return jsonify({
        "data": (
            _serialize_reservation(reservation)
            if reservation
            else None
        ),
    }), 200


@ward_bp.post(
    "/reservations/<int:reservation_id>/cancel"
)
@role_required(*CLINICAL_ROLES)
def cancel_bed_reservation_route(
    reservation_id: int,
):
    payload = BedReservationCancelSchema.model_validate(
        request.get_json() or {}
    )

    reservation = cancel_bed_reservation(
        reservation_id=reservation_id,
        reason=payload.reason,
    )

    return jsonify({
        "message": "Bed reservation cancelled successfully",
        "data": _serialize_reservation(reservation),
    }), 200


@ward_bp.post(
    "/reservations/<int:reservation_id>/admit"
)
@role_required(*CLINICAL_ROLES)
def admit_patient_from_reservation_route(
    reservation_id: int,
):
    payload = AdmissionFromReservationSchema.model_validate(
        request.get_json() or {}
    )

    admission = admit_patient_from_reservation(
        reservation_id=reservation_id,
        admitted_by_id=payload.admitted_by_id,
        reason=payload.reason,
    )

    return jsonify({
        "message": "Patient admitted from reservation successfully",
        "data": _serialize_admission(admission),
    }), 201


# ---------------------------------------------------------------------------
# ADMISSIONS
# ---------------------------------------------------------------------------

@ward_bp.post("/admissions")
@role_required(*CLINICAL_ROLES)
def admit_patient_route():
    payload = AdmissionCreateSchema.model_validate(
        request.get_json() or {}
    )

    admission = admit_patient(
        patient_id=payload.patient_id,
        bed_id=payload.bed_id,
        admitted_by_id=payload.admitted_by_id,
        reason=payload.reason,
    )

    return jsonify({
        "message": "Patient admitted successfully",
        "data": _serialize_admission(admission),
    }), 201


@ward_bp.get("/admissions/<int:admission_id>")
@role_required(*VIEW_ROLES)
def get_admission_route(admission_id: int):
    admission = get_admission(admission_id)

    return jsonify({
        "data": _serialize_admission(admission),
    }), 200


@ward_bp.get(
    "/patients/<int:patient_id>/admissions"
)
@role_required(*VIEW_ROLES)
def list_patient_admissions_route(
    patient_id: int,
):
    admissions = list_admissions_for_patient(
        patient_id,
    )

    return jsonify({
        "data": [
            _serialize_admission(admission)
            for admission in admissions
        ],
    }), 200


@ward_bp.post(
    "/admissions/<int:admission_id>/transfer"
)
@role_required(*CLINICAL_ROLES)
def transfer_admission_route(
    admission_id: int,
):
    payload = AdmissionTransferSchema.model_validate(
        request.get_json() or {}
    )

    transfer = transfer_bed(
        admission_id=admission_id,
        to_bed_id=payload.to_bed_id,
        reason=payload.reason,
    )

    return jsonify({
        "message": "Patient transferred successfully",
        "data": _serialize_transfer(transfer),
    }), 200


@ward_bp.post(
    "/admissions/<int:admission_id>/discharge"
)
@role_required(*CLINICAL_ROLES)
def discharge_patient_route(
    admission_id: int,
):
    payload = AdmissionDischargeSchema.model_validate(
        request.get_json() or {}
    )

    admission = discharge_patient(
        admission_id=admission_id,
        reason=payload.reason,
    )

    return jsonify({
        "message": "Patient discharged successfully",
        "data": _serialize_admission(admission),
    }), 200