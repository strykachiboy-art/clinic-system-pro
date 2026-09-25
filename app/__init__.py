from __future__ import annotations

import os
import re

from flask import Flask, request

from app.config import config_by_name
from app.extensions import (
    celery,
    db,
    init_extensions,
)
from app.core.api import register_api_blueprint
from app.core.api.versioning import validate_api_version
from app.core.error_handlers import register_error_handlers
from app.core.observability import (
    init_celery_metrics,
    init_db_metrics,
    init_request_metrics,
)


_API_VERSION_PATH_PATTERN = re.compile(
    r"^/api/(?P<version>v\d+)(?:/|$)"
)


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

    init_celery_metrics(celery)
    init_db_metrics(app)
    init_request_metrics(app)

    with app.app_context():
        from app import models_registry  # noqa: F401

    register_error_handlers(app)
    register_api_version_boundary(app)
    register_blueprints(app)

    return app


def register_api_version_boundary(app: Flask) -> None:

    @app.before_request
    def validate_api_version_boundary():
        match = _API_VERSION_PATH_PATTERN.match(
            request.path
        )

        if not match:
            return None

        validate_api_version(
            match.group("version")
        )

        return None


def register_blueprints(app):
    from app.core.web_routes import web_bp
    from app.core.audit.routes.audit_route import (
        audit_bp
    )
    from app.core.auth.user.routes.auth_routes import (
        auth_bp
    )
    from app.core.notifications.routes.notification_route import (
        notification_bp
    )

    from app.modules.ai.routes.ai_route import ai_bp
    from app.modules.ambulance.routes.ambulance_vehicle_routes import (
        vehicle_bp
    )
    from app.modules.ambulance.routes.ambulance_trip_routes import (
        trip_bp
    )
    from app.modules.appointment.routes.appointment_route import (
        appointment_bp
    )
    from app.modules.billing.routes.billing_route import (
        billing_bp
    )
    from app.modules.clinic.routes.clinic_route import (
        clinic_bp
    )
    from app.modules.consultation.routes.consultation_route import (
        consultation_bp
    )
    from app.modules.hie.routes.hie_route import hie_bp
    from app.modules.inventory.routes.inventory_route import (
        inventory_bp
    )
    from app.modules.lab.routes.lab_route import lab_bp
    from app.modules.patient.routes.patient_route import (
        patient_bp
    )
    from app.modules.pharmacy.routes.pharmacy_routes import (
        pharmacy_bp
    )
    from app.modules.prescription.routes.prescription_routes import (
        prescription_bp
    )
    from app.modules.reports.routes.reports_route import (
        reports_bp
    )
    from app.modules.settings.routes.settings_routes import (
        settings_bp
    )
    from app.modules.staff.routes.staff_route import (
        staff_bp
    )
    from app.modules.ward.routes.ward_route import ward_bp
    from app.core.auth.user.routes.user_device_routes import (
        user_device_bp
    )
    from app.modules.asset_control.routes.asset_route import (
        asset_bp
    )
    from app.modules.profile.routes.profile_route import (
        profile_bp
    )
    from app.modules.access_control.routes.access_control_routes import (
        access_control_bp
    )
    from app.modules.chat.routes.chat_routes import chat_bp
    from app.modules.dashboard.routes.dashboard_route import (
        dashboard_bp
    )
    
    from app.core.emergency_access.routes.emergency_access_routes import (
        emergency_access_bp,
    )
    
    from app.core.clinical_safety.routes.clinical_safety_routes import (
        clinical_safety_bp,
    )
    
    from app.modules.feedback.routes.feedback_routes import (
        feedback_bp,
    )

    app.register_blueprint(web_bp)

    api_blueprints = (
        auth_bp,
        vehicle_bp,
        trip_bp,
        hie_bp,
        pharmacy_bp,
        appointment_bp,
        audit_bp,
        ai_bp,
        billing_bp,
        clinic_bp,
        consultation_bp,
        inventory_bp,
        lab_bp,
        patient_bp,
        prescription_bp,
        reports_bp,
        staff_bp,
        ward_bp,
        notification_bp,
        settings_bp,
        user_device_bp,
        asset_bp,
        profile_bp,
        access_control_bp,
        chat_bp,
        dashboard_bp,
        emergency_access_bp,
        clinical_safety_bp,
        feedback_bp,
    )

    for blueprint in api_blueprints:
        register_api_blueprint(
            app,
            blueprint,
        )