import os
from flask import Flask

from app.config import config_by_name
from app.extensions import init_extensions, db
from app.core.error_handlers import register_error_handlers


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    init_extensions(app)

    with app.app_context():
        from app import models_registry

    register_error_handlers(app)
    register_blueprints(app)

    return app


def register_blueprints(app):
    from app.core.audit.routes.audit_route import audit_bp
    from app.modules.ai.routes.ai_route import ai_bp
    from app.modules.ambulance.routes import vehicle_bp
    from app.modules.ambulance.routes import trip_bp
    from app.modules.appointment.routes.appointment_route import appointment_bp
    from app.modules.billing.routes.billing_route import billing_bp
    from app.modules.clinic.routes.clinic_route import clinic_bp
    from app.modules.consultation.routes.consultation_route import consultation_bp
    from app.modules.ward.routes.ward_route import ward_bp

    app.register_blueprint(vehicle_bp)
    app.register_blueprint(trip_bp)
    app.register_blueprint(appointment_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(clinic_bp)
    app.register_blueprint(consultation_bp)
    app.register_blueprint(ward_bp)


