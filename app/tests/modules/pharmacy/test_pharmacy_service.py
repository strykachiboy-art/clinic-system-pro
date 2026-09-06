from datetime import date, timedelta

import pytest

from app.core.enums.pharmacy_enums import DispenseStatus, DrugCategory
from app.core.enums.prescription_enums import PrescriptionStatus
from app.core.enums.role_enums import Role
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.pharmacy.services import pharmacy_service as svc


class TestDrugCatalog:
    def test_create_drug_global(self, db):
        drug = svc.create_drug(name="Amoxicillin")

        assert drug.id is not None
        assert drug.clinic_id is None
        assert drug.is_active is True
        assert drug.category == DrugCategory.OTHER

    def test_create_drug_clinic_specific(self, db, clinic):
        drug = svc.create_drug(name="Local Mix", clinic_id=clinic.id)

        assert drug.clinic_id == clinic.id

    def test_create_drug_rejects_blank_name(self, db):
        with pytest.raises(ValidationError):
            svc.create_drug(name="   ")

    def test_create_drug_rejects_negative_price(self, db):
        with pytest.raises(ValidationError):
            svc.create_drug(name="X", unit_price=-1)

    def test_create_drug_rejects_duplicate_barcode(self, db):
        svc.create_drug(name="A", barcode="123")

        with pytest.raises(ConflictError):
            svc.create_drug(name="B", barcode="123")

    def test_create_drug_requires_active_clinic(self, db, suspended_clinic):
        with pytest.raises(Exception):
            svc.create_drug(name="X", clinic_id=suspended_clinic.id)

    def test_get_drug_not_found(self, db):
        with pytest.raises(NotFoundError):
            svc.get_drug(999999)

    def test_get_drug_works_even_for_inactive_drug(self, db):
        drug = svc.create_drug(name="Old Drug")
        svc.set_drug_active_status(drug.id, is_active=False)

        fetched = svc.get_drug(drug.id)
        assert fetched.id == drug.id

    def test_list_drugs_global_only_without_clinic(self, db, clinic):
        svc.create_drug(name="Global")
        svc.create_drug(name="ClinicOnly", clinic_id=clinic.id)

        results = svc.list_drugs(clinic_id=None)
        names = {d.name for d in results}

        assert "Global" in names
        assert "ClinicOnly" not in names

    def test_list_drugs_includes_global_and_own_clinic(self, db, clinic, make_clinic):
        other_clinic = make_clinic(name="Other")
        svc.create_drug(name="Global")
        svc.create_drug(name="Mine", clinic_id=clinic.id)
        svc.create_drug(name="Theirs", clinic_id=other_clinic.id)

        names = {d.name for d in svc.list_drugs(clinic_id=clinic.id)}

        assert names == {"Global", "Mine"}

    def test_list_drugs_excludes_inactive_by_default(self, db):
        drug = svc.create_drug(name="Inactive Me")
        svc.set_drug_active_status(drug.id, is_active=False)

        names = {d.name for d in svc.list_drugs()}
        assert "Inactive Me" not in names

        names_all = {d.name for d in svc.list_drugs(include_inactive=True)}
        assert "Inactive Me" in names_all

    def test_update_drug_rejects_unknown_field(self, db):
        drug = svc.create_drug(name="X")

        with pytest.raises(ValidationError):
            svc.update_drug(drug.id, not_a_real_field=1)

    def test_update_drug_happy_path(self, db):
        drug = svc.create_drug(name="X")
        updated = svc.update_drug(drug.id, name="  Y  ", unit_price=9)

        assert updated.name == "Y"
        assert float(updated.unit_price) == 9

    def test_update_drug_rejects_duplicate_barcode(self, db):
        svc.create_drug(name="A", barcode="AAA")
        b = svc.create_drug(name="B", barcode="BBB")

        with pytest.raises(ConflictError):
            svc.update_drug(b.id, barcode="AAA")

    def test_set_drug_active_status_toggles(self, db):
        drug = svc.create_drug(name="X")
        svc.set_drug_active_status(drug.id, is_active=False)
        assert svc.get_drug(drug.id).is_active is False

        svc.set_drug_active_status(drug.id, is_active=True)
        assert svc.get_drug(drug.id).is_active is True


