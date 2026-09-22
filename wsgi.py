from __future__ import annotations

import os

from app import create_app


app = create_app(
    os.environ.get(
        "FLASK_ENV",
        "production",
    )
)



# cd C:\Users\HP\Documents\clinic-system

# New-Item -ItemType Directory -Force .\logs | Out-Null

# if (Test-Path .\logs\system_mixed_server.log) {
#     Remove-Item .\logs\system_mixed_server.log -Force
# }

# python -c "import os; from app import create_app; from app.extensions import socketio; app=create_app('development'); socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT',5000)), debug=False, use_reloader=False)" 2>&1 | Tee-Object -FilePath .\logs\system_mixed_server.log