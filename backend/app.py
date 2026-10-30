"""
app.py — thin Flask entry point.

All actual logic lives in routes/movies.py and routes/tv.py as Blueprints —
this file just creates the app, enables CORS, registers both Blueprints,
and runs the dev server.

CORS is restricted to a known allowlist. In production the Vercel
frontend URL is provided via the ALLOWED_ORIGINS environment variable
(comma-separated list).
"""

import os

from flask import Flask
from flask_compress import Compress
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

# --- Create app ---
app = Flask(__name__)

# Trust Render's proxy (also useful if you later add rate limiting)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=3, x_proto=1, x_host=1)

# --- CORS allowlist ---
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]
_extra = os.getenv("ALLOWED_ORIGINS", "")
if _extra:
    ALLOWED_ORIGINS.extend([o.strip() for o in _extra.split(",") if o.strip()])

CORS(app, origins=ALLOWED_ORIGINS)
Compress(app)

# --- Register blueprints ---
from routes.movies import movies_bp
from routes.tv import tv_bp

app.register_blueprint(movies_bp)
app.register_blueprint(tv_bp)


if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)