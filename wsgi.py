from __future__ import annotations

import os

from app import create_app


app = create_app(
    os.environ.get(
        "FLASK_ENV",
        "production",
    )
)