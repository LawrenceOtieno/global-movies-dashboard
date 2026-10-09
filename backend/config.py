"""
config.py — shared setup loaded once, used by both routes/movies.py and
routes/tv.py. Keeping this in one place (rather than duplicating .env
loading and TMDB setup in each blueprint) means there's exactly one source
of truth for the API key and base URL — but each blueprint still builds and
caches its OWN genre-id map (movie genre ids and TV genre ids are different,
overlapping numbers mean different things in each), and each blueprint's
data/model loading stays completely separate from this file and from each
other.
"""

import os

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Loads backend/.env if present, so TMDB_API_KEY persists across restarts
# without retyping it into the terminal each session. Safe no-op if the file
# doesn't exist.
load_dotenv(os.path.join(BASE_DIR, ".env"))

TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
TMDB_BASE_URL = "https://api.themoviedb.org/3"


def fetch_tmdb_genre_map(endpoint: str) -> dict:
    """endpoint is 'movie' or 'tv' — TMDB keeps separate genre lists for
    each. Returns {} on any failure (no key, network error) rather than
    raising, so an unreachable TMDB at startup never prevents the server
    from starting — it just means the live fallback silently stays
    unavailable for that session, same as if no key were set at all."""
    if not TMDB_API_KEY:
        return {}
    try:
        resp = requests.get(
            f"{TMDB_BASE_URL}/genre/{endpoint}/list",
            params={"api_key": TMDB_API_KEY},
            timeout=5,
        )
        resp.raise_for_status()
        return {g["id"]: g["name"] for g in resp.json().get("genres", [])}
    except Exception as e:
        print(f"TMDB {endpoint} genre list fetch failed ({e}) — "
              f"live lookup will be skipped for this session.")
        return {}


if TMDB_API_KEY:
    print("TMDB_API_KEY found — live lookup fallback available for both movies and TV.")
else:
    print("TMDB_API_KEY not set — recommenders will only search local datasets "
          "(this is entirely optional; see backend/.env setup notes).")
