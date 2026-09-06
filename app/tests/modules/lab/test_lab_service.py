from decimal import Decimal

import pytest

from app.core.enums.lab_enums import LabOrderStatus, LabResultFlag, SampleType
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.lab.services import lab_service as svc


class TestLabTestCatalog:
    def test_create_lab_test_happy_path(self, db):
        test = svc.create_lab_test(name="CBC", code="CBC1", sample_type=SampleType.BLOOD)
        assert test.id is not None
        assert test.is_active is True

    def test_create_lab_test_rejects_blank_name(self, db):
        with pytest.raises(ValidationError):
            svc.create_lab_test(name="   ")

    def test_create_lab_test_rejects_unknown_field(self, db):
        with pytest.raises(ValidationError):
            svc.create_lab_test(name="X", made_up_field=1)

    def test_create_lab_test_rejects_duplicate_code(self, db):
        svc.create_lab_test(name="A", code="DUP")
        with pytest.raises(ConflictError):
            svc.create_lab_test(name="B", code="DUP")

    def test_create_lab_test_rejects_invalid_critical_range(self, db):
        with pytest.raises(ValidationError):
            svc.create_lab_test(name="X", critical_low=Decimal("10"), critical_high=Decimal("5"))

    def test_get_lab_test_not_found(self, db):
        with pytest.raises(NotFoundError):
            svc.get_lab_test(999999)

    def test_list_lab_tests_global_vs_clinic_scoped(self, db, clinic, make_lab_test):
        make_lab_test(None, name="Global")
        make_lab_test(clinic, name="ClinicOnly")

        global_only = svc.list_lab_tests(clinic_id=None)
        assert {t.name for t in global_only} == {"Global"}

        scoped = svc.list_lab_tests(clinic_id=clinic.id)
        assert {t.name for t in scoped} == {"Global", "ClinicOnly"}

    def test_list_lab_tests_excludes_inactive_by_default(self, db, make_lab_test):
        make_lab_test(None, name="Active")
        make_lab_test(None, name="Inactive", is_active=False)

        assert {t.name for t in svc.list_lab_tests()} == {"Active"}
        assert {t.name for t in svc.list_lab_tests(active_only=False)} == {"Active", "Inactive"}

    def test_update_lab_test_rejects_unknown_field(self, db, make_lab_test):
        test = make_lab_test(None)
        with pytest.raises(ValidationError):
            svc.update_lab_test(test.id, bogus=1)

    def test_update_lab_test_rejects_duplicate_code(self, db, make_lab_test):
        make_lab_test(None, code="AAA")
        b = make_lab_test(None, code="BBB")

        with pytest.raises(ConflictError):
            svc.update_lab_test(b.id, code="AAA")

    def test_update_lab_test_happy_path(self, db, make_lab_test):
        test = make_lab_test(None, name="Old")
        updated = svc.update_lab_test(test.id, name="New")
        assert updated.name == "New"


