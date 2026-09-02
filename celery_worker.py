import os
from app import create_app
from app.extensions import celery

flask_app = create_app(os.environ.get("FLASK_ENV", "development"))


class ContextTask(celery.Task):
    """Ensures every Celery task runs inside the Flask app context."""

    def __call__(self, *args, **kwargs):
        with flask_app.app_context():
            return self.run(*args, **kwargs)


celery.Task = ContextTask

from app.modules.appointment.services import appointment_service
from app.modules.billing.services import billing_service
from app.modules.clinic.services import clinic_service

