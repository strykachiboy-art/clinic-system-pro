from datetime import timedelta

import pytest

from app.core.enums.ward_enums import (
    AdmissionStatus,
    BedStatus,
    ReservationStatus,
    WardType,
)
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.ward.services import ward_service as svc


def _future(minutes=30):
    from app.modules.ward.services.ward_service import _utcnow
    return _utcnow() + timedelta(minutes=minutes)


class TestWards:
    def test_create_ward_happy_path(self, db, clinic):
        ward = svc.create_ward(clinic_id=clinic.id, name="ICU-1", ward_type=WardType.ICU, capacity=5)
        assert ward.id is not None
        assert ward.ward_type == WardType.ICU

    def test_create_ward_requires_active_clinic(self, db, suspended_clinic):
        with pytest.raises(Exception):
            svc.create_ward(clinic_id=suspended_clinic.id, name="X")

    def test_create_ward_rejects_duplicate_name(self, db, clinic):
        svc.create_ward(clinic_id=clinic.id, name="Same")
        with pytest.raises(ConflictError):
            svc.create_ward(clinic_id=clinic.id, name="Same")

    def test_create_ward_rejects_negative_capacity(self, db, clinic):
        with pytest.raises(ValidationError):
            svc.create_ward(clinic_id=clinic.id, name="X", capacity=-1)

    def test_update_ward_capacity_cannot_go_below_bed_count(self, db, clinic, make_ward, make_bed):
        ward = make_ward(clinic, capacity=3)
        make_bed(ward)
        make_bed(ward)

        with pytest.raises(ValidationError):
            svc.update_ward(ward.id, capacity=1)

    def test_get_ward_occupancy(self, db, clinic, make_ward, make_bed):
        ward = make_ward(clinic, capacity=4)
        make_bed(ward, status=BedStatus.OCCUPIED)
        make_bed(ward, status=BedStatus.AVAILABLE)
        make_bed(ward, status=BedStatus.RESERVED)

        occ = svc.get_ward_occupancy(ward.id)
        assert occ["total_beds"] == 3
        assert occ["occupied"] == 1
        assert occ["available"] == 1
        assert occ["reserved"] == 1
        assert occ["occupancy_rate"] == round(1 / 3 * 100, 2)


class TestBeds:
    def test_add_bed_happy_path(self, db, clinic, make_ward):
        ward = make_ward(clinic, capacity=2)
        bed = svc.add_bed(ward.id, "A1")
        assert bed.status == BedStatus.AVAILABLE

    def test_add_bed_rejects_over_capacity(self, db, clinic, make_ward, make_bed):
        ward = make_ward(clinic, capacity=1)
        make_bed(ward)

        with pytest.raises(ConflictError):
            svc.add_bed(ward.id, "extra")

    def test_add_bed_rejects_duplicate_number(self, db, clinic, make_ward):
        ward = make_ward(clinic, capacity=5)
        svc.add_bed(ward.id, "A1")

        with pytest.raises(ConflictError):
            svc.add_bed(ward.id, "A1")

    def test_set_bed_maintenance_toggle(self, db, clinic, make_ward, make_bed):
        ward = make_ward(clinic)
        bed = make_bed(ward)

        svc.set_bed_maintenance(bed.id, True)
        assert svc.get_bed(bed.id).status == BedStatus.MAINTENANCE

        svc.set_bed_maintenance(bed.id, False)
        assert svc.get_bed(bed.id).status == BedStatus.AVAILABLE

    def test_set_bed_maintenance_rejects_when_occupied(self, db, clinic, make_ward, make_bed):
        ward = make_ward(clinic)
        bed = make_bed(ward, status=BedStatus.OCCUPIED)

        with pytest.raises(ConflictError):
            svc.set_bed_maintenance(bed.id, True)