class TestBatches:
    def test_add_batch_happy_path(self, db, clinic, make_drug):
        drug = make_drug(clinic)

        batch = svc.add_batch(
            clinic_id=clinic.id,
            drug_id=drug.id,
            batch_number="B1",
            quantity_on_hand=50,
            expiry_date=date.today() + timedelta(days=30),
        )

        assert batch.id is not None
        assert batch.quantity_on_hand == 50

    def test_add_batch_rejects_already_expired(self, db, clinic, make_drug):
        drug = make_drug(clinic)

        with pytest.raises(ValidationError):
            svc.add_batch(
                clinic_id=clinic.id,
                drug_id=drug.id,
                batch_number="B1",
                quantity_on_hand=10,
                expiry_date=date.today() - timedelta(days=1),
            )

    def test_add_batch_rejects_inactive_drug(self, db, clinic, make_drug):
        drug = make_drug(clinic)
        svc.set_drug_active_status(drug.id, is_active=False)

        with pytest.raises(ValidationError):
            svc.add_batch(
                clinic_id=clinic.id,
                drug_id=drug.id,
                batch_number="B1",
                quantity_on_hand=10,
                expiry_date=date.today() + timedelta(days=30),
            )

    def test_add_batch_rejects_wrong_clinic_scope(
        self, db, clinic, make_clinic, make_drug
    ):
        other_clinic = make_clinic(name="Other")
        drug = make_drug(clinic)  # clinic-specific to `clinic`

        with pytest.raises(ValidationError):
            svc.add_batch(
                clinic_id=other_clinic.id,
                drug_id=drug.id,
                batch_number="B1",
                quantity_on_hand=10,
                expiry_date=date.today() + timedelta(days=30),
            )

    def test_add_batch_rejects_duplicate_batch_number(self, db, clinic, make_drug):
        drug = make_drug(clinic)
        svc.add_batch(
            clinic_id=clinic.id,
            drug_id=drug.id,
            batch_number="DUP",
            quantity_on_hand=10,
            expiry_date=date.today() + timedelta(days=30),
        )

        with pytest.raises(ConflictError):
            svc.add_batch(
                clinic_id=clinic.id,
                drug_id=drug.id,
                batch_number="DUP",
                quantity_on_hand=5,
                expiry_date=date.today() + timedelta(days=60),
            )

    def test_list_expiring_batches_window(self, db, clinic, make_drug, make_drug_batch):
        drug = make_drug(clinic)
        soon = make_drug_batch(
            clinic, drug, expiry_date=date.today() + timedelta(days=5)
        )
        make_drug_batch(clinic, drug, expiry_date=date.today() + timedelta(days=200))

        results = svc.list_expiring_batches(clinic.id, days=30)
        ids = {b.id for b in results}

        assert soon.id in ids
        assert len(results) == 1

    def test_get_stock_summary_sums_unexpired_batches(
        self, db, clinic, make_drug, make_drug_batch
    ):
        drug = make_drug(clinic)
        make_drug_batch(clinic, drug, quantity_on_hand=40)
        make_drug_batch(clinic, drug, quantity_on_hand=10)
        make_drug_batch(
            clinic,
            drug,
            quantity_on_hand=999,
            expiry_date=date.today() - timedelta(days=1),
            batch_number="EXPIRED",
        )

        summary = svc.get_stock_summary(clinic.id, drug.id)

        assert summary["quantity_on_hand"] == 50
        assert summary["batch_count"] == 2


