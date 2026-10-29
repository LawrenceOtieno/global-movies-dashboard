"""
app.py — thin Flask entry point.

All actual logic lives in routes/movies.py and routes/tv.py as Blueprints —
this file just creates the app, enables CORS, registers both Blueprints,
and runs the dev server.

CORS is restricted to a known allowlist. In production the Vercel
frontend URL is provided via the ALLOWED_ORIGINS environment variable
(comma-separated list).

Rate limiting uses Upstash Redis (UPSTASH_REDIS_URL). Falls back to
in-memory storage if the env var is missing, which means limits won't
persist across restarts — acceptable for local dev.
"""

import os

from flask import Flask
from flask_compress import Compress
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from extensions import limiter
from routes.movies import movies_bp
from routes.tv import tv_bp

app = Flask(__name__)

# Trust Render's proxy so rate limiting sees the real user IP
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# --- CORS allowlist ---
ALLOWED_ORIGINS = [
    "http://localhost:5173",   # Vite dev server
    "http://localhost:3000",   # CRA dev server (fallback)
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]
_extra = os.getenv("ALLOWED_ORIGINS", "")
if _extra:
    ALLOWED_ORIGINS.extend([o.strip() for o in _extra.split(",") if o.strip()])

CORS(app, origins=ALLOWED_ORIGINS)
Compress(app)

# --- Rate Limiting ---
# Configure storage via config, then bind limiter to app
app.config["RATELIMIT_STORAGE_URI"] = os.getenv("UPSTASH_REDIS_URL", "memory://")
limiter.init_app(app)

app.register_blueprint(movies_bp)
app.register_blueprint(tv_bp)

# Note: The @limiter.exempt decorators for health checks live directly in
# routes/movies.py and routes/tv.py, applied at the function definition.

if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)