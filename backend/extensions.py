"""
extensions.py — shared Flask extensions.
Kept separate from app.py to avoid circular imports with routes/*.py.
"""
from flask import request
from flask_limiter import Limiter


def get_client_ip():
    """
    Return the real client IP, preferring Cloudflare's dedicated header.

    On Render (which sits behind Cloudflare), the standard X-Forwarded-For
    header contains a chain of IPs (client, Cloudflare, Render's internal
    proxy). Using it directly is unreliable because the limiter may see an
    internal proxy IP instead of the real client.

    CF-Connecting-IP is set by Cloudflare and cannot be spoofed by an
    external client, so it's the safest signal for the true origin IP.
    """
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        # Leftmost entry is the original client
        return xff.split(",")[0].strip()
    return request.remote_addr or "unknown"


# Storage URI is injected in app.py via init_app
limiter = Limiter(
    get_client_ip,
    default_limits=["200 per day", "50 per hour"],
    strategy="moving-window",
    headers_enabled=True,
)