class TestDispensing:
    @pytest.fixture()
    def dispensing_setup(self, clinic, make_staff, make_patient, make_drug, make_drug_batch, make_prescription, make_prescription_item):
        pharmacist = make_staff(clinic, role=Role.PHARMACIST)
        patient = make_patient(clinic)
        drug = make_drug(clinic)
        batch = make_drug_batch(clinic, drug, quantity_on_hand=20)
        prescription = make_prescription(clinic, patient, pharmacist)
        item = make_prescription_item(prescription, drug, quantity=10)

        return {
            "pharmacist": pharmacist,
            "patient": patient,
            "drug": drug,
            "batch": batch,
            "prescription": prescription,
            "item": item,
        }

    def test_create_dispense_record_full_fulfillment(self, db, clinic, dispensing_setup):
        s = dispensing_setup

        record = svc.create_dispense_record(
            clinic_id=clinic.id,
            prescription_id=s["prescription"].id,
            dispensed_by_id=s["pharmacist"].id,
            items=[{"prescription_item_id": s["item"].id, "quantity": 10}],
        )

        assert record.status == DispenseStatus.DISPENSED
        assert s["batch"].quantity_on_hand == 10  # 20 - 10

    def test_create_dispense_record_partial_fulfillment(self, db, clinic, dispensing_setup):
        s = dispensing_setup

        record = svc.create_dispense_record(
            clinic_id=clinic.id,
            prescription_id=s["prescription"].id,
            dispensed_by_id=s["pharmacist"].id,
            items=[{"prescription_item_id": s["item"].id, "quantity": 4}],
        )

        assert record.status == DispenseStatus.PARTIALLY_DISPENSED

    def test_create_dispense_record_fefo_order(self, db, clinic, make_staff, make_patient, make_drug, make_drug_batch, make_prescription, make_prescription_item):
        pharmacist = make_staff(clinic, role=Role.PHARMACIST)
        patient = make_patient(clinic)
        drug = make_drug(clinic)

        # Earlier-expiring batch should be drained first
        expires_soon = make_drug_batch(
            clinic, drug, quantity_on_hand=5, expiry_date=date.today() + timedelta(days=5)
        )
        expires_later = make_drug_batch(
            clinic, drug, quantity_on_hand=20, expiry_date=date.today() + timedelta(days=200)
        )

        prescription = make_prescription(clinic, patient, pharmacist)
        item = make_prescription_item(prescription, drug, quantity=10)

        svc.create_dispense_record(
            clinic_id=clinic.id,
            prescription_id=prescription.id,
            dispensed_by_id=pharmacist.id,
            items=[{"prescription_item_id": item.id, "quantity": 10}],
        )

        assert expires_soon.quantity_on_hand == 0
        assert expires_later.quantity_on_hand == 15  # 20 - (10 - 5)

    def test_create_dispense_record_insufficient_stock(self, db, clinic, dispensing_setup):
        s = dispensing_setup
        s["batch"].quantity_on_hand = 2
        db.session.commit()

        with pytest.raises(ConflictError):
            svc.create_dispense_record(
                clinic_id=clinic.id,
                prescription_id=s["prescription"].id,
                dispensed_by_id=s["pharmacist"].id,
                items=[{"prescription_item_id": s["item"].id, "quantity": 10}],
            )

    def test_create_dispense_record_rejects_over_remaining_quantity(self, db, clinic, dispensing_setup):
        s = dispensing_setup

        with pytest.raises(ValidationError):
            svc.create_dispense_record(
                clinic_id=clinic.id,
                prescription_id=s["prescription"].id,
                dispensed_by_id=s["pharmacist"].id,
                items=[{"prescription_item_id": s["item"].id, "quantity": 999}],
            )

    def test_create_dispense_record_rejects_non_pharmacist_staff(self, db, clinic, make_staff, dispensing_setup):
        s = dispensing_setup
        nurse = make_staff(clinic, role=Role.NURSE)

        with pytest.raises(ValidationError):
            svc.create_dispense_record(
                clinic_id=clinic.id,
                prescription_id=s["prescription"].id,
                dispensed_by_id=nurse.id,
                items=[{"prescription_item_id": s["item"].id, "quantity": 5}],
            )

    def test_create_dispense_record_rejects_inactive_prescription(self, db, clinic, dispensing_setup):
        s = dispensing_setup
        s["prescription"].status = PrescriptionStatus.CANCELLED
        db.session.commit()

        with pytest.raises(ValidationError):
            svc.create_dispense_record(
                clinic_id=clinic.id,
                prescription_id=s["prescription"].id,
                dispensed_by_id=s["pharmacist"].id,
                items=[{"prescription_item_id": s["item"].id, "quantity": 5}],
            )

    def test_create_dispense_record_rejects_duplicate_items(self, db, clinic, dispensing_setup):
        s = dispensing_setup

        with pytest.raises(ValidationError):
            svc.create_dispense_record(
                clinic_id=clinic.id,
                prescription_id=s["prescription"].id,
                dispensed_by_id=s["pharmacist"].id,
                items=[
                    {"prescription_item_id": s["item"].id, "quantity": 2},
                    {"prescription_item_id": s["item"].id, "quantity": 3},
                ],
            )

    def test_cancel_dispense_record_restores_stock(self, db, clinic, dispensing_setup):
        s = dispensing_setup

        # Dispense less than the full prescribed quantity (4 of 10) so
        # the record lands in PARTIALLY_DISPENSED, which is cancellable
        # — a fully DISPENSED record cannot be, by design.
        record = svc.create_dispense_record(
            clinic_id=clinic.id,
            prescription_id=s["prescription"].id,
            dispensed_by_id=s["pharmacist"].id,
            items=[{"prescription_item_id": s["item"].id, "quantity": 4}],
        )
        assert record.status == DispenseStatus.PARTIALLY_DISPENSED
        assert s["batch"].quantity_on_hand == 16  # 20 - 4

        cancelled = svc.cancel_dispense_record(
            clinic_id=clinic.id,
            dispense_record_id=record.id,
        )

        assert cancelled.status == DispenseStatus.CANCELLED
        assert s["batch"].quantity_on_hand == 20

    def test_cancel_already_cancelled_conflicts(self, db, clinic, dispensing_setup):
        s = dispensing_setup

        record = svc.create_dispense_record(
            clinic_id=clinic.id,
            prescription_id=s["prescription"].id,
            dispensed_by_id=s["pharmacist"].id,
            items=[{"prescription_item_id": s["item"].id, "quantity": 5}],
        )
        svc.cancel_dispense_record(clinic_id=clinic.id, dispense_record_id=record.id)

        with pytest.raises(ConflictError):
            svc.cancel_dispense_record(clinic_id=clinic.id, dispense_record_id=record.id)

    def test_cancel_fully_dispensed_conflicts(self, db, clinic, dispensing_setup):
        s = dispensing_setup

        record = svc.create_dispense_record(
            clinic_id=clinic.id,
            prescription_id=s["prescription"].id,
            dispensed_by_id=s["pharmacist"].id,
            items=[{"prescription_item_id": s["item"].id, "quantity": 10}],
        )
        assert record.status == DispenseStatus.DISPENSED

        with pytest.raises(ConflictError):
            svc.cancel_dispense_record(clinic_id=clinic.id, dispense_record_id=record.id)

    def test_list_dispense_records_for_prescription_ordering(self, db, clinic, dispensing_setup):
        s = dispensing_setup

        r1 = svc.create_dispense_record(
            clinic_id=clinic.id,
            prescription_id=s["prescription"].id,
            dispensed_by_id=s["pharmacist"].id,
            items=[{"prescription_item_id": s["item"].id, "quantity": 3}],
        )

        results = svc.list_dispense_records_for_prescription(s["prescription"].id)
        assert len(results) == 1
        assert results[0].id == r1.id