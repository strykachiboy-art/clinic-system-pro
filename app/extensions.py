from celery import Celery
from celery.schedules import crontab
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
import redis

from app.core.auth.user.services.token_service import (
    is_token_revoked,
)


db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
cors = CORS()
limiter = Limiter(
    key_func=get_remote_address
)
socketio = SocketIO()
celery = Celery(__name__)

redis_client = None


@jwt.token_in_blocklist_loader
def check_if_token_revoked(
    jwt_header,
    jwt_payload,
):
    """
    JWT blocklist callback.

    Token revocation remains fail-closed through
    token_service.is_token_revoked().
    """
    return is_token_revoked(jwt_payload)


def init_extensions(app):
    global redis_client

    # ------------------------------------------------------------------
    # Flask-SQLAlchemy
    # ------------------------------------------------------------------

    db.init_app(app)

    # ------------------------------------------------------------------
    # Flask-Migrate
    # ------------------------------------------------------------------

    migrate.init_app(
        app,
        db,
    )

    # ------------------------------------------------------------------
    # JWT
    # ------------------------------------------------------------------

    jwt.init_app(app)

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------

    cors.init_app(app)

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    limiter.init_app(app)

    # ------------------------------------------------------------------
    # Redis
    # ------------------------------------------------------------------

    redis_url = app.config["REDIS_URL"]

    redis_client = redis.StrictRedis.from_url(
        redis_url,
        decode_responses=True,
    )

    # ------------------------------------------------------------------
    # Socket.IO
    # ------------------------------------------------------------------

    socketio.init_app(
        app,
        cors_allowed_origins="*",
        message_queue=redis_url,
    )

    # ------------------------------------------------------------------
    # Celery
    # ------------------------------------------------------------------

    celery.conf.update(
        broker_url=app.config.get(
            "CELERY_BROKER_URL",
            redis_url,
        ),
        result_backend=app.config.get(
            "CELERY_RESULT_BACKEND",
            redis_url,
        ),
        timezone="UTC",
        beat_schedule={
            "check-upcoming-appointments-hourly": {
                "task": "check_upcoming_appointments",
                "schedule": 3600.0,
            },
            "mark-overdue-invoices-daily": {
                "task": "mark_overdue_invoices",
                "schedule": crontab(
                    hour=0,
                    minute=0,
                ),
            },
            "reset-monthly-ai-usage": {
                "task": "reset_monthly_ai_usage",
                "schedule": crontab(
                    day_of_month=1,
                    hour=0,
                    minute=0,
                ),
            },
        },
    )