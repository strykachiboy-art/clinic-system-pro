
from __future__ import annotations

from app.core.audit.models.audit_model import AuditLog
from app.core.enums.audit_enums import AuditAction
from app.core.enums.feedback_enums import (
    FeedbackCategory,
    FeedbackPriority,
    FeedbackStatus,
    FeedbackType,
)
from app.core.enums.role_enums import Role
from app.modules.feedback.models.feedback_comment_model import (
    FeedbackComment,
)
from app.modules.feedback.models.feedback_model import Feedback


def test_feedback_core_e2e(
    client,
    db,
    clinic,
    make_clinic,
    make_user,
    make_staff,
    make_patient,
    e2e_login,
):
    admin = make_user(
        clinic=clinic,
        role=Role.ADMIN,
        email="e2e-g9-feedback-admin@test.com",
    )

    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
        user_overrides={
            "email": "e2e-g9-feedback-doctor@test.com",
        },
    )

    patient = make_patient(
        clinic,
        first_name="Gate",
        last_name="Nine",
    )

    admin_login = e2e_login(
        "e2e-g9-feedback-admin@test.com",
    )

    staff_login = e2e_login(
        "e2e-g9-feedback-doctor@test.com",
    )

    admin_headers = {
        "Authorization": (
            f"Bearer {admin_login['access_token']}"
        ),
    }

    staff_headers = {
        "Authorization": (
            f"Bearer {staff_login['access_token']}"
        ),
    }

    # ================================================================
    # FEEDBACK CREATE
    # ================================================================

    create_response = client.post(
        "/api/v1/feedback",
        json={
            "feedback_type": FeedbackType.BUG_REPORT.value,
            "category": FeedbackCategory.CLINICAL_WORKFLOW.value,
            "subject": "Gate 9 feedback E2E",
            "message": (
                "Clinical workflow feedback integration test."
            ),
            "target_module": "patient",
            "target_resource_type": "patient",
            "target_resource_id": patient.id,
        },
        headers=staff_headers,
    )

    assert create_response.status_code == 201, (
        create_response.get_json()
    )

    create_body = create_response.get_json()

    assert create_body["success"] is True
    assert create_body["data"]["clinic_id"] == clinic.id
    assert (
        create_body["data"]["submitted_by_user_id"]
        == staff.user.id
    )
    assert create_body["data"]["status"] == (
        FeedbackStatus.OPEN.value
    )
    assert create_body["data"]["priority"] == (
        FeedbackPriority.NORMAL.value
    )
    assert create_body["data"]["target_module"] == "patient"
    assert create_body["data"]["target_resource_type"] == "patient"
    assert create_body["data"]["target_resource_id"] == patient.id

    feedback_id = create_body["data"]["id"]

    persisted_feedback = db.session.get(
        Feedback,
        feedback_id,
    )

    assert persisted_feedback is not None
    assert persisted_feedback.clinic_id == clinic.id
    assert (
        persisted_feedback.submitted_by_user_id
        == staff.user.id
    )

    # ================================================================
    # GET FEEDBACK
    # ================================================================

    get_response = client.get(
        f"/api/v1/feedback/{feedback_id}",
        headers=staff_headers,
    )

    assert get_response.status_code == 200, (
        get_response.get_json()
    )

    get_body = get_response.get_json()

    assert get_body["success"] is True
    assert get_body["data"]["id"] == feedback_id
    assert get_body["data"]["clinic_id"] == clinic.id

    # ================================================================
    # STAFF COMMENT
    # ================================================================

    comment_response = client.post(
        f"/api/v1/feedback/{feedback_id}/comments",
        json={
            "body": "Gate 9 staff comment.",
        },
        headers=staff_headers,
    )

    assert comment_response.status_code == 201, (
        comment_response.get_json()
    )

    comment_body = comment_response.get_json()

    assert comment_body["success"] is True
    assert (
        comment_body["data"]["feedback_id"]
        == feedback_id
    )
    assert (
        comment_body["data"]["author_user_id"]
        == staff.user.id
    )

    staff_comment_id = comment_body["data"]["id"]

    # ================================================================
    # ADMIN COMMENT
    # ================================================================

    admin_comment_response = client.post(
        f"/api/v1/feedback/{feedback_id}/comments",
        json={
            "body": "Gate 9 administrative response.",
        },
        headers=admin_headers,
    )

    assert admin_comment_response.status_code == 201, (
        admin_comment_response.get_json()
    )

    admin_comment_body = admin_comment_response.get_json()

    assert admin_comment_body["success"] is True
    assert (
        admin_comment_body["data"]["author_user_id"]
        == admin.id
    )

    # ================================================================
    # LIST COMMENTS
    # ================================================================

    comments_response = client.get(
        f"/api/v1/feedback/{feedback_id}/comments",
        headers=staff_headers,
    )

    assert comments_response.status_code == 200, (
        comments_response.get_json()
    )

    comments_body = comments_response.get_json()

    assert comments_body["success"] is True
    assert comments_body["data"]["total"] == 2

    comment_ids = {
        item["id"]
        for item in comments_body["data"]["items"]
    }

    assert staff_comment_id in comment_ids
    assert admin_comment_body["data"]["id"] in comment_ids

    # ================================================================
    # ADMIN MANAGE ? ASSIGN + TRIAGE
    # ================================================================

    manage_response = client.patch(
        f"/api/v1/feedback/{feedback_id}",
        json={
            "priority": FeedbackPriority.HIGH.value,
            "assigned_to_user_id": staff.user.id,
            "status": FeedbackStatus.TRIAGED.value,
        },
        headers=admin_headers,
    )

    assert manage_response.status_code == 200, (
        manage_response.get_json()
    )

    manage_body = manage_response.get_json()

    assert manage_body["success"] is True
    assert manage_body["data"]["clinic_id"] == clinic.id
    assert manage_body["data"]["priority"] == (
        FeedbackPriority.HIGH.value
    )
    assert manage_body["data"]["assigned_to_user_id"] == (
        staff.user.id
    )
    assert manage_body["data"]["status"] == (
        FeedbackStatus.TRIAGED.value
    )

    # ================================================================
    # TRIAGED -> IN PROGRESS
    # ================================================================

    in_progress_response = client.patch(
        f"/api/v1/feedback/{feedback_id}",
        json={
            "status": FeedbackStatus.IN_PROGRESS.value,
        },
        headers=admin_headers,
    )

    assert in_progress_response.status_code == 200, (
        in_progress_response.get_json()
    )

    assert (
        in_progress_response.get_json()["data"]["status"]
        == FeedbackStatus.IN_PROGRESS.value
    )

    # ================================================================
    # RESOLVE
    # ================================================================

    resolve_response = client.post(
        f"/api/v1/feedback/{feedback_id}/resolve",
        json={
            "resolution_note": (
                "Gate 9 issue resolved successfully."
            ),
        },
        headers=admin_headers,
    )

    assert resolve_response.status_code == 200, (
        resolve_response.get_json()
    )

    resolve_body = resolve_response.get_json()

    assert resolve_body["success"] is True
    assert resolve_body["data"]["status"] == (
        FeedbackStatus.RESOLVED.value
    )
    assert resolve_body["data"]["resolution_note"] == (
        "Gate 9 issue resolved successfully."
    )
    assert resolve_body["data"]["resolved_at"] is not None

    # ================================================================
    # CLOSE
    # ================================================================

    close_response = client.post(
        f"/api/v1/feedback/{feedback_id}/close",
        headers=admin_headers,
    )

    assert close_response.status_code == 200, (
        close_response.get_json()
    )

    close_body = close_response.get_json()

    assert close_body["success"] is True
    assert close_body["data"]["status"] == (
        FeedbackStatus.CLOSED.value
    )
    assert close_body["data"]["closed_at"] is not None

    # ================================================================
    # REOPEN
    # ================================================================

    reopen_response = client.post(
        f"/api/v1/feedback/{feedback_id}/reopen",
        headers=admin_headers,
    )

    assert reopen_response.status_code == 200, (
        reopen_response.get_json()
    )

    reopen_body = reopen_response.get_json()

    assert reopen_body["success"] is True
    assert reopen_body["data"]["status"] == (
        FeedbackStatus.REOPENED.value
    )
    assert reopen_body["data"]["resolution_note"] is None
    assert reopen_body["data"]["resolved_at"] is None
    assert reopen_body["data"]["closed_at"] is None

    # ================================================================
    # FINAL DATABASE STATE
    # ================================================================

    db.session.expire_all()

    final_feedback = db.session.get(
        Feedback,
        feedback_id,
    )

    assert final_feedback is not None
    assert final_feedback.clinic_id == clinic.id
    assert final_feedback.status is FeedbackStatus.REOPENED
    assert final_feedback.priority is FeedbackPriority.HIGH
    assert final_feedback.assigned_to_user_id == staff.user.id

    comments = (
        db.session.execute(
            db.select(FeedbackComment)
            .where(
                FeedbackComment.feedback_id
                == feedback_id,
            )
            .order_by(
                FeedbackComment.id.asc(),
            )
        )
        .scalars()
        .all()
    )

    assert len(comments) == 2

    # ================================================================
    # AUDIT ? FEEDBACK
    # ================================================================

    feedback_audits = (
        db.session.execute(
            db.select(AuditLog)
            .where(
                AuditLog.entity_type == "Feedback",
                AuditLog.entity_id == feedback_id,
            )
            .order_by(
                AuditLog.id.asc(),
            )
        )
        .scalars()
        .all()
    )

    assert feedback_audits

    assert any(
        row.action is AuditAction.CREATE
        and row.user_id == staff.user.id
        for row in feedback_audits
    )

    assert any(
        row.action is AuditAction.STATUS_CHANGE
        and row.user_id == admin.id
        for row in feedback_audits
    )

    assert all(
        row.clinic_id == clinic.id
        for row in feedback_audits
    )

    # ================================================================
    # AUDIT ? COMMENTS
    # ================================================================

    comment_audits = (
        db.session.execute(
            db.select(AuditLog)
            .where(
                AuditLog.entity_type == "FeedbackComment",
                AuditLog.entity_id.in_(
                    [comment.id for comment in comments]
                ),
            )
            .order_by(
                AuditLog.id.asc(),
            )
        )
        .scalars()
        .all()
    )

    assert len(comment_audits) >= 2

    assert all(
        row.clinic_id == clinic.id
        for row in comment_audits
    )

    assert any(
        row.action is AuditAction.CREATE
        and row.user_id == staff.user.id
        for row in comment_audits
    )

    assert any(
        row.action is AuditAction.CREATE
        and row.user_id == admin.id
        for row in comment_audits
    )

    # ================================================================
    # SECOND CLINIC
    # ================================================================

    second_clinic = make_clinic(
        name="Gate 9 Feedback Other Clinic",
    )

    second_admin = make_user(
        clinic=second_clinic,
        role=Role.ADMIN,
        email="e2e-g9-feedback-other-admin@test.com",
    )

    second_patient = make_patient(
        second_clinic,
        first_name="Foreign",
        last_name="Feedback",
    )

    second_admin_login = e2e_login(
        "e2e-g9-feedback-other-admin@test.com",
    )

    second_admin_headers = {
        "Authorization": (
            f"Bearer {second_admin_login['access_token']}"
        ),
    }

    # ================================================================
    # CROSS-CLINIC READ MUST FAIL
    # ================================================================

    foreign_get_response = client.get(
        f"/api/v1/feedback/{feedback_id}",
        headers=second_admin_headers,
    )

    assert foreign_get_response.status_code == 404

    # ================================================================
    # CROSS-CLINIC COMMENT READ MUST FAIL
    # ================================================================

    foreign_comment_response = client.get(
        f"/api/v1/feedback/{feedback_id}/comments/{staff_comment_id}",
        headers=second_admin_headers,
    )

    assert foreign_comment_response.status_code == 404

    # ================================================================
    # CROSS-CLINIC TARGET CREATION MUST FAIL
    # ================================================================

    foreign_target_response = client.post(
        "/api/v1/feedback",
        json={
            "feedback_type": FeedbackType.BUG_REPORT.value,
            "category": FeedbackCategory.SECURITY.value,
            "subject": "Cross clinic target attempt",
            "message": "This target must be rejected.",
            "target_module": "patient",
            "target_resource_type": "patient",
            "target_resource_id": second_patient.id,
        },
        headers=staff_headers,
    )

    assert foreign_target_response.status_code == 404

    print(
        "PHASE8_E2E_GATE9_FEEDBACK_CORE=PASS"
    )