class TestReservations:
    def test_reserve_bed_happy_path(self, db, clinic, make_ward, make_bed, make_patient, make_staff):
        ward = make_ward(clinic)
        bed = make_bed(ward)
        patient = make_patient(clinic)
        staff = make_staff(clinic)

        reservation = svc.reserve_bed(
            patient_id=patient.id, bed_id=bed.id, reserved_by_id=staff.id
        )

        assert reservation.status == ReservationStatus.PENDING
        assert svc.get_bed(bed.id).status == BedStatus.RESERVED

    def test_reserve_bed_rejects_when_patient_already_admitted(
        self, db, clinic, make_ward, make_bed, make_patient, make_staff
    ):
        ward = make_ward(clinic)
        bed1 = make_bed(ward)
        bed2 = make_bed(ward)
        patient = make_patient(clinic)
        staff = make_staff(clinic)

        svc.admit_patient(patient_id=patient.id, bed_id=bed1.id, admitted_by_id=staff.id)

        with pytest.raises(ConflictError):
            svc.reserve_bed(patient_id=patient.id, bed_id=bed2.id, reserved_by_id=staff.id)

    def test_reserve_bed_rejects_non_available_bed(self, db, clinic, make_ward, make_bed, make_patient, make_staff):
        ward = make_ward(clinic)
        bed = make_bed(ward, status=BedStatus.MAINTENANCE)
        patient = make_patient(clinic)
        staff = make_staff(clinic)

        with pytest.raises(ConflictError):
            svc.reserve_bed(patient_id=patient.id, bed_id=bed.id, reserved_by_id=staff.id)

    def test_reserve_bed_rejects_past_expiry(self, db, clinic, make_ward, make_bed, make_patient, make_staff):
        ward = make_ward(clinic)
        bed = make_bed(ward)
        patient = make_patient(clinic)
        staff = make_staff(clinic)

        from app.modules.ward.services.ward_service import _utcnow
        with pytest.raises(ValidationError):
            svc.reserve_bed(
                patient_id=patient.id, bed_id=bed.id, reserved_by_id=staff.id,
                expires_at=_utcnow() - timedelta(minutes=1),
            )

    def test_cancel_bed_reservation_releases_bed(self, db, clinic, make_ward, make_bed, make_patient, make_staff):
        ward = make_ward(clinic)
        bed = make_bed(ward)
        patient = make_patient(clinic)
        staff = make_staff(clinic)

        reservation = svc.reserve_bed(patient_id=patient.id, bed_id=bed.id, reserved_by_id=staff.id)
        cancelled = svc.cancel_bed_reservation(reservation.id, reason="Changed mind")

        assert cancelled.status == ReservationStatus.CANCELLED
        assert svc.get_bed(bed.id).status == BedStatus.AVAILABLE

    def test_expire_bed_reservation_requires_expiry_time(
        self, db, clinic, make_ward, make_bed, make_patient, make_staff
    ):
        ward = make_ward(clinic)
        bed = make_bed(ward)
        patient = make_patient(clinic)
        staff = make_staff(clinic)

        reservation = svc.reserve_bed(patient_id=patient.id, bed_id=bed.id, reserved_by_id=staff.id)

        with pytest.raises(ValidationError):
            svc.expire_bed_reservation(reservation.id)

    def test_expire_bed_reservation_rejects_not_yet_expired(
        self, db, clinic, make_ward, make_bed, make_patient, make_staff
    ):
        ward = make_ward(clinic)
        bed = make_bed(ward)
        patient = make_patient(clinic)
        staff = make_staff(clinic)

        reservation = svc.reserve_bed(
            patient_id=patient.id, bed_id=bed.id, reserved_by_id=staff.id,
            expires_at=_future(60),
        )

        with pytest.raises(ConflictError):
            svc.expire_bed_reservation(reservation.id)

    def test_expire_due_bed_reservations_batch(self, db, clinic, make_ward, make_bed, make_patient, make_staff):
        ward = make_ward(clinic)
        bed = make_bed(ward)
        patient = make_patient(clinic)
        staff = make_staff(clinic)

        reservation = svc.reserve_bed(
            patient_id=patient.id, bed_id=bed.id, reserved_by_id=staff.id,
            expires_at=_future(1),
        )
        # Simulate time having passed: push both reserved_at and
        # expires_at back together, since the DB enforces
        # expires_at > reserved_at at all times (ck_bed_reservations_valid_expiry).
        reservation.reserved_at = reservation.reserved_at - timedelta(hours=2)
        reservation.expires_at = reservation.expires_at - timedelta(hours=1)
        db.session.commit()

        expired = svc.expire_due_bed_reservations(clinic_id=clinic.id)

        assert len(expired) == 1
        assert svc.get_bed(bed.id).status == BedStatus.AVAILABLE


