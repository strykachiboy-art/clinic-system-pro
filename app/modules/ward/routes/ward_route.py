from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError as PydanticValidationError

from app.core.auth.user.models.user_model import User
from app.core.enums.role_enums import Role
from app.core.enums.ward_enums import (
    BedStatus,
    ReservationStatus,
    WardType,
)
from app.core.exceptions import (
    DomainError,
    ValidationError,
)
from app.core.utils.decorators import role_required

from app.modules.ward.schemas.admission_schema import (
    AdmissionCreateSchema,
    AdmissionDischargeSchema,
    AdmissionFromReservationSchema,
    AdmissionTransferSchema,
)
from app.modules.ward.schemas.reservation_schema import (
    BedReservationCancelSchema,
    BedReservationCreateSchema,
    BedReservationResponseSchema,
)
from app.modules.ward.schemas.bed_schema import (
    BedCreateSchema,
    BedMaintenanceSchema,
)
from app.modules.ward.schemas.ward_schema import (
    WardCreateSchema,
    WardOccupancyResponseSchema,
)

from app.modules.ward.services.ward_service import (
    add_bed,
    admit_patient,
    admit_patient_from_reservation,
    cancel_bed_reservation,
    create_ward,
    discharge_patient,
    get_active_bed_reservation_for_bed,
    get_active_bed_reservation_for_patient,
    get_active_admission_for_patient,
    get_admission,
    get_bed,
    get_bed_reservation,
    get_ward,
    get_ward_occupancy,
    list_admissions_for_patient,
    list_bed_reservations,
    list_beds,
    list_wards,
    reserve_bed,
    set_bed_maintenance,
    transfer_bed,
)


ward_bp = Blueprint(
    "ward",
    __name__,
    url_prefix="/api/wards",
)


# ============================================================================
# ROLES
# ============================================================================


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


# ============================================================================
# AUTH HELPERS
# ============================================================================


def _current_user() -> User:
    user_id = getattr(
        g,
        "current_user_id",
        None,
    )

    if user_id is None:
        raise ValidationError(
            "Authenticated user is required"
        )

    user = User.query.get(user_id)

    if user is None:
        raise ValidationError(
            "Authenticated user no longer exists"
        )

    if not user.is_active:
        raise ValidationError(
            "Authenticated user is inactive"
        )

    return user


def _current_clinic_id() -> int:
    user = _current_user()

    if user.clinic_id is None:
        raise ValidationError(
            "Authenticated user is not assigned to a clinic"
        )

    return user.clinic_id


def _serialize_model(schema, value):
    if value is None:
        return None

    return schema.model_validate(value).model_dump(
        mode="json"
    )


def _domain_error_response(exc: DomainError):
    return jsonify(
        {
            "error": str(exc),
        }
    ), exc.status_code


def _validation_error_response(exc):
    return jsonify(
        {
            "error": "Validation failed",
            "details": exc.errors(),
        }
    ), 422


# ============================================================================
# WARDS
# ============================================================================


@ward_bp.route("", methods=["POST"])
@role_required(*MANAGEMENT_ROLES)
def create_ward_route():
    try:
        user = _current_user()
        clinic_id = _current_clinic_id()

        payload = WardCreateSchema.model_validate(
            request.get_json(
                silent=True
            ) or {}
        )

        ward = create_ward(
            clinic_id=clinic_id,
            name=payload.name,
            ward_type=payload.ward_type,
            capacity=payload.capacity,
            actor_user_id=user.id,
        )

        return jsonify(
            {
                "message": "Ward created successfully",
                "ward": _serialize_model(
                    WardCreateSchema,
                    ward,
                ),
            }
        ), 201

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except DomainError as exc:
        return _domain_error_response(exc)


@ward_bp.route("", methods=["GET"])
@role_required(*VIEW_ROLES)
def list_wards_route():
    try:
        clinic_id = _current_clinic_id()

        ward_type = request.args.get(
            "ward_type"
        )

        if ward_type is not None:
            try:
                ward_type = WardType(
                    ward_type
                )
            except ValueError:
                raise ValidationError(
                    f"Invalid ward type: {ward_type}"
                )

        wards = list_wards(
            clinic_id=clinic_id,
            ward_type=ward_type,
        )

        return jsonify(
            [
                _serialize_model(
                    WardCreateSchema,
                    ward,
                )
                for ward in wards
            ]
        ), 200

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except DomainError as exc:
        return _domain_error_response(exc)


