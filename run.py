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
    
# C:\Users\HP>psql -U postgres
# 'psql' is not recognized as an internal or external command,
# operable program or batch file.

# C:\Users\HP>cd C:\Program Files\PostgreSQL\18\bin

# C:\Program Files\PostgreSQL\18\bin>psql -U postgres
# psql (18.3)
# WARNING: Console code page (437) differs from Windows code page (1252)
#          8-bit characters might not work correctly. See psql reference
#          page "Notes for Windows users" for details.
# Type "help" for help.

# postgres=#