class TestAdmissions:
    def test_admit_patient_happy_path(self, db, clinic, make_ward, make_bed, make_patient, make_staff):
        ward = make_ward(clinic)
        bed = make_bed(ward)
        patient = make_patient(clinic)
        staff = make_staff(clinic)

        admission = svc.admit_patient(patient_id=patient.id, bed_id=bed.id, admitted_by_id=staff.id)

        assert admission.status == AdmissionStatus.ADMITTED
        assert svc.get_bed(bed.id).status == BedStatus.OCCUPIED

    def test_admit_patient_rejects_when_reservation_active(
        self, db, clinic, make_ward, make_bed, make_patient, make_staff
    ):
        ward = make_ward(clinic)
        bed1 = make_bed(ward)
        bed2 = make_bed(ward)
        patient = make_patient(clinic)
        staff = make_staff(clinic)

        svc.reserve_bed(patient_id=patient.id, bed_id=bed1.id, reserved_by_id=staff.id)

        with pytest.raises(ConflictError):
            svc.admit_patient(patient_id=patient.id, bed_id=bed2.id, admitted_by_id=staff.id)

    def test_admit_patient_from_reservation_happy_path(
        self, db, clinic, make_ward, make_bed, make_patient, make_staff
    ):
        ward = make_ward(clinic)
        bed = make_bed(ward)
        patient = make_patient(clinic)
        staff = make_staff(clinic)

        reservation = svc.reserve_bed(patient_id=patient.id, bed_id=bed.id, reserved_by_id=staff.id)
        admission = svc.admit_patient_from_reservation(reservation_id=reservation.id, admitted_by_id=staff.id)

        assert admission.status == AdmissionStatus.ADMITTED
        assert svc.get_bed_reservation(reservation.id).status == ReservationStatus.FULFILLED
        assert svc.get_bed(bed.id).status == BedStatus.OCCUPIED

    def test_transfer_bed_happy_path(self, db, clinic, make_ward, make_bed, make_patient, make_staff):
        ward = make_ward(clinic)
        bed1 = make_bed(ward)
        bed2 = make_bed(ward)
        patient = make_patient(clinic)
        staff = make_staff(clinic)

        admission = svc.admit_patient(patient_id=patient.id, bed_id=bed1.id, admitted_by_id=staff.id)
        transfer = svc.transfer_bed(admission_id=admission.id, to_bed_id=bed2.id)

        assert svc.get_bed(bed1.id).status == BedStatus.AVAILABLE
        assert svc.get_bed(bed2.id).status == BedStatus.OCCUPIED
        assert svc.get_admission(admission.id).bed_id == bed2.id

    def test_transfer_bed_rejects_same_bed(self, db, clinic, make_ward, make_bed, make_patient, make_staff):
        ward = make_ward(clinic)
        bed = make_bed(ward)
        patient = make_patient(clinic)
        staff = make_staff(clinic)

        admission = svc.admit_patient(patient_id=patient.id, bed_id=bed.id, admitted_by_id=staff.id)

        with pytest.raises(ValidationError):
            svc.transfer_bed(admission_id=admission.id, to_bed_id=bed.id)

    def test_transfer_bed_rejects_occupied_destination(
        self, db, clinic, make_ward, make_bed, make_patient, make_staff
    ):
        ward = make_ward(clinic)
        bed1 = make_bed(ward)
        bed2 = make_bed(ward, status=BedStatus.OCCUPIED)
        patient = make_patient(clinic)
        staff = make_staff(clinic)

        admission = svc.admit_patient(patient_id=patient.id, bed_id=bed1.id, admitted_by_id=staff.id)

        with pytest.raises(ConflictError):
            svc.transfer_bed(admission_id=admission.id, to_bed_id=bed2.id)


class TestDischarge:
    def test_discharge_patient_happy_path(self, db, clinic, make_ward, make_bed, make_patient, make_staff):
        ward = make_ward(clinic)
        bed = make_bed(ward)
        patient = make_patient(clinic)
        staff = make_staff(clinic)

        admission = svc.admit_patient(patient_id=patient.id, bed_id=bed.id, admitted_by_id=staff.id)
        discharged = svc.discharge_patient(admission_id=admission.id, reason="Recovered")

        assert discharged.status == AdmissionStatus.DISCHARGED
        assert svc.get_bed(bed.id).status == BedStatus.AVAILABLE

    def test_discharge_patient_rejects_already_discharged(
        self, db, clinic, make_ward, make_bed, make_patient, make_staff
    ):
        ward = make_ward(clinic)
        bed = make_bed(ward)
        patient = make_patient(clinic)
        staff = make_staff(clinic)

        admission = svc.admit_patient(patient_id=patient.id, bed_id=bed.id, admitted_by_id=staff.id)
        svc.discharge_patient(admission_id=admission.id)

        with pytest.raises(ConflictError):
            svc.discharge_patient(admission_id=admission.id)