@ward_bp.route("/<int:ward_id>", methods=["GET"])
@role_required(*VIEW_ROLES)
def get_ward_route(ward_id):
    try:
        clinic_id = _current_clinic_id()

        ward = get_ward(
            ward_id,
            clinic_id=clinic_id,
        )

        return jsonify(
            _serialize_model(
                WardCreateSchema,
                ward,
            )
        ), 200

    except DomainError as exc:
        return _domain_error_response(exc)


@ward_bp.route(
    "/<int:ward_id>/occupancy",
    methods=["GET"],
)
@role_required(*VIEW_ROLES)
def get_ward_occupancy_route(ward_id):
    try:
        clinic_id = _current_clinic_id()

        occupancy = get_ward_occupancy(
            ward_id=ward_id,
            clinic_id=clinic_id,
        )

        return jsonify(
            WardOccupancyResponseSchema.model_validate(
                occupancy
            ).model_dump(
                mode="json"
            )
        ), 200

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except DomainError as exc:
        return _domain_error_response(exc)


# ============================================================================
# BEDS
# ============================================================================


@ward_bp.route(
    "/<int:ward_id>/beds",
    methods=["POST"],
)
@role_required(*MANAGEMENT_ROLES)
def add_bed_route(ward_id):
    try:
        user = _current_user()
        clinic_id = _current_clinic_id()

        payload = BedCreateSchema.model_validate(
            request.get_json(
                silent=True
            ) or {}
        )

        bed = add_bed(
            ward_id=ward_id,
            bed_number=payload.bed_number,
            clinic_id=clinic_id,
            actor_user_id=user.id,
        )

        return jsonify(
            {
                "message": "Bed added successfully",
                "bed": {
                    "id": bed.id,
                    "ward_id": bed.ward_id,
                    "bed_number": bed.bed_number,
                    "status": bed.status.value,
                },
            }
        ), 201

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except DomainError as exc:
        return _domain_error_response(exc)


@ward_bp.route(
    "/<int:ward_id>/beds",
    methods=["GET"],
)
@role_required(*VIEW_ROLES)
def list_beds_route(ward_id):
    try:
        clinic_id = _current_clinic_id()

        status = request.args.get(
            "status"
        )

        if status is not None:
            try:
                status = BedStatus(
                    status
                )
            except ValueError:
                raise ValidationError(
                    f"Invalid bed status: {status}"
                )

        beds = list_beds(
            ward_id=ward_id,
            clinic_id=clinic_id,
            status=status,
        )

        return jsonify(
            [
                {
                    "id": bed.id,
                    "ward_id": bed.ward_id,
                    "bed_number": bed.bed_number,
                    "status": bed.status.value,
                }
                for bed in beds
            ]
        ), 200

    except DomainError as exc:
        return _domain_error_response(exc)


@ward_bp.route(
    "/beds/<int:bed_id>",
    methods=["GET"],
)
@role_required(*VIEW_ROLES)
def get_bed_route(bed_id):
    try:
        clinic_id = _current_clinic_id()

        bed = get_bed(
            bed_id,
            clinic_id=clinic_id,
        )

        return jsonify(
            {
                "id": bed.id,
                "ward_id": bed.ward_id,
                "bed_number": bed.bed_number,
                "status": bed.status.value,
            }
        ), 200

    except DomainError as exc:
        return _domain_error_response(exc)


@ward_bp.route(
    "/beds/<int:bed_id>/maintenance",
    methods=["PATCH"],
)
@role_required(*MANAGEMENT_ROLES)
def set_bed_maintenance_route(bed_id):
    try:
        user = _current_user()
        clinic_id = _current_clinic_id()

        payload = BedMaintenanceSchema.model_validate(
            request.get_json(
                silent=True
            ) or {}
        )

        bed = set_bed_maintenance(
            bed_id=bed_id,
            under_maintenance=payload.under_maintenance,
            clinic_id=clinic_id,
            actor_user_id=user.id,
        )

        return jsonify(
            {
                "message": (
                    "Bed maintenance status updated"
                ),
                "bed": {
                    "id": bed.id,
                    "ward_id": bed.ward_id,
                    "bed_number": bed.bed_number,
                    "status": bed.status.value,
                },
            }
        ), 200

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except DomainError as exc:
        return _domain_error_response(exc)


# ============================================================================
# RESERVATIONS
# ============================================================================


