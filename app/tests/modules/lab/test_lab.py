from app.core.enums.role_enums import Role


def _headers(make_authenticated_staff, clinic, role):
    _, h = make_authenticated_staff(clinic, role)
    return h


class TestLabTestRoutes:
    def test_create_lab_test_requires_admin(self, client, clinic, make_authenticated_staff, assert_forbidden):
        headers = _headers(make_authenticated_staff, clinic, Role.LAB_TECHNICIAN)
        resp = client.post("/api/lab/tests", json={"name": "CBC"}, headers=headers)
        assert_forbidden(resp)

    def test_create_lab_test_happy_path(self, client, clinic, make_authenticated_staff):
        headers = _headers(make_authenticated_staff, clinic, Role.ADMIN)
        resp = client.post(
            "/api/lab/tests", json={"name": "CBC", "code": "CBC1", "sample_type": "blood"}, headers=headers
        )
        assert resp.status_code == 201
        assert resp.get_json()["data"]["name"] == "CBC"

    def test_create_lab_test_rejects_bad_critical_range_at_schema_layer(
        self, client, clinic, make_authenticated_staff
    ):
        headers = _headers(make_authenticated_staff, clinic, Role.ADMIN)
        resp = client.post(
            "/api/lab/tests",
            json={"name": "X", "critical_low": "10", "critical_high": "5"},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_get_lab_test_not_found(self, client, clinic, make_authenticated_staff, assert_domain_error):
        headers = _headers(make_authenticated_staff, clinic, Role.DOCTOR)
        resp = client.get("/api/lab/tests/999999", headers=headers)
        assert_domain_error(resp, 404)

    def test_list_lab_tests_scoping(self, client, clinic, make_lab_test, make_authenticated_staff):
        make_lab_test(None, name="Global")
        make_lab_test(clinic, name="ClinicOnly")
        headers = _headers(make_authenticated_staff, clinic, Role.RECEPTIONIST)

        resp = client.get(f"/api/lab/tests?clinic_id={clinic.id}", headers=headers)
        assert resp.status_code == 200
        names = {t["name"] for t in resp.get_json()["data"]}
        assert names == {"Global", "ClinicOnly"}

    def test_update_lab_test(self, client, clinic, make_lab_test, make_authenticated_staff):
        test = make_lab_test(clinic, name="Old")
        headers = _headers(make_authenticated_staff, clinic, Role.ADMIN)

        resp = client.patch(f"/api/lab/tests/{test.id}", json={"is_active": False}, headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["is_active"] is False


class TestLabOrderRoutes:
    def test_create_lab_order_requires_clinical_role(
        self, client, clinic, make_patient, make_lab_test, make_authenticated_staff, assert_forbidden
    ):
        patient = make_patient(clinic)
        test = make_lab_test(clinic)
        headers = _headers(make_authenticated_staff, clinic, Role.RECEPTIONIST)

        resp = client.post(
            "/api/lab/orders",
            json={"clinic_id": clinic.id, "patient_id": patient.id, "ordered_by_id": 1, "test_ids": [test.id]},
            headers=headers,
        )
        assert_forbidden(resp)

    def test_create_lab_order_happy_path(self, client, clinic, make_patient, make_lab_test, make_authenticated_staff):
        doctor, headers = make_authenticated_staff(clinic, Role.DOCTOR)
        patient = make_patient(clinic)
        test = make_lab_test(clinic)

        resp = client.post(
            "/api/lab/orders",
            json={
                "clinic_id": clinic.id,
                "patient_id": patient.id,
                "ordered_by_id": doctor.id,
                "test_ids": [test.id],
            },
            headers=headers,
        )
        assert resp.status_code == 201
        body = resp.get_json()["data"]
        assert body["status"] == "ordered"
        assert body["qr_code"] is not None
        assert len(body["items"]) == 1

    def test_create_lab_order_rejects_duplicate_test_ids_at_schema_layer(
        self, client, clinic, make_patient, make_lab_test, make_authenticated_staff
    ):
        doctor, headers = make_authenticated_staff(clinic, Role.DOCTOR)
        patient = make_patient(clinic)
        test = make_lab_test(clinic)

        resp = client.post(
            "/api/lab/orders",
            json={
                "clinic_id": clinic.id,
                "patient_id": patient.id,
                "ordered_by_id": doctor.id,
                "test_ids": [test.id, test.id],
            },
            headers=headers,
        )
        assert resp.status_code == 422

    def test_get_lab_order_not_found(self, client, clinic, make_authenticated_staff, assert_domain_error):
        headers = _headers(make_authenticated_staff, clinic, Role.DOCTOR)
        resp = client.get("/api/lab/orders/999999", headers=headers)
        assert_domain_error(resp, 404)

    def test_list_orders_for_patient(self, client, clinic, make_patient, make_lab_test, make_authenticated_staff):
        doctor, headers = make_authenticated_staff(clinic, Role.DOCTOR)
        patient = make_patient(clinic)
        test = make_lab_test(clinic)

        client.post(
            "/api/lab/orders",
            json={"clinic_id": clinic.id, "patient_id": patient.id, "ordered_by_id": doctor.id, "test_ids": [test.id]},
            headers=headers,
        )

        resp = client.get(f"/api/lab/orders?patient_id={patient.id}", headers=headers)
        assert resp.status_code == 200
        assert len(resp.get_json()["data"]) == 1


class TestSampleCollectionEquipmentAndResultRoutes:
    def _order(self, client, clinic, make_patient, make_lab_test, make_authenticated_staff):
        doctor, doctor_headers = make_authenticated_staff(clinic, Role.DOCTOR)
        patient = make_patient(clinic)
        test = make_lab_test(clinic)

        resp = client.post(
            "/api/lab/orders",
            json={"clinic_id": clinic.id, "patient_id": patient.id, "ordered_by_id": doctor.id, "test_ids": [test.id]},
            headers=doctor_headers,
        )
        return resp.get_json()["data"]

    def test_collect_sample_requires_lab_technician(
        self, client, clinic, make_patient, make_lab_test, make_authenticated_staff, assert_forbidden
    ):
        order = self._order(client, clinic, make_patient, make_lab_test, make_authenticated_staff)
        doctor_headers = _headers(make_authenticated_staff, clinic, Role.DOCTOR)

        resp = client.post(
            f"/api/lab/orders/{order['id']}/collect-sample", json={}, headers=doctor_headers
        )
        assert_forbidden(resp)

    def test_collect_sample_and_link_equipment_and_enter_result(
        self, client, clinic, make_patient, make_lab_test, make_authenticated_staff
    ):
        order = self._order(client, clinic, make_patient, make_lab_test, make_authenticated_staff)
        tech_headers = _headers(make_authenticated_staff, clinic, Role.LAB_TECHNICIAN)

        collect_resp = client.post(
            f"/api/lab/orders/{order['id']}/collect-sample", json={}, headers=tech_headers
        )
        assert collect_resp.status_code == 200
        assert collect_resp.get_json()["data"]["status"] == "sample_collected"

        equip_resp = client.post(
            f"/api/lab/orders/{order['id']}/equipment",
            json={"equipment_reference_id": "EQ-1"},
            headers=tech_headers,
        )
        assert equip_resp.status_code == 200
        assert equip_resp.get_json()["data"]["status"] == "in_progress"

        item_id = order["items"][0]["id"]
        result_resp = client.post(
            f"/api/lab/order-items/{item_id}/result",
            json={"result_value": "7.2"},
            headers=tech_headers,
        )
        assert result_resp.status_code == 200
        assert result_resp.get_json()["data"]["result_value"] == "7.2"

    def test_cancel_order(self, client, clinic, make_patient, make_lab_test, make_authenticated_staff):
        order = self._order(client, clinic, make_patient, make_lab_test, make_authenticated_staff)
        doctor_headers = _headers(make_authenticated_staff, clinic, Role.DOCTOR)

        resp = client.post(
            f"/api/lab/orders/{order['id']}/cancel", json={"reason": "No longer needed"}, headers=doctor_headers
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["status"] == "cancelled"