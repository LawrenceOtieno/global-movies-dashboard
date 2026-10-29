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

from flask import Flask, jsonify, request
from flask_compress import Compress
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from extensions import limiter, get_client_ip
from routes.movies import movies_bp
from routes.tv import tv_bp

app = Flask(__name__)

# Trust Cloudflare + Render's proxy layers. x_for=3 accounts for the
# full chain: real client → Cloudflare → Render internal proxy → app.
# (The limiter itself uses CF-Connecting-IP directly, but ProxyFix is
# still needed so Flask's request.remote_addr reflects the real IP.)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=3, x_proto=1, x_host=1)

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


@app.route("/api/ratelimit-status")
def ratelimit_status():
    """TEMPORARY diagnostic endpoint — delete after debugging is done."""
    raw = os.getenv("UPSTASH_REDIS_URL") or ""
    return jsonify({
        "env_var_present": bool(raw),
        "env_var_prefix": raw[:10] if raw else "MISSING",
        "env_var_length": len(raw),
        "configured_storage": app.config.get("RATELIMIT_STORAGE_URI", "")[:10],
        "limiter_storage_type": type(limiter._storage).__name__ if hasattr(limiter, "_storage") and limiter._storage else "None",
        # --- IP diagnostics ---
        "remote_addr": request.remote_addr,
        "limiter_sees_ip": get_client_ip(),
        "x_forwarded_for": request.headers.get("X-Forwarded-For", "NOT SET"),
        "cf_connecting_ip": request.headers.get("CF-Connecting-IP", "NOT SET"),
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)