@ward_bp.route(
    "/reservations",
    methods=["POST"],
)
@role_required(*CLINICAL_ROLES)
def reserve_bed_route():
    try:
        user = _current_user()
        clinic_id = _current_clinic_id()

        payload = BedReservationCreateSchema.model_validate(
            request.get_json(
                silent=True
            ) or {}
        )

        reservation = reserve_bed(
            patient_id=payload.patient_id,
            bed_id=payload.bed_id,
            reserved_by_id=user.staff.id,
            clinic_id=clinic_id,
            reason=payload.reason,
            expires_at=payload.expires_at,
            actor_user_id=user.id,
        )

        return jsonify(
            {
                "message": "Bed reserved successfully",
                "reservation": _serialize_model(
                    BedReservationResponseSchema,
                    reservation,
                ),
            }
        ), 201

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except DomainError as exc:
        return _domain_error_response(exc)


@ward_bp.route(
    "/reservations",
    methods=["GET"],
)
@role_required(*VIEW_ROLES)
def list_bed_reservations_route():
    try:
        clinic_id = _current_clinic_id()

        status = request.args.get(
            "status"
        )

        if status is not None:
            try:
                status = ReservationStatus(
                    status
                )
            except ValueError:
                raise ValidationError(
                    f"Invalid reservation status: {status}"
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
            status=status,
            patient_id=patient_id,
            bed_id=bed_id,
        )

        return jsonify(
            [
                _serialize_model(
                    BedReservationResponseSchema,
                    reservation,
                )
                for reservation in reservations
            ]
        ), 200

    except DomainError as exc:
        return _domain_error_response(exc)


@ward_bp.route(
    "/reservations/<int:reservation_id>",
    methods=["GET"],
)
@role_required(*VIEW_ROLES)
def get_bed_reservation_route(
    reservation_id,
):
    try:
        clinic_id = _current_clinic_id()

        reservation = get_bed_reservation(
            reservation_id,
            clinic_id=clinic_id,
        )

        return jsonify(
            _serialize_model(
                BedReservationResponseSchema,
                reservation,
            )
        ), 200

    except DomainError as exc:
        return _domain_error_response(exc)


@ward_bp.route(
    "/patients/<int:patient_id>/reservation",
    methods=["GET"],
)
@role_required(*VIEW_ROLES)
def get_patient_active_reservation_route(
    patient_id,
):
    try:
        clinic_id = _current_clinic_id()

        reservation = (
            get_active_bed_reservation_for_patient(
                patient_id=patient_id,
                clinic_id=clinic_id,
            )
        )

        if reservation is None:
            return jsonify(
                {
                    "message": "No active reservation found",
                }
            ), 404

        return jsonify(
            _serialize_model(
                BedReservationResponseSchema,
                reservation,
            )
        ), 200

    except DomainError as exc:
        return _domain_error_response(exc)


@ward_bp.route(
    "/beds/<int:bed_id>/reservation",
    methods=["GET"],
)
@role_required(*VIEW_ROLES)
def get_bed_active_reservation_route(
    bed_id,
):
    try:
        clinic_id = _current_clinic_id()

        reservation = (
            get_active_bed_reservation_for_bed(
                bed_id=bed_id,
                clinic_id=clinic_id,
            )
        )

        if reservation is None:
            return jsonify(
                {
                    "message": "No active reservation found",
                }
            ), 404

        return jsonify(
            _serialize_model(
                BedReservationResponseSchema,
                reservation,
            )
        ), 200

    except DomainError as exc:
        return _domain_error_response(exc)


@ward_bp.route(
    "/reservations/<int:reservation_id>/cancel",
    methods=["POST"],
)
@role_required(*CLINICAL_ROLES)
def cancel_bed_reservation_route(
    reservation_id,
):
    try:
        user = _current_user()
        clinic_id = _current_clinic_id()

        payload = BedReservationCancelSchema.model_validate(
            request.get_json(
                silent=True
            ) or {}
        )

        reservation = cancel_bed_reservation(
            reservation_id=reservation_id,
            clinic_id=clinic_id,
            reason=payload.reason,
            actor_user_id=user.id,
        )

        return jsonify(
            {
                "message": (
                    "Bed reservation cancelled successfully"
                ),
                "reservation": _serialize_model(
                    BedReservationResponseSchema,
                    reservation,
                ),
            }
        ), 200

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except DomainError as exc:
        return _domain_error_response(exc)


# ============================================================================
# ADMISSIONS
# ============================================================================


