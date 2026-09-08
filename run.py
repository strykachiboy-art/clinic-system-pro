import os
from app import create_app
from app.extensions import socketio

app = create_app(os.environ.get("FLASK_ENV", "development"))

if __name__ == "__main__":
    # socketio.run instead of app.run — required since we're using Flask-SocketIO
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=app.config.get("DEBUG", False),
    )
    