class TestLabOrderCreation:
    def test_create_lab_order_happy_path(self, db, clinic, make_patient, make_staff, make_lab_test):
        doctor = make_staff(clinic, role=Role.DOCTOR)
        patient = make_patient(clinic)
        test = make_lab_test(clinic)

        order = svc.create_lab_order(
            clinic_id=clinic.id, patient_id=patient.id, ordered_by_id=doctor.id, test_ids=[test.id],
        )

        assert order.status == LabOrderStatus.ORDERED
        assert order.qr_code is not None
        assert len(order.items) == 1

    def test_create_lab_order_requires_active_clinic(self, db, suspended_clinic):
        with pytest.raises(Exception):
            svc.create_lab_order(
                clinic_id=suspended_clinic.id, patient_id=1, ordered_by_id=1, test_ids=[1],
            )

    def test_create_lab_order_rejects_empty_tests(self, db, clinic, make_patient, make_staff):
        doctor = make_staff(clinic, role=Role.DOCTOR)
        patient = make_patient(clinic)

        with pytest.raises(ValidationError):
            svc.create_lab_order(
                clinic_id=clinic.id, patient_id=patient.id, ordered_by_id=doctor.id, test_ids=[],
            )

    def test_create_lab_order_rejects_duplicate_test_ids(self, db, clinic, make_patient, make_staff, make_lab_test):
        doctor = make_staff(clinic, role=Role.DOCTOR)
        patient = make_patient(clinic)
        test = make_lab_test(clinic)

        with pytest.raises(ValidationError):
            svc.create_lab_order(
                clinic_id=clinic.id, patient_id=patient.id, ordered_by_id=doctor.id,
                test_ids=[test.id, test.id],
            )

    def test_create_lab_order_rejects_patient_from_other_clinic(
        self, db, clinic, make_clinic, make_patient, make_staff, make_lab_test
    ):
        doctor = make_staff(clinic, role=Role.DOCTOR)
        other_clinic = make_clinic(name="Other")
        patient = make_patient(other_clinic)
        test = make_lab_test(clinic)

        with pytest.raises(ValidationError):
            svc.create_lab_order(
                clinic_id=clinic.id, patient_id=patient.id, ordered_by_id=doctor.id, test_ids=[test.id],
            )

    def test_create_lab_order_rejects_inactive_ordering_staff(self, db, clinic, make_patient, make_staff, make_lab_test):
        doctor = make_staff(clinic, role=Role.DOCTOR, status=StaffStatus.SUSPENDED)
        patient = make_patient(clinic)
        test = make_lab_test(clinic)

        with pytest.raises(ValidationError):
            svc.create_lab_order(
                clinic_id=clinic.id, patient_id=patient.id, ordered_by_id=doctor.id, test_ids=[test.id],
            )

    def test_create_lab_order_rejects_missing_test_id(self, db, clinic, make_patient, make_staff):
        doctor = make_staff(clinic, role=Role.DOCTOR)
        patient = make_patient(clinic)

        with pytest.raises(NotFoundError):
            svc.create_lab_order(
                clinic_id=clinic.id, patient_id=patient.id, ordered_by_id=doctor.id, test_ids=[999999],
            )

    def test_create_lab_order_rejects_test_from_other_clinic(
        self, db, clinic, make_clinic, make_patient, make_staff, make_lab_test
    ):
        doctor = make_staff(clinic, role=Role.DOCTOR)
        patient = make_patient(clinic)
        other_clinic = make_clinic(name="Other")
        test = make_lab_test(other_clinic)

        with pytest.raises(ValidationError):
            svc.create_lab_order(
                clinic_id=clinic.id, patient_id=patient.id, ordered_by_id=doctor.id, test_ids=[test.id],
            )

    def test_create_lab_order_rejects_inactive_test(self, db, clinic, make_patient, make_staff, make_lab_test):
        doctor = make_staff(clinic, role=Role.DOCTOR)
        patient = make_patient(clinic)
        test = make_lab_test(clinic, is_active=False)

        with pytest.raises(ValidationError):
            svc.create_lab_order(
                clinic_id=clinic.id, patient_id=patient.id, ordered_by_id=doctor.id, test_ids=[test.id],
            )

    def test_list_orders_for_patient(self, db, clinic, make_patient, make_staff, make_lab_test):
        doctor = make_staff(clinic, role=Role.DOCTOR)
        patient = make_patient(clinic)
        test = make_lab_test(clinic)

        order = svc.create_lab_order(
            clinic_id=clinic.id, patient_id=patient.id, ordered_by_id=doctor.id, test_ids=[test.id],
        )

        results = svc.list_orders_for_patient(patient.id)
        assert [o.id for o in results] == [order.id]


