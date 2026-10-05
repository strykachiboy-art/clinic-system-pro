from __future__ import annotations

from app.core.audit.models.audit_model import AuditLog
from app.core.enums.ai_enums import (
    AIApprovalStatus,
    AIFeature,
    AIRiskLevel,
)
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role
from app.modules.ai.models.ai_model import AILog


def _headers(login: dict) -> dict[str, str]:
    return {
        "Authorization": (
            f"Bearer {login['access_token']}"
        ),
    }


def _latest_ai_log(
    db,
    *,
    clinic_id: int,
    user_id: int,
    feature: AIFeature,
):
    return (
        db.session.execute(
            db.select(AILog)
            .where(
                AILog.clinic_id == clinic_id,
                AILog.user_id == user_id,
                AILog.feature_used == feature,
            )
            .order_by(
                AILog.id.desc(),
            )
        )
        .scalars()
        .first()
    )


def _audit_rows(
    db,
    *,
    entity_id: int,
):
    return (
        db.session.execute(
            db.select(AuditLog)
            .where(
                AuditLog.entity_type == "AILog",
                AuditLog.entity_id == entity_id,
            )
            .order_by(
                AuditLog.id.asc(),
            )
        )
        .scalars()
        .all()
    )


def _assert_ai_audit(
    rows,
    *,
    clinic_id: int,
    user_id: int,
    ip_address: str,
):
    assert rows

    owner_rows = [
        row
        for row in rows
        if (
            row.clinic_id == clinic_id
            and row.user_id == user_id
            and row.action is AuditAction.CREATE
        )
    ]

    assert owner_rows

    audit = owner_rows[-1]

    assert audit.ip_address == ip_address
    assert audit.new_value is not None
    assert "feature" in audit.new_value
    assert "risk_level" in audit.new_value
    assert "approval_status" in audit.new_value
    assert "credits_used" in audit.new_value
    assert "generated_by_system" in audit.new_value

    assert "input_data" not in audit.new_value
    assert "output_data" not in audit.new_value


