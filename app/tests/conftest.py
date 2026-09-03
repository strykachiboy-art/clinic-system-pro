import pytest
from app import create_app
from app.extensions import db as _db


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


@pytest.fixture()
def clinic(db):
    from app.modules.clinic.models.clinic_model import Clinic
    c = Clinic(name="Test Clinic", ai_credits=5)
    db.session.add(c)
    db.session.commit()
    return c


@pytest.fixture()
def patient(db, clinic):
    from app.modules.patient.models.patient_model import Patient
    p = Patient(clinic_id=clinic.id, first_name="Jane", last_name="Doe", patient_number="MRN-1")
    db.session.add(p)
    db.session.commit()
    return p


@pytest.fixture()
def user(db, clinic):
    from app.modules.user.models.user_model import User
    from app.core.enums.role_enums import Role
    u = User(email="admin@test.com", role=Role.ADMIN, clinic_id=clinic.id)
    u.set_password("supersecret")
    db.session.add(u)
    db.session.commit()
    return u