class TestSampleCollectionAndCancellation:
    def _order(self, clinic, make_patient, make_staff, make_lab_test):
        doctor = make_staff(clinic, role=Role.DOCTOR)
        patient = make_patient(clinic)
        test = make_lab_test(clinic)
        return svc.create_lab_order(
            clinic_id=clinic.id, patient_id=patient.id, ordered_by_id=doctor.id, test_ids=[test.id],
        )

    def test_collect_sample_happy_path(self, db, clinic, make_patient, make_staff, make_lab_test):
        order = self._order(clinic, make_patient, make_staff, make_lab_test)
        collected = svc.collect_sample(order.id)

        assert collected.status == LabOrderStatus.SAMPLE_COLLECTED
        assert collected.sample_collected_at is not None

    def test_collect_sample_rejects_mismatched_qr_code(self, db, clinic, make_patient, make_staff, make_lab_test):
        order = self._order(clinic, make_patient, make_staff, make_lab_test)

        with pytest.raises(ConflictError):
            svc.collect_sample(order.id, scanned_qr_code="WRONG-CODE")

    def test_collect_sample_rejects_wrong_status(self, db, clinic, make_patient, make_staff, make_lab_test):
        order = self._order(clinic, make_patient, make_staff, make_lab_test)
        svc.collect_sample(order.id)

        with pytest.raises(ConflictError):
            svc.collect_sample(order.id)

    def test_cancel_order_happy_path(self, db, clinic, make_patient, make_staff, make_lab_test):
        order = self._order(clinic, make_patient, make_staff, make_lab_test)
        cancelled = svc.cancel_order(order.id, reason="Patient declined")

        assert cancelled.status == LabOrderStatus.CANCELLED
        assert cancelled.cancellation_reason == "Patient declined"

    def test_cancel_order_rejects_already_completed(self, db, clinic, make_patient, make_staff, make_lab_test):
        order = self._order(clinic, make_patient, make_staff, make_lab_test)
        svc.collect_sample(order.id)
        item_id = order.items[0].id
        svc.enter_result(item_id, result_value="5")

        with pytest.raises(ConflictError):
            svc.cancel_order(order.id)


class TestEquipmentLinking:
    def test_link_equipment_happy_path(self, db, clinic, make_patient, make_staff, make_lab_test):
        doctor = make_staff(clinic, role=Role.DOCTOR)
        patient = make_patient(clinic)
        test = make_lab_test(clinic)
        order = svc.create_lab_order(
            clinic_id=clinic.id, patient_id=patient.id, ordered_by_id=doctor.id, test_ids=[test.id],
        )
        svc.collect_sample(order.id)

        linked = svc.link_equipment(order.id, "EQ-123")

        assert linked.status == LabOrderStatus.IN_PROGRESS
        assert linked.equipment_reference_id == "EQ-123"

    def test_link_equipment_rejects_blank_reference(self, db, clinic, make_patient, make_staff, make_lab_test):
        doctor = make_staff(clinic, role=Role.DOCTOR)
        patient = make_patient(clinic)
        test = make_lab_test(clinic)
        order = svc.create_lab_order(
            clinic_id=clinic.id, patient_id=patient.id, ordered_by_id=doctor.id, test_ids=[test.id],
        )
        svc.collect_sample(order.id)

        with pytest.raises(ValidationError):
            svc.link_equipment(order.id, "   ")

    def test_link_equipment_rejects_wrong_status(self, db, clinic, make_patient, make_staff, make_lab_test):
        doctor = make_staff(clinic, role=Role.DOCTOR)
        patient = make_patient(clinic)
        test = make_lab_test(clinic)
        order = svc.create_lab_order(
            clinic_id=clinic.id, patient_id=patient.id, ordered_by_id=doctor.id, test_ids=[test.id],
        )
        # Not collected yet -> still ORDERED
        with pytest.raises(ConflictError):
            svc.link_equipment(order.id, "EQ-123")


