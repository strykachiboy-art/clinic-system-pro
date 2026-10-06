from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.enums.hie_enums import HIEFailureClass, HIESubmissionStatus
from app.modules.hie.providers.exceptions import (
    HIEFailClosedError,
    HIEReconciliationRequiredError,
    HIERetryableError,
    HIEUserActionRequiredError,
)
from app.modules.hie.services import hie_service


def make_submission(
    *,
    submission_id=1,
    retry_count=0,
    failure_class=None,
):
    now = datetime.now(timezone.utc)

    return SimpleNamespace(
        id=submission_id,
        status=HIESubmissionStatus.PENDING,
        failure_class=failure_class,
        response_data=None,
        status_code=None,
        external_reference=None,
        error_message=None,
        retry_count=retry_count,
        submitted_at=None,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def no_transaction(monkeypatch):
    monkeypatch.setattr(
        hie_service.db.session,
        "commit",
        lambda: None,
    )
    monkeypatch.setattr(
        hie_service.db.session,
        "rollback",
        lambda: None,
    )


@pytest.mark.parametrize(
    ("error", "expected_class"),
    [
        (
            HIERetryableError("temporary provider failure"),
            HIEFailureClass.RETRYABLE,
        ),
        (
            HIEReconciliationRequiredError("unknown provider outcome"),
            HIEFailureClass.RECONCILIATION_REQUIRED,
        ),
        (
            HIEUserActionRequiredError("provider rejected request"),
            HIEFailureClass.USER_ACTION_REQUIRED,
        ),
        (
            HIEFailClosedError("unsafe provider failure"),
            HIEFailureClass.FAIL_CLOSED,
        ),
        (
            TimeoutError("provider timeout"),
            HIEFailureClass.RETRYABLE,
        ),
        (
            ConnectionError("provider connection failure"),
            HIEFailureClass.RETRYABLE,
        ),
    ],
)
def test_mark_submission_failure_persists_failure_class(
    monkeypatch,
    no_transaction,
    error,
    expected_class,
):
    submission = make_submission(
        submission_id=20,
        retry_count=2,
    )

    monkeypatch.setattr(
        hie_service.db.session,
        "get",
        lambda model, submission_id: submission,
    )

    hie_service._mark_submission_failure(
        20,
        error,
    )

    assert submission.status == HIESubmissionStatus.FAILED
    assert submission.failure_class is expected_class
    assert submission.retry_count == 3
    assert submission.error_message == (
        "HIE provider operation failed"
    )
    assert submission.submitted_at is not None


def test_mark_submission_failure_does_not_leak_provider_error(
    monkeypatch,
    no_transaction,
):
    submission = make_submission(
        submission_id=30,
        retry_count=0,
    )

    monkeypatch.setattr(
        hie_service.db.session,
        "get",
        lambda model, submission_id: submission,
    )

    hie_service._mark_submission_failure(
        30,
        RuntimeError("provider token=SECRET-123"),
    )

    assert submission.failure_class is HIEFailureClass.FAIL_CLOSED
    assert submission.error_message == (
        "HIE provider operation failed"
    )
    assert "SECRET-123" not in (
        submission.error_message or ""
    )


def test_mark_submission_success_clears_failure_class(
    monkeypatch,
    no_transaction,
):
    submission = make_submission(
        submission_id=40,
        retry_count=2,
        failure_class=HIEFailureClass.RETRYABLE,
    )

    monkeypatch.setattr(
        hie_service.db.session,
        "get",
        lambda model, submission_id: submission,
    )

    hie_service._mark_submission_success(
        40,
        {
            "status_code": 200,
            "external_reference": "HIE-40",
        },
    )

    assert submission.status == HIESubmissionStatus.SUCCESS
    assert submission.failure_class is None
    assert submission.external_reference == "HIE-40"