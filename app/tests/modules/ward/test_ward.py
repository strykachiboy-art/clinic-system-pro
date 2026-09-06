from app.core.enums.role_enums import Role
from app.core.enums.ward_enums import BedStatus


def _headers(make_authenticated_staff, clinic, role=Role.NURSE):
    _, h = make_authenticated_staff(clinic, role)
    return h


class TestWardRoutes:
    def test_create_ward_requires_management_role(self, client, clinic, make_authenticated_staff, assert_forbidden):
        headers = _headers(make_authenticated_staff, clinic, Role.RECEPTIONIST)
        resp = client.post("/api/wards", json={"clinic_id": clinic.id, "name": "ICU"}, headers=headers)
        assert_forbidden(resp)

    def test_create_ward_happy_path(self, client, clinic, make_authenticated_staff):
        headers = _headers(make_authenticated_staff, clinic)
        resp = client.post(
            "/api/wards", json={"clinic_id": clinic.id, "name": "ICU", "capacity": 5}, headers=headers
        )
        assert resp.status_code == 201
        assert resp.get_json()["data"]["name"] == "ICU"

    def test_get_ward_not_found(self, client, clinic, make_authenticated_staff, assert_domain_error):
        headers = _headers(make_authenticated_staff, clinic)
        resp = client.get("/api/wards/999999", headers=headers)
        assert_domain_error(resp, 404)

    def test_ward_occupancy(self, client, clinic, make_ward, make_bed, make_authenticated_staff):
        ward = make_ward(clinic, capacity=2)
        make_bed(ward, status=BedStatus.OCCUPIED)
        make_bed(ward, status=BedStatus.AVAILABLE)
        headers = _headers(make_authenticated_staff, clinic)

        resp = client.get(f"/api/wards/{ward.id}/occupancy", headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["occupied"] == 1


class TestBedRoutes:
    def test_add_bed_happy_path(self, client, clinic, make_ward, make_authenticated_staff):
        ward = make_ward(clinic, capacity=3)
        headers = _headers(make_authenticated_staff, clinic)

        resp = client.post(f"/api/wards/{ward.id}/beds", json={"bed_number": "A1"}, headers=headers)
        assert resp.status_code == 201
        assert resp.get_json()["data"]["status"] == "available"

    def test_add_bed_over_capacity_maps_to_409(self, client, clinic, make_ward, make_bed, make_authenticated_staff, assert_domain_error):
        ward = make_ward(clinic, capacity=1)
        make_bed(ward)
        headers = _headers(make_authenticated_staff, clinic)

        resp = client.post(f"/api/wards/{ward.id}/beds", json={"bed_number": "extra"}, headers=headers)
        assert_domain_error(resp, 409)

    def test_set_bed_maintenance(self, client, clinic, make_ward, make_bed, make_authenticated_staff):
        ward = make_ward(clinic)
        bed = make_bed(ward)
        headers = _headers(make_authenticated_staff, clinic)

        resp = client.patch(
            f"/api/wards/beds/{bed.id}/maintenance", json={"under_maintenance": True}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["status"] == "maintenance"


class TestReservationRoutes:
    def test_reserve_and_cancel(self, client, clinic, make_ward, make_bed, make_patient, make_staff, make_authenticated_staff):
        ward = make_ward(clinic)
        bed = make_bed(ward)
        patient = make_patient(clinic)
        reserver = make_staff(clinic)
        headers = _headers(make_authenticated_staff, clinic)

        resp = client.post(
            "/api/wards/reservations",
            json={"patient_id": patient.id, "bed_id": bed.id, "reserved_by_id": reserver.id},
            headers=headers,
        )
        assert resp.status_code == 201
        reservation_id = resp.get_json()["data"]["id"]

        cancel_resp = client.post(
            f"/api/wards/reservations/{reservation_id}/cancel", json={}, headers=headers
        )
        assert cancel_resp.status_code == 200
        assert cancel_resp.get_json()["data"]["status"] == "cancelled"

    def test_admit_from_reservation(self, client, clinic, make_ward, make_bed, make_patient, make_staff, make_authenticated_staff):
        ward = make_ward(clinic)
        bed = make_bed(ward)
        patient = make_patient(clinic)
        reserver = make_staff(clinic)
        headers = _headers(make_authenticated_staff, clinic)

        reserve_resp = client.post(
            "/api/wards/reservations",
            json={"patient_id": patient.id, "bed_id": bed.id, "reserved_by_id": reserver.id},
            headers=headers,
        )
        reservation_id = reserve_resp.get_json()["data"]["id"]

        admit_resp = client.post(
            f"/api/wards/reservations/{reservation_id}/admit",
            json={"admitted_by_id": reserver.id},
            headers=headers,
        )
        assert admit_resp.status_code == 201
        assert admit_resp.get_json()["data"]["status"] == "admitted"

    def test_get_active_reservation_for_patient_null_when_none(self, client, clinic, make_patient, make_authenticated_staff):
        patient = make_patient(clinic)
        headers = _headers(make_authenticated_staff, clinic)

        resp = client.get(f"/api/wards/patients/{patient.id}/reservation", headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()["data"] is None


class TestAdmissionRoutes:
    def test_admit_transfer_discharge_flow(
        self, client, clinic, make_ward, make_bed, make_patient, make_staff, make_authenticated_staff
    ):
        ward = make_ward(clinic)
        bed1 = make_bed(ward)
        bed2 = make_bed(ward)
        patient = make_patient(clinic)
        admitter = make_staff(clinic)
        headers = _headers(make_authenticated_staff, clinic)

        admit_resp = client.post(
            "/api/wards/admissions",
            json={"patient_id": patient.id, "bed_id": bed1.id, "admitted_by_id": admitter.id},
            headers=headers,
        )
        assert admit_resp.status_code == 201
        admission_id = admit_resp.get_json()["data"]["id"]

        transfer_resp = client.post(
            f"/api/wards/admissions/{admission_id}/transfer",
            json={"to_bed_id": bed2.id},
            headers=headers,
        )
        assert transfer_resp.status_code == 200
        assert transfer_resp.get_json()["data"]["to_bed_id"] == bed2.id

        discharge_resp = client.post(
            f"/api/wards/admissions/{admission_id}/discharge",
            json={"reason": "Recovered"},
            headers=headers,
        )
        assert discharge_resp.status_code == 200
        assert discharge_resp.get_json()["data"]["status"] == "discharged"

    def test_admit_patient_requires_clinical_role(self, client, clinic, make_ward, make_bed, make_patient, make_staff, make_authenticated_staff, assert_forbidden):
        ward = make_ward(clinic)
        bed = make_bed(ward)
        patient = make_patient(clinic)
        admitter = make_staff(clinic)
        headers = _headers(make_authenticated_staff, clinic, Role.RECEPTIONIST)

        resp = client.post(
            "/api/wards/admissions",
            json={"patient_id": patient.id, "bed_id": bed.id, "admitted_by_id": admitter.id},
            headers=headers,
        )
        assert_forbidden(resp)

    def test_list_patient_admissions(self, client, clinic, make_ward, make_bed, make_patient, make_staff, make_authenticated_staff):
        ward = make_ward(clinic)
        bed = make_bed(ward)
        patient = make_patient(clinic)
        admitter = make_staff(clinic)
        headers = _headers(make_authenticated_staff, clinic)

        client.post(
            "/api/wards/admissions",
            json={"patient_id": patient.id, "bed_id": bed.id, "admitted_by_id": admitter.id},
            headers=headers,
        )

        resp = client.get(f"/api/wards/patients/{patient.id}/admissions", headers=headers)
        assert resp.status_code == 200
        assert len(resp.get_json()["data"]) == 1