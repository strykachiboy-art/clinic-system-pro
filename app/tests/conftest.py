import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db as _db


# ============================================================================
# APP / DB / CLIENT
# ============================================================================

@pytest.fixture()
def app():
    flask_app = create_app("testing")
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    return _db


# ============================================================================
# AUTH HELPERS
# ============================================================================

@pytest.fixture()
def auth_headers_for(app):
    """
    Factory: auth_headers_for(user, role=None) -> {"Authorization": "Bearer ..."}

    Builds a JWT for `user` with a "role" claim (defaults to
    user.role) — this is the claim role_required() checks. Pass an
    explicit `role=` to deliberately mismatch it against the user's
    real Staff/User role, e.g. to test that role_required rejects a
    token whose claim doesn't match what the route allows.
    """

    def _make(user, role=None):
        claim_role = role.value if role is not None else user.role.value

        with app.test_request_context():
            token = create_access_token(
                identity=str(user.id),
                additional_claims={"role": claim_role},
            )

        return {"Authorization": f"Bearer {token}"}

    return _make


# ============================================================================
# CLINIC
# ============================================================================

@pytest.fixture()
def make_clinic(db):
    """Factory: make_clinic(**overrides) -> Clinic (defaults to ACTIVE)."""
    from app.modules.clinic.models.clinic_model import Clinic

    created = []

    def _make(**overrides):
        overrides.setdefault("name", "Test Clinic")
        overrides.setdefault("ai_credits", 5)
        c = Clinic(**overrides)
        db.session.add(c)
        db.session.commit()
        created.append(c)
        return c

    return _make


@pytest.fixture()
def clinic(make_clinic):
    """A single active clinic — the default most tests need."""
    return make_clinic()


@pytest.fixture()
def suspended_clinic(make_clinic):
    """
    A clinic with status=SUSPENDED. Use this to exercise the
    ensure_clinic_active() guard that most write-path service
    functions call before doing anything — this is the one clean way
    to hit that branch without hand-rolling a Clinic in every test
    that needs it.
    """
    from app.core.enums.clinic_enums import ClinicStatus

    return make_clinic(name="Suspended Clinic", status=ClinicStatus.SUSPENDED)


# ============================================================================
# USER
# ============================================================================

@pytest.fixture()
def make_user(db):
    """Factory: make_user(clinic, role=Role.ADMIN, **overrides) -> User."""
    from app.core.auth.user.models.user_model import User
    from app.core.enums.role_enums import Role

    counter = {"n": 0}

    def _make(clinic, role=Role.ADMIN, is_active=True, password="supersecret", **overrides):
        counter["n"] += 1
        overrides.setdefault("email", f"user{counter['n']}@test.com")

        u = User(
            clinic_id=clinic.id,
            role=role,
            is_active=is_active,
            **overrides,
        )
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        return u

    return _make


@pytest.fixture()
def user(make_user, clinic):
    """A single ADMIN user tied to `clinic` — kept for existing tests."""
    from app.core.enums.role_enums import Role

    return make_user(clinic, role=Role.ADMIN, email="admin@test.com")


# ============================================================================
# STAFF
# ============================================================================

@pytest.fixture()
def make_staff(db, make_user):
    """
    Factory: make_staff(clinic, role=Role.ADMIN, status=StaffStatus.ACTIVE,
                         first_name=..., last_name=..., **overrides) -> Staff

    Creates a matching User + Staff pair in one call. This is
    deliberately the one place that sets up both rows together,
    because several services validate *both*:

        staff.status == ACTIVE
        staff.user.is_active == True
        staff.user.role in <allowed roles for that operation>

    (see e.g. _validate_staff_for_pharmacy in pharmacy_service.py —
    the same shape repeats in inventory, lab, ward, reports, staff
    services). Building a Staff without a properly-active linked User
    is a common way to get a confusing 422 instead of testing what
    you meant to test.
    """
    from app.core.enums.role_enums import Role
    from app.core.enums.staff_enums import StaffStatus
    from app.modules.staff.models.staff_model import Staff

    def _make(
        clinic,
        role=Role.ADMIN,
        status=StaffStatus.ACTIVE,
        first_name="Test",
        last_name="Staff",
        user_is_active=True,
        **overrides,
    ):
        linked_user = make_user(clinic, role=role, is_active=user_is_active)

        staff = Staff(
            clinic_id=clinic.id,
            user_id=linked_user.id,
            first_name=first_name,
            last_name=last_name,
            status=status,
            **overrides,
        )
        db.session.add(staff)
        db.session.commit()
        return staff

    return _make


@pytest.fixture()
def staff(make_staff, clinic):
    """A single ACTIVE, ADMIN-role staff member tied to `clinic`."""
    return make_staff(clinic)