def test_ai_external_integration_e2e(
    client,
    db,
    clinic,
    make_clinic,
    make_staff,
    make_patient,
    e2e_login,
    mock_ai_provider,
    monkeypatch,
):
    # ================================================================
    # PRIMARY ACTOR + PATIENT
    # ================================================================

    actor_staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
        user_overrides={
            "email": "e2e-g15-ai-doctor@test.com",
        },
    )

    actor = actor_staff.user

    patient = make_patient(
        clinic,
        first_name="AI",
        last_name="E2E",
        patient_number="MRN-G15-AI",
    )

    login = e2e_login(
        "e2e-g15-ai-doctor@test.com",
    )

    assert login["user_id"] == actor.id
    assert login["role"] == Role.DOCTOR.value

    headers = _headers(login)

    # The existing test fixture replaces the OpenAI call with a
    # deterministic provider boundary. The application still takes
    # the real configured provider path.
    monkeypatch.setitem(
        clinic.__dict__,
        "ai_credits",
        clinic.ai_credits,
    )

    starting_credits = clinic.ai_credits

    assert starting_credits >= 4

    ip_address = "203.0.113.15"

    # ================================================================
    # DRUG INTERACTION CHECK
    # HTTP -> ROUTE -> SERVICE -> PROVIDER -> AILOG -> AUDIT
    # ================================================================

    mock_ai_provider.set_response(
        {
            "summary": (
                "No clinically significant interaction found."
            ),
            "interactions": [],
            "recommendations": [
                "Continue routine monitoring.",
            ],
        }
    )

    drug_response = client.post(
        "/api/v1/ai/drug-interactions",
        json={
            "patient_id": patient.id,
            "drug_names": [
                "Aspirin",
                "Warfarin",
            ],
        },
        headers=headers,
        environ_base={
            "REMOTE_ADDR": ip_address,
        },
    )

    assert drug_response.status_code == 200, (
        drug_response.get_json()
    )

    drug_body = drug_response.get_json()

    assert drug_body["success"] is True
    assert drug_body["data"]["summary"] == (
        "No clinically significant interaction found."
    )

    assert mock_ai_provider.last_call is not None
    assert mock_ai_provider.last_call["feature"] is (
        AIFeature.DRUG_INTERACTION_CHECK
    )
    assert mock_ai_provider.last_call["payload"] == {
        "drug_names": [
            "Aspirin",
            "Warfarin",
        ],
    }

    db.session.refresh(clinic)

    assert clinic.ai_credits == (
        starting_credits - 1
    )
    assert clinic.ai_requests_this_month == 1

    drug_log = _latest_ai_log(
        db,
        clinic_id=clinic.id,
        user_id=actor.id,
        feature=AIFeature.DRUG_INTERACTION_CHECK,
    )

    assert drug_log is not None
    assert drug_log.clinic_id == clinic.id
    assert drug_log.patient_id == patient.id
    assert drug_log.user_id == actor.id
    assert drug_log.feature_used is (
        AIFeature.DRUG_INTERACTION_CHECK
    )
    assert drug_log.risk_level is AIRiskLevel.MEDIUM
    assert drug_log.model == "gpt-4o-mini"
    assert drug_log.input_context_version == "v1"
    assert drug_log.generated_by_system is True
    assert drug_log.approval_status is (
        AIApprovalStatus.PENDING
    )
    assert drug_log.credits_used == 1
    assert drug_log.input_data == {
        "drug_names": [
            "Aspirin",
            "Warfarin",
        ],
    }
    assert drug_log.output_data["recommendations"] == [
        "Continue routine monitoring.",
    ]

    _assert_ai_audit(
        _audit_rows(
            db,
            entity_id=drug_log.id,
        ),
        clinic_id=clinic.id,
        user_id=actor.id,
        ip_address=ip_address,
    )

    # ================================================================
    # TRIAGE ASSISTANT
    # ================================================================

    mock_ai_provider.set_response(
        {
            "summary": (
                "Patient requires prompt clinical assessment."
            ),
            "risk_score": "high",
            "recommendation": (
                "Arrange prompt clinical review."
            ),
        }
    )

    triage_response = client.post(
        "/api/v1/ai/triage",
        json={
            "patient_id": patient.id,
            "symptoms": "High fever and persistent cough",
            "vitals": {
                "temperature": 39.1,
                "heart_rate": 104,
            },
        },
        headers=headers,
        environ_base={
            "REMOTE_ADDR": ip_address,
        },
    )

    assert triage_response.status_code == 200, (
        triage_response.get_json()
    )

    triage_body = triage_response.get_json()

    assert triage_body["success"] is True
    assert triage_body["data"]["risk_score"] == "high"

    assert mock_ai_provider.last_call["feature"] is (
        AIFeature.TRIAGE_ASSISTANT
    )
    assert mock_ai_provider.last_call["payload"] == {
        "symptoms": (
            "High fever and persistent cough"
        ),
        "vitals": {
            "temperature": 39.1,
            "heart_rate": 104,
        },
    }

    db.session.refresh(clinic)

    assert clinic.ai_credits == (
        starting_credits - 2
    )
    assert clinic.ai_requests_this_month == 2

    triage_log = _latest_ai_log(
        db,
        clinic_id=clinic.id,
        user_id=actor.id,
        feature=AIFeature.TRIAGE_ASSISTANT,
    )

    assert triage_log is not None
    assert triage_log.patient_id == patient.id
    assert triage_log.user_id == actor.id
    assert triage_log.feature_used is (
        AIFeature.TRIAGE_ASSISTANT
    )
    assert triage_log.risk_level is AIRiskLevel.HIGH
    assert triage_log.approval_status is (
        AIApprovalStatus.PENDING
    )
    assert triage_log.credits_used == 1
    assert triage_log.output_data["risk_score"] == "high"

    _assert_ai_audit(
        _audit_rows(
            db,
            entity_id=triage_log.id,
        ),
        clinic_id=clinic.id,
        user_id=actor.id,
        ip_address=ip_address,
    )

    # ================================================================
    # LAB RESULT INTERPRETER
    # ================================================================

    mock_ai_provider.set_response(
        {
            "summary": (
                "Laboratory results reviewed."
            ),
            "interpretation": (
                "Results require clinical correlation."
            ),
            "abnormal_findings": [
                "Hemoglobin is below the configured reference range."
            ],
            "recommendations": [
                "Review results with the treating clinician.",
            ],
        }
    )

    lab_response = client.post(
        "/api/v1/ai/lab-results/interpret",
        json={
            "patient_id": patient.id,
            "result_data": {
                "hemoglobin": 10.2,
                "wbc": 7.1,
            },
        },
        headers=headers,
        environ_base={
            "REMOTE_ADDR": ip_address,
        },
    )

    assert lab_response.status_code == 200, (
        lab_response.get_json()
    )

    lab_body = lab_response.get_json()

    assert lab_body["success"] is True
    assert lab_body["data"]["summary"] == (
        "Laboratory results reviewed."
    )

    assert mock_ai_provider.last_call["feature"] is (
        AIFeature.LAB_RESULT_INTERPRETER
    )
    assert mock_ai_provider.last_call["payload"] == {
        "result_data": {
            "hemoglobin": 10.2,
            "wbc": 7.1,
        },
        "lab_order_id": None,
    }

    db.session.refresh(clinic)

    assert clinic.ai_credits == (
        starting_credits - 3
    )
    assert clinic.ai_requests_this_month == 3

    lab_log = _latest_ai_log(
        db,
        clinic_id=clinic.id,
        user_id=actor.id,
        feature=AIFeature.LAB_RESULT_INTERPRETER,
    )

    assert lab_log is not None
    assert lab_log.patient_id == patient.id
    assert lab_log.user_id == actor.id
    assert lab_log.feature_used is (
        AIFeature.LAB_RESULT_INTERPRETER
    )
    assert lab_log.risk_level is AIRiskLevel.MEDIUM
    assert lab_log.approval_status is (
        AIApprovalStatus.PENDING
    )
    assert lab_log.credits_used == 1
    assert lab_log.input_data["result_data"] == {
        "hemoglobin": 10.2,
        "wbc": 7.1,
    }

    _assert_ai_audit(
        _audit_rows(
            db,
            entity_id=lab_log.id,
        ),
        clinic_id=clinic.id,
        user_id=actor.id,
        ip_address=ip_address,
    )

    # ================================================================
    # PROVIDER RESPONSE VALIDATION MUST ROLLBACK
    # ================================================================

    logs_before_invalid = (
        db.session.execute(
            db.select(AILog)
            .where(
                AILog.clinic_id == clinic.id,
            )
        )
        .scalars()
        .all()
    )

    credits_before_invalid = clinic.ai_credits

    mock_ai_provider.set_response(
        {
            "summary": "Invalid provider response",
            "unexpected": "blocked",
        }
    )

    invalid_response = client.post(
        "/api/v1/ai/drug-interactions",
        json={
            "patient_id": patient.id,
            "drug_names": [
                "Aspirin",
                "Ibuprofen",
            ],
        },
        headers=headers,
        environ_base={
            "REMOTE_ADDR": ip_address,
        },
    )

    assert invalid_response.status_code == 422

    invalid_body = invalid_response.get_json()

    assert invalid_body["success"] is False
    assert invalid_body["error"] == (
        "AI provider returned invalid "
        "drug_interaction_check response"
    )

    db.session.refresh(clinic)

    assert clinic.ai_credits == (
        credits_before_invalid
    )
    assert clinic.ai_requests_this_month == 3

    logs_after_invalid = (
        db.session.execute(
            db.select(AILog)
            .where(
                AILog.clinic_id == clinic.id,
            )
        )
        .scalars()
        .all()
    )

    assert len(logs_after_invalid) == (
        len(logs_before_invalid)
    )

    # ================================================================
    # CROSS-CLINIC PATIENT ACCESS MUST FAIL BEFORE AI CONSUMPTION
    # ================================================================

    foreign_clinic = make_clinic(
        name="Gate 15 Foreign AI Clinic",
    )

    foreign_staff = make_staff(
        clinic=foreign_clinic,
        role=Role.DOCTOR,
        user_overrides={
            "email": (
                "e2e-g15-ai-foreign@test.com"
            ),
        },
    )

    foreign_login = e2e_login(
        "e2e-g15-ai-foreign@test.com",
    )

    assert foreign_login["user_id"] == (
        foreign_staff.user.id
    )

    foreign_headers = _headers(
        foreign_login
    )

    foreign_credits_before = (
        foreign_clinic.ai_credits
    )

    foreign_logs_before = (
        db.session.execute(
            db.select(AILog)
            .where(
                AILog.clinic_id == foreign_clinic.id,
            )
        )
        .scalars()
        .all()
    )

    # Reset provider to a valid deterministic response.
    mock_ai_provider.set_response(
        {
            "summary": (
                "Patient requires clinical assessment."
            ),
            "risk_score": "medium",
            "recommendation": (
                "Arrange clinical review."
            ),
        }
    )

    foreign_response = client.post(
        "/api/v1/ai/triage",
        json={
            "patient_id": patient.id,
            "symptoms": "Unauthorized cross-clinic request",
        },
        headers=foreign_headers,
    )

    assert foreign_response.status_code == 422

    foreign_body = foreign_response.get_json()

    assert foreign_body["success"] is False
    assert foreign_body["error"] == (
        "Patient does not belong to the "
        "authenticated clinic"
    )

    db.session.refresh(foreign_clinic)

    assert foreign_clinic.ai_credits == (
        foreign_credits_before
    )
    assert foreign_clinic.ai_requests_this_month == 0

    foreign_logs_after = (
        db.session.execute(
            db.select(AILog)
            .where(
                AILog.clinic_id == foreign_clinic.id,
            )
        )
        .scalars()
        .all()
    )

    assert len(foreign_logs_after) == (
        len(foreign_logs_before)
    )
