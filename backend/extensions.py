"""
extensions.py — shared Flask extensions.
Kept separate from app.py to avoid circular imports with routes/*.py.
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Storage URI is injected in app.py via init_app
limiter = Limiter(
    get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    strategy="moving-window",
    headers_enabled=True,
)