@pytest.fixture()
def make_authenticated_staff(make_staff, auth_headers_for):
    """
    Factory: make_authenticated_staff(clinic, role) -> (staff, headers)

    The shortcut most module tests actually want: one call gets you a
    Staff row with the right role AND a bearer token whose "role"
    claim matches it, ready to pass straight to client.post(...).
    """

    def _make(clinic, role, **overrides):
        staff_obj = make_staff(clinic, role=role, **overrides)
        headers = auth_headers_for(staff_obj.user, role=role)
        return staff_obj, headers

    return _make


# ============================================================================
# PATIENT
# ============================================================================

@pytest.fixture()
def make_patient(db):
    """
    Factory: make_patient(clinic, **overrides) -> Patient

    Sets patient_number directly rather than going through
    create_patient() in patient_service.py (which auto-generates it
    via generate_tracking_code) — fine for a raw fixture, but if a
    test is specifically exercising patient creation/number
    generation, call the service function instead of this fixture.
    """
    from app.modules.patient.models.patient_model import Patient

    counter = {"n": 0}

    def _make(clinic, **overrides):
        counter["n"] += 1
        overrides.setdefault("first_name", "Jane")
        overrides.setdefault("last_name", "Doe")
        overrides.setdefault("patient_number", f"MRN-{counter['n']}")

        p = Patient(clinic_id=clinic.id, **overrides)
        db.session.add(p)
        db.session.commit()
        return p

    return _make


@pytest.fixture()
def patient(make_patient, clinic):
    return make_patient(clinic)


# ============================================================================
# AI PROVIDER (for AI-module tests only)
# ============================================================================

@pytest.fixture()
def mock_ai_provider(monkeypatch):
    """
    Patches ai_service._call_openai so AI routes don't hit the real
    OpenAI API in tests. Returns a small controller:

        mock_ai_provider.set_response({"risk_score": "low"})
        # ... hit the route ...
        assert mock_ai_provider.last_call["feature"] == AIFeature.TRIAGE_ASSISTANT

    Service-level tests that call assist_triage()/check_drug_interactions()
    directly don't need this — pass `provider=` to those functions
    instead, since that param exists precisely for this.
    """
    import app.modules.ai.services.ai_service as ai_service

    state = {"response": {}, "last_call": None}

    def _fake_call_openai(feature, payload):
        state["last_call"] = {"feature": feature, "payload": payload}
        return state["response"]

    monkeypatch.setattr(ai_service, "_call_openai", _fake_call_openai)

    class _Controller:
        def set_response(self, value):
            state["response"] = value

        @property
        def last_call(self):
            return state["last_call"]

    return _Controller()


# ============================================================================
# RESPONSE ASSERTION HELPERS
# ============================================================================
#
# The app does not have one error response shape — it has three,
# depending on where a request gets rejected. Verified against the
# real routes (not assumed from error_handlers.py alone):
#
#   1. Business-logic errors (NotFoundError, ValidationError,
#      ConflictError, InsufficientCreditsError — raised from service
#      functions) -> {"success": False, "error": "...", "details": [...]?}
#      via app/core/error_handlers.py. This is the shape you'll hit
#      constantly in module tests (bad input, missing entity, etc).
#
#   2. role_required() rejecting a wrong/insufficient role
#      -> {"error": "Insufficient permissions"}, no "success" key at
#      all. Set directly in app/core/utils/decorators.py, bypassing
#      error_handlers.py entirely.
#
#   3. Missing/invalid/expired JWT (flask-jwt-extended itself, before
#      your view function even runs) -> {"msg": "..."}. Different key
#      name, no "success", no "error". This is flask-jwt-extended's
#      own default error handler, registered separately from the
#      app's error_handlers.py.
#
# Using the wrong helper against the wrong failure mode is a
# guaranteed silent-KeyError trap, so there are three helpers, not one.

@pytest.fixture()
def assert_domain_error():
    """
    assert_domain_error(response, status_code) -> parsed body

    For errors raised from service-layer code (NotFoundError=404,
    ValidationError=422, ConflictError=409, InsufficientCreditsError=402).
    """

    def _assert(response, status_code):
        assert response.status_code == status_code, response.get_json()
        body = response.get_json()
        assert body["success"] is False
        assert "error" in body
        return body

    return _assert


@pytest.fixture()
def assert_forbidden():
    """assert_forbidden(response) -> parsed body, for role_required()'s 403."""

    def _assert(response):
        assert response.status_code == 403, response.get_json()
        body = response.get_json()
        assert body["error"] == "Insufficient permissions"
        return body

    return _assert


@pytest.fixture()
def assert_unauthorized():
    """assert_unauthorized(response) -> parsed body, for missing/invalid JWTs."""

    def _assert(response):
        assert response.status_code in (401, 422), response.get_json()
        body = response.get_json()
        assert "msg" in body
        return body

    return _assert