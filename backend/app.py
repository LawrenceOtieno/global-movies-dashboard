"""
app.py — thin Flask entry point.
"""

import os

from flask import Flask, jsonify, request
from flask_compress import Compress
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from extensions import limiter, get_client_ip

# --- Create app and initialize extensions BEFORE importing blueprints ---
app = Flask(__name__)

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=3, x_proto=1, x_host=1)

# CORS
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

# Rate Limiting — MUST be initialized BEFORE importing blueprints
app.config["RATELIMIT_STORAGE_URI"] = os.getenv("UPSTASH_REDIS_URL", "memory://")
limiter.init_app(app)

# NOW import and register blueprints (their @limiter.limit decorators will work)
from routes.movies import movies_bp
from routes.tv import tv_bp

app.register_blueprint(movies_bp)
app.register_blueprint(tv_bp)


@app.route("/api/ratelimit-status")
def ratelimit_status():
    """TEMPORARY diagnostic endpoint — delete after debugging is done."""
    raw = os.getenv("UPSTASH_REDIS_URL") or ""

    # Try to read actual rate limit keys from Redis
    redis_keys = []
    redis_error = None
    try:
        import redis
        r = redis.from_url(raw)
        redis_keys = [k.decode() for k in r.keys("LIMITER*")][:20]
    except Exception as e:
        redis_error = str(e)

    # Introspect what limits are registered on the limiter instance
    limit_strings = []
    try:
        for (scope, limit) in limiter.limit_manager._limits:
            limit_strings.append(str(limit))
    except Exception:
        pass

    # --- NEW: inspect route-level registration ---
    route_limits = {}
    try:
        if hasattr(limiter, '_route_limits'):
            for key, limits in limiter._route_limits.items():
                route_limits[str(key)] = [str(l) for l in limits]
    except Exception as e:
        route_limits = {"error": str(e)}

    # --- NEW: check if recommend functions are wrapped by the limiter ---
    try:
        from routes.movies import recommend as movie_recommend
        from routes.tv import recommend as tv_recommend
        movie_wrapped = hasattr(movie_recommend, '__wrapped__')
        tv_wrapped = hasattr(tv_recommend, '__wrapped__')
        movie_module = movie_recommend.__module__
        movie_name = movie_recommend.__name__
    except Exception as e:
        movie_wrapped = f"error: {e}"
        tv_wrapped = f"error: {e}"
        movie_module = "unknown"
        movie_name = "unknown"

    return jsonify({
        "env_var_present": bool(raw),
        "limiter_storage_type": type(limiter._storage).__name__ if hasattr(limiter, "_storage") and limiter._storage else "None",
        "limiter_sees_ip": get_client_ip(),
        "redis_keys_count": len(redis_keys),
        "redis_keys_sample": redis_keys,
        "redis_error": redis_error,
        "registered_limits": limit_strings,
        # --- New diagnostic fields ---
        "route_limits_count": len(route_limits),
        "route_limits_keys": list(route_limits.keys())[:10],
        "movie_recommend_module": movie_module,
        "movie_recommend_name": movie_name,
        "movie_recommend_has_wrapped": movie_wrapped,
        "tv_recommend_has_wrapped": tv_wrapped,
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)