from __future__ import annotations

import os

from flask import Flask

from app.config import config_by_name
from app.extensions import db, init_extensions
from app.core.error_handlers import register_error_handlers


def create_app(config_name=None):
    config_name = config_name or os.environ.get(
        "FLASK_ENV",
        "development",
    )

    if config_name not in config_by_name:
        raise ValueError(
            f"Unknown configuration: {config_name}"
        )

    app = Flask(__name__)

    app.config.from_object(
        config_by_name[config_name]
    )

    init_extensions(app)

    # Import all registered models so SQLAlchemy
    # knows about them before migrations/table creation.
    with app.app_context():
        from app import models_registry  # noqa: F401

    register_error_handlers(app)
    register_blueprints(app)

    return app


def register_blueprints(app):
    from app.core.web_routes import web_bp
    from app.core.audit.routes.audit_route import audit_bp
    from app.core.auth.user.routes.auth_routes import auth_bp
    from app.core.notifications.routes.notification_route import notification_bp

    from app.modules.ai.routes.ai_route import ai_bp

    from app.modules.ambulance.routes.ambulance_vehicle_routes import (
        vehicle_bp,
    )
    from app.modules.ambulance.routes.ambulance_trip_routes import (
        trip_bp,
    )

    from app.modules.appointment.routes.appointment_route import (
        appointment_bp,
    )
    from app.modules.billing.routes.billing_route import billing_bp
    from app.modules.clinic.routes.clinic_route import clinic_bp
    from app.modules.consultation.routes.consultation_route import (
        consultation_bp,
    )
    from app.modules.hie.routes.hie_route import hie_bp
    from app.modules.inventory.routes.inventory_route import inventory_bp
    from app.modules.lab.routes.lab_route import lab_bp
    from app.modules.messages.routes.message_routes import message_bp
    from app.modules.patient.routes.patient_route import patient_bp
    from app.modules.pharmacy.routes.pharmacy_routes import pharmacy_bp
    from app.modules.prescription.routes.prescription_routes import (
        prescription_bp,
    )
    from app.modules.reports.routes.reports_route import reports_bp
    from app.modules.settings.routes.settings_routes import settings_bp
    from app.modules.staff.routes.staff_route import staff_bp
    from app.modules.ward.routes.ward_route import ward_bp
    from app.core.auth.user.routes.user_device_routes import user_device_bp
    from app.modules.asset_control.routes.asset_route import asset_bp
    

    app.register_blueprint(web_bp)
    app.register_blueprint(auth_bp)

    app.register_blueprint(vehicle_bp)
    app.register_blueprint(trip_bp)

    app.register_blueprint(hie_bp)
    app.register_blueprint(pharmacy_bp)
    app.register_blueprint(appointment_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(clinic_bp)
    app.register_blueprint(consultation_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(lab_bp)
    app.register_blueprint(patient_bp)
    app.register_blueprint(prescription_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(staff_bp)
    app.register_blueprint(ward_bp)

    app.register_blueprint(message_bp)
    app.register_blueprint(notification_bp)

    app.register_blueprint(settings_bp)
    app.register_blueprint(user_device_bp)
    app.register_blueprint(asset_bp)