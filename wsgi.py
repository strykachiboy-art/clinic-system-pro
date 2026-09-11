import os
from app import create_app

app = create_app(os.environ.get("FLASK_ENV", "production"))

if __name__ == "__main__":
    app.run()
    

# $env:FLASK_APP = "wsgi.py"
# 25. Assets Control ->.pending Profiles → 26. Dashboard → 27. Advanced Access Control → 28. Internal Clinical Chat → 29. Rules Engine
