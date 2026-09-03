import os
from flask import Flask, jsonify
from app.core.exceptions import DomainError

from app.config import config_by_name
from app.extensions import init_extensions, db


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    init_extensions(app)

    with app.app_context():
        from app import models_registry

    register_blueprints(app)
    
    @app.errorhandler(DomainError)
    def handle_domain_error(err):
        return jsonify({"success": False, "error": str(err)}), err.status_code


    return app


def register_blueprints(app):
    from app.core.audit.routes.audit_route import audit_bp
    from app.modules.ai.routes.ai_route import ai_bp

    app.register_blueprint(audit_bp)
    app.register_blueprint(ai_bp)
    
    
# then we issue access tokens in login