@ward_bp.route(
    "/reservations/<int:reservation_id>/admit",
    methods=["POST"],
)
@role_required(*CLINICAL_ROLES)
def admit_patient_from_reservation_route(
    reservation_id,
):
    try:
        user = _current_user()
        clinic_id = _current_clinic_id()

        payload = AdmissionFromReservationSchema.model_validate(
            request.get_json(
                silent=True
            ) or {}
        )

        if user.staff is None:
            raise ValidationError(
                "Authenticated user is not linked to a staff record"
            )

        admission = admit_patient_from_reservation(
            reservation_id=reservation_id,
            admitted_by_id=user.staff.id,
            clinic_id=clinic_id,
            reason=payload.reason,
            actor_user_id=user.id,
        )

        return jsonify(
            {
                "message": (
                    "Patient admitted from reservation"
                ),
                "admission": {
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
                },
            }
        ), 201

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except DomainError as exc:
        return _domain_error_response(exc)


@ward_bp.route(
    "/admissions",
    methods=["POST"],
)
@role_required(*CLINICAL_ROLES)
def admit_patient_route():
    try:
        user = _current_user()
        clinic_id = _current_clinic_id()

        payload = AdmissionCreateSchema.model_validate(
            request.get_json(
                silent=True
            ) or {}
        )

        if user.staff is None:
            raise ValidationError(
                "Authenticated user is not linked to a staff record"
            )

        admission = admit_patient(
            patient_id=payload.patient_id,
            bed_id=payload.bed_id,
            admitted_by_id=user.staff.id,
            clinic_id=clinic_id,
            reason=payload.reason,
            actor_user_id=user.id,
        )

        return jsonify(
            {
                "message": "Patient admitted successfully",
                "admission": {
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
                },
            }
        ), 201

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except DomainError as exc:
        return _domain_error_response(exc)


@ward_bp.route(
    "/admissions/<int:admission_id>",
    methods=["GET"],
)
@role_required(*VIEW_ROLES)
def get_admission_route(admission_id):
    try:
        clinic_id = _current_clinic_id()

        admission = get_admission(
            admission_id,
            clinic_id=clinic_id,
        )

        return jsonify(
            {
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
            }
        ), 200

    except DomainError as exc:
        return _domain_error_response(exc)


@ward_bp.route(
    "/patients/<int:patient_id>/admissions",
    methods=["GET"],
)
@role_required(*VIEW_ROLES)
def list_patient_admissions_route(
    patient_id,
):
    try:
        clinic_id = _current_clinic_id()

        admissions = list_admissions_for_patient(
            patient_id=patient_id,
            clinic_id=clinic_id,
        )

        return jsonify(
            [
                {
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
                }
                for admission in admissions
            ]
        ), 200

    except DomainError as exc:
        return _domain_error_response(exc)


@ward_bp.route(
    "/admissions/<int:admission_id>/transfer",
    methods=["POST"],
)
@role_required(*CLINICAL_ROLES)
def transfer_bed_route(admission_id):
    try:
        user = _current_user()
        clinic_id = _current_clinic_id()

        payload = AdmissionTransferSchema.model_validate(
            request.get_json(
                silent=True
            ) or {}
        )

        transfer = transfer_bed(
            admission_id=admission_id,
            to_bed_id=payload.to_bed_id,
            clinic_id=clinic_id,
            reason=payload.reason,
            actor_user_id=user.id,
        )

        return jsonify(
            {
                "message": "Patient transferred successfully",
                "transfer": {
                    "id": transfer.id,
                    "admission_id": transfer.admission_id,
                    "from_bed_id": transfer.from_bed_id,
                    "to_bed_id": transfer.to_bed_id,
                    "reason": transfer.reason,
                    "transferred_at": (
                        transfer.transferred_at.isoformat()
                        if transfer.transferred_at
                        else None
                    ),
                },
            }
        ), 201

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except DomainError as exc:
        return _domain_error_response(exc)


@ward_bp.route(
    "/admissions/<int:admission_id>/discharge",
    methods=["POST"],
)
@role_required(*CLINICAL_ROLES)
def discharge_patient_route(admission_id):
    try:
        user = _current_user()
        clinic_id = _current_clinic_id()

        payload = AdmissionDischargeSchema.model_validate(
            request.get_json(
                silent=True
            ) or {}
        )

        admission = discharge_patient(
            admission_id=admission_id,
            clinic_id=clinic_id,
            reason=payload.reason,
            actor_user_id=user.id,
        )

        return jsonify(
            {
                "message": "Patient discharged successfully",
                "admission": {
                    "id": admission.id,
                    "patient_id": admission.patient_id,
                    "bed_id": admission.bed_id,
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
                },
            }
        ), 200

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except DomainError as exc:
        return _domain_error_response(exc)