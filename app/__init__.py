import os
from flask import Flask

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

    return app


def register_blueprints(app):
    pass