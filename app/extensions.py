from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO
from celery import Celery
import redis

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
cors = CORS()
limiter = Limiter(key_func=get_remote_address)
socketio = SocketIO()
celery = Celery(__name__)

redis_client = None 


def init_extensions(app):
    global redis_client

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(app)
    limiter.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*", message_queue=app.config.get("REDIS_URL"))

    redis_client = redis.StrictRedis.from_url(app.config["REDIS_URL"], decode_responses=True)

    celery.conf.update(
        broker_url=app.config.get("REDIS_URL"),
        result_backend=app.config.get("REDIS_URL"),
    )