class TestResultEntryAndAutoFlagging:
    def _collected_order(self, clinic, make_patient, make_staff, make_lab_test, **test_overrides):
        doctor = make_staff(clinic, role=Role.DOCTOR)
        patient = make_patient(clinic)
        test = make_lab_test(clinic, **test_overrides)
        order = svc.create_lab_order(
            clinic_id=clinic.id, patient_id=patient.id, ordered_by_id=doctor.id, test_ids=[test.id],
        )
        svc.collect_sample(order.id)
        return order, test

    def test_enter_result_rejects_blank_value(self, db, clinic, make_patient, make_staff, make_lab_test):
        order, _ = self._collected_order(clinic, make_patient, make_staff, make_lab_test)
        item_id = order.items[0].id

        with pytest.raises(ValidationError):
            svc.enter_result(item_id, result_value="   ")

    def test_enter_result_not_found(self, db):
        with pytest.raises(NotFoundError):
            svc.enter_result(999999, result_value="5")

    def test_enter_result_explicit_flag_wins_over_auto(self, db, clinic, make_patient, make_staff, make_lab_test):
        order, test = self._collected_order(
            clinic, make_patient, make_staff, make_lab_test, reference_range="10 - 20"
        )
        item_id = order.items[0].id

        item = svc.enter_result(item_id, result_value="15", flag=LabResultFlag.CRITICAL)
        assert item.flag == LabResultFlag.CRITICAL

    def test_enter_result_auto_flags_critical_threshold(self, db, clinic, make_patient, make_staff, make_lab_test):
        order, test = self._collected_order(
            clinic, make_patient, make_staff, make_lab_test,
            critical_low=Decimal("2"), critical_high=Decimal("10"),
        )
        item_id = order.items[0].id

        item = svc.enter_result(item_id, result_value="1")
        assert item.flag == LabResultFlag.CRITICAL

    def test_enter_result_auto_flags_normal_range(self, db, clinic, make_patient, make_staff, make_lab_test):
        order, test = self._collected_order(
            clinic, make_patient, make_staff, make_lab_test, reference_range="10 - 20"
        )
        item_id = order.items[0].id

        item = svc.enter_result(item_id, result_value="15")
        assert item.flag == LabResultFlag.NORMAL

    def test_enter_result_auto_flags_abnormal_out_of_range(self, db, clinic, make_patient, make_staff, make_lab_test):
        order, test = self._collected_order(
            clinic, make_patient, make_staff, make_lab_test, reference_range="10 - 20"
        )
        item_id = order.items[0].id

        item = svc.enter_result(item_id, result_value="99")
        assert item.flag == LabResultFlag.ABNORMAL

    def test_enter_result_auto_flags_bound_pattern(self, db, clinic, make_patient, make_staff, make_lab_test):
        order, test = self._collected_order(
            clinic, make_patient, make_staff, make_lab_test, reference_range="< 5"
        )
        item_id = order.items[0].id

        item = svc.enter_result(item_id, result_value="3")
        assert item.flag == LabResultFlag.NORMAL

        # New order/item to test the failing side of the same bound
        order2, _ = self._collected_order(clinic, make_patient, make_staff, make_lab_test, reference_range="< 5")

    def test_enter_result_leaves_non_numeric_unflagged(self, db, clinic, make_patient, make_staff, make_lab_test):
        order, test = self._collected_order(
            clinic, make_patient, make_staff, make_lab_test, reference_range="10 - 20"
        )
        item_id = order.items[0].id

        item = svc.enter_result(item_id, result_value="Positive")
        assert item.flag is None

    def test_enter_result_completes_order_when_all_items_resulted(
        self, db, clinic, make_patient, make_staff, make_lab_test
    ):
        doctor = make_staff(clinic, role=Role.DOCTOR)
        patient = make_patient(clinic)
        test_a = make_lab_test(clinic)
        test_b = make_lab_test(clinic)

        order = svc.create_lab_order(
            clinic_id=clinic.id, patient_id=patient.id, ordered_by_id=doctor.id,
            test_ids=[test_a.id, test_b.id],
        )
        svc.collect_sample(order.id)

        item_a_id, item_b_id = [item.id for item in order.items]

        svc.enter_result(item_a_id, result_value="1")
        assert svc.get_lab_order(order.id).status == LabOrderStatus.SAMPLE_COLLECTED  # not done yet

        svc.enter_result(item_b_id, result_value="2")
        assert svc.get_lab_order(order.id).status == LabOrderStatus.COMPLETED
        assert svc.get_lab_order(order.id).completed_at is not None