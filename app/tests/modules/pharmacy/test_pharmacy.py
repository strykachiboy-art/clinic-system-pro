from datetime import date, timedelta

from app.core.enums.role_enums import Role


def _auth(make_authenticated_staff, clinic, role=Role.PHARMACIST):
    _, headers = make_authenticated_staff(clinic, role)
    return headers


class TestDrugRoutes:
    def test_create_drug_requires_auth(self, client, assert_unauthorized):
        resp = client.post("/pharmacy/drugs", json={"name": "X"})
        assert_unauthorized(resp)

    def test_create_drug_rejects_wrong_role(self, client, clinic, make_authenticated_staff, assert_forbidden):
        _, headers = make_authenticated_staff(clinic, Role.NURSE)
        resp = client.post("/pharmacy/drugs", json={"name": "X"}, headers=headers)
        assert_forbidden(resp)

    def test_create_drug_happy_path(self, client, clinic, make_authenticated_staff):
        headers = _auth(make_authenticated_staff, clinic)
        resp = client.post(
            "/pharmacy/drugs",
            json={"name": "Amoxicillin", "clinic_id": clinic.id, "unit_price": "5.50"},
            headers=headers,
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"]["name"] == "Amoxicillin"
        assert body["data"]["unit_price"] == "5.50"

    def test_create_drug_rejects_blank_name(self, client, clinic, make_authenticated_staff, assert_domain_error):
        headers = _auth(make_authenticated_staff, clinic)
        resp = client.post("/pharmacy/drugs", json={"name": ""}, headers=headers)
        # Pydantic min_length=1 rejects blank at the schema layer -> 422 with
        # a "details" key rather than the plain domain-error shape, since
        # this never reaches the service layer at all.
        assert resp.status_code == 422

    def test_get_drug_not_found(self, client, clinic, make_authenticated_staff, assert_domain_error):
        headers = _auth(make_authenticated_staff, clinic)
        resp = client.get("/pharmacy/drugs/999999", headers=headers)
        assert_domain_error(resp, 404)

    def test_list_drugs_scoped_to_clinic(self, client, clinic, make_clinic, make_drug, make_authenticated_staff):
        other = make_clinic(name="Other")
        make_drug(clinic, name="Mine")
        make_drug(other, name="Theirs")
        make_drug(None, name="Global")

        headers = _auth(make_authenticated_staff, clinic)
        resp = client.get(f"/pharmacy/drugs?clinic_id={clinic.id}", headers=headers)

        assert resp.status_code == 200
        names = {d["name"] for d in resp.get_json()["data"]}
        assert names == {"Mine", "Global"}

    def test_update_drug(self, client, clinic, make_drug, make_authenticated_staff):
        drug = make_drug(clinic)
        headers = _auth(make_authenticated_staff, clinic)

        resp = client.patch(
            f"/pharmacy/drugs/{drug.id}", json={"name": "Renamed"}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["name"] == "Renamed"

    def test_activate_deactivate_drug_requires_admin(self, client, clinic, make_drug, make_authenticated_staff, assert_forbidden):
        drug = make_drug(clinic)
        pharmacist_headers = _auth(make_authenticated_staff, clinic, Role.PHARMACIST)

        # Pharmacist is allowed to read/create/update drugs, but not
        # activate/deactivate — that route is Role.ADMIN only.
        resp = client.post(f"/pharmacy/drugs/{drug.id}/deactivate", headers=pharmacist_headers)
        assert_forbidden(resp)

        admin_headers = _auth(make_authenticated_staff, clinic, Role.ADMIN)
        resp2 = client.post(f"/pharmacy/drugs/{drug.id}/deactivate", headers=admin_headers)
        assert resp2.status_code == 200
        assert resp2.get_json()["data"]["is_active"] is False


class TestBatchRoutes:
    def test_create_batch_and_list(self, client, clinic, make_drug, make_authenticated_staff):
        drug = make_drug(clinic)
        headers = _auth(make_authenticated_staff, clinic)

        resp = client.post(
            "/pharmacy/batches",
            json={
                "clinic_id": clinic.id,
                "drug_id": drug.id,
                "batch_number": "B1",
                "quantity_on_hand": 50,
                "expiry_date": str(date.today() + timedelta(days=60)),
            },
            headers=headers,
        )
        assert resp.status_code == 201

        list_resp = client.get(
            f"/pharmacy/drugs/{drug.id}/batches?clinic_id={clinic.id}", headers=headers
        )
        assert list_resp.status_code == 200
        assert len(list_resp.get_json()["data"]) == 1

    def test_create_batch_rejects_past_expiry(self, client, clinic, make_drug, make_authenticated_staff, assert_domain_error):
        drug = make_drug(clinic)
        headers = _auth(make_authenticated_staff, clinic)

        resp = client.post(
            "/pharmacy/batches",
            json={
                "clinic_id": clinic.id,
                "drug_id": drug.id,
                "batch_number": "B1",
                "quantity_on_hand": 50,
                "expiry_date": str(date.today() - timedelta(days=1)),
            },
            headers=headers,
        )
        assert_domain_error(resp, 422)

    def test_expiring_batches_requires_clinic_id_query_param(self, client, clinic, make_authenticated_staff, assert_domain_error):
        headers = _auth(make_authenticated_staff, clinic)
        resp = client.get("/pharmacy/batches/expiring", headers=headers)
        assert_domain_error(resp, 422)

    def test_stock_summary(self, client, clinic, make_drug, make_drug_batch, make_authenticated_staff):
        drug = make_drug(clinic)
        make_drug_batch(clinic, drug, quantity_on_hand=30)
        make_drug_batch(clinic, drug, quantity_on_hand=15)

        headers = _auth(make_authenticated_staff, clinic)
        resp = client.get(
            f"/pharmacy/drugs/{drug.id}/stock-summary?clinic_id={clinic.id}", headers=headers
        )

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["quantity_on_hand"] == 45
        assert data["batch_count"] == 2


class TestDispenseRoutes:
    def _build_prescription(self, clinic, make_staff, make_patient, make_drug, make_drug_batch, make_prescription, make_prescription_item, quantity=10, stock=20):
        pharmacist = make_staff(clinic, role=Role.PHARMACIST)
        patient = make_patient(clinic)
        drug = make_drug(clinic)
        batch = make_drug_batch(clinic, drug, quantity_on_hand=stock)
        prescription = make_prescription(clinic, patient, pharmacist)
        item = make_prescription_item(prescription, drug, quantity=quantity)
        return pharmacist, patient, drug, batch, prescription, item

    def test_create_dispense_record_happy_path(
        self, client, clinic, make_staff, make_patient, make_drug, make_drug_batch,
        make_prescription, make_prescription_item, make_authenticated_staff,
    ):
        pharmacist, patient, drug, batch, prescription, item = self._build_prescription(
            clinic, make_staff, make_patient, make_drug, make_drug_batch,
            make_prescription, make_prescription_item,
        )
        headers = _auth(make_authenticated_staff, clinic)

        resp = client.post(
            "/pharmacy/dispense",
            json={
                "clinic_id": clinic.id,
                "prescription_id": prescription.id,
                "dispensed_by_id": pharmacist.id,
                "items": [{"prescription_item_id": item.id, "quantity": 10}],
            },
            headers=headers,
        )

        assert resp.status_code == 201
        body = resp.get_json()["data"]
        assert body["status"] == "dispensed"
        assert len(body["items"]) == 1

    def test_create_dispense_record_insufficient_stock_maps_to_409(
        self, client, clinic, make_staff, make_patient, make_drug, make_drug_batch,
        make_prescription, make_prescription_item, make_authenticated_staff, assert_domain_error,
    ):
        pharmacist, patient, drug, batch, prescription, item = self._build_prescription(
            clinic, make_staff, make_patient, make_drug, make_drug_batch,
            make_prescription, make_prescription_item, quantity=999, stock=2,
        )
        headers = _auth(make_authenticated_staff, clinic)

        resp = client.post(
            "/pharmacy/dispense",
            json={
                "clinic_id": clinic.id,
                "prescription_id": prescription.id,
                "dispensed_by_id": pharmacist.id,
                "items": [{"prescription_item_id": item.id, "quantity": 5}],
            },
            headers=headers,
        )
        assert_domain_error(resp, 409)

    def test_create_dispense_record_requires_at_least_one_item(
        self, client, clinic, make_authenticated_staff, assert_domain_error,
    ):
        headers = _auth(make_authenticated_staff, clinic)
        resp = client.post(
            "/pharmacy/dispense",
            json={
                "clinic_id": clinic.id,
                "prescription_id": 1,
                "dispensed_by_id": 1,
                "items": [],
            },
            headers=headers,
        )
        # min_length=1 on items -> pydantic 422, never reaches the service
        assert resp.status_code == 422

    def test_cancel_dispense_record(
        self, client, clinic, make_staff, make_patient, make_drug, make_drug_batch,
        make_prescription, make_prescription_item, make_authenticated_staff,
    ):
        pharmacist, patient, drug, batch, prescription, item = self._build_prescription(
            clinic, make_staff, make_patient, make_drug, make_drug_batch,
            make_prescription, make_prescription_item, quantity=10, stock=20,
        )
        headers = _auth(make_authenticated_staff, clinic)

        create_resp = client.post(
            "/pharmacy/dispense",
            json={
                "clinic_id": clinic.id,
                "prescription_id": prescription.id,
                "dispensed_by_id": pharmacist.id,
                "items": [{"prescription_item_id": item.id, "quantity": 4}],
            },
            headers=headers,
        )
        record_id = create_resp.get_json()["data"]["id"]

        cancel_resp = client.post(
            f"/pharmacy/dispense/{record_id}/cancel",
            json={"clinic_id": clinic.id},
            headers=headers,
        )

        assert cancel_resp.status_code == 200
        assert cancel_resp.get_json()["data"]["status"] == "cancelled"

    def test_list_dispense_records_for_prescription(
        self, client, clinic, make_staff, make_patient, make_drug, make_drug_batch,
        make_prescription, make_prescription_item, make_authenticated_staff,
    ):
        pharmacist, patient, drug, batch, prescription, item = self._build_prescription(
            clinic, make_staff, make_patient, make_drug, make_drug_batch,
            make_prescription, make_prescription_item,
        )
        headers = _auth(make_authenticated_staff, clinic)

        client.post(
            "/pharmacy/dispense",
            json={
                "clinic_id": clinic.id,
                "prescription_id": prescription.id,
                "dispensed_by_id": pharmacist.id,
                "items": [{"prescription_item_id": item.id, "quantity": 3}],
            },
            headers=headers,
        )

        resp = client.get(
            f"/pharmacy/prescriptions/{prescription.id}/dispense-records", headers=headers
        )
        assert resp.status_code == 200
        assert len(resp.get_json()["data"]) == 1