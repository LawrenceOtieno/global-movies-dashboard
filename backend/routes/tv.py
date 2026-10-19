"""
routes/tv.py — TV endpoints backed by Supabase + Pinecone.
"""

import difflib
import json
import os
import time

import requests
from flask import Blueprint, jsonify, request
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from pinecone import Pinecone

from config import TMDB_API_KEY, TMDB_BASE_URL, fetch_tmdb_genre_map

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

tv_bp = Blueprint("tv", __name__, url_prefix="/api/tv")

# --- Connection Pooling ---
DB_URI = os.getenv('SUPABASE_DB_URI')
engine = create_engine(
    DB_URI,
    pool_pre_ping=True,
    pool_size=3,
    max_overflow=5,
    pool_timeout=30,
    pool_recycle=300,
    connect_args={"connect_timeout": 30}
)

pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))
TV_INDEX_NAME = os.getenv('PINECONE_TV_INDEX')
tv_index = pc.Index(TV_INDEX_NAME)

TMDB_TV_GENRE_MAP = fetch_tmdb_genre_map("tv")
if TMDB_TV_GENRE_MAP:
    print(f"TV TMDB live lookup enabled ({len(TMDB_TV_GENRE_MAP)} genres loaded).")

MIN_SIMILARITY = 0.15


def safe_int(v):
    if v is None: return None
    try:
        if v != v: return None
    except Exception: pass
    try: return int(float(v))
    except (ValueError, TypeError): return None


def safe_float(v, ndigits=None):
    if v is None: return None
    try:
        if v != v: return None
    except Exception: pass
    try:
        f = float(v)
        return round(f, ndigits) if ndigits is not None else f
    except (ValueError, TypeError): return None


def safe_str(v):
    if v is None: return None
    try:
        if v != v: return None
    except Exception: pass
    return str(v)


# ---------- Cached analytics from disk ----------
CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', 'analytics_cache')


def load_cached(content_type: str, key: str, default):
    path = os.path.join(CACHE_DIR, f"{content_type}_{key}.json")
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"  WARNING: could not load {path}: {e}. Using default.")
        return default


print("Loading TV analytics from disk...")
_t0 = time.time()
CACHED_SUMMARY_STATS = load_cached('tv', 'summary_stats', {})
CACHED_GENRE_DISTRIBUTION = load_cached('tv', 'genre_distribution', {"genres": [], "uncategorized_count": 0, "uncategorized_percentage": 0.0})
CACHED_DECADE_TRENDS = load_cached('tv', 'decade_trends', [])
CACHED_NETWORK_PERFORMANCE = load_cached('tv', 'network_performance', [])
CACHED_COMPANY_PERFORMANCE = load_cached('tv', 'production_companies_performance', [])
CACHED_COUNTRY_PERFORMANCE = load_cached('tv', 'production_countries_performance', [])
CACHED_RANKINGS = load_cached('tv', 'show_rankings', {"top": [], "bottom": []})
CACHED_CULT_CLASSICS = load_cached('tv', 'cult_classics', {"hidden_gems": [], "overrated": [], "all_points": []})
print(f"  Loaded TV analytics in {time.time() - _t0:.2f}s")


# ---------- Fast In-Memory Title Matcher ----------
print("Loading TV titles for in-memory matcher...")
_t0 = time.time()
with engine.connect() as conn:
    # FIX: Cast vote_count (TEXT) to INTEGER for comparison
    rows = conn.execute(text(
        "SELECT DISTINCT name FROM tv_shows WHERE name IS NOT NULL AND CAST(vote_count AS INTEGER) >= 5"
    )).fetchall()
FUZZY_NAMES = [r[0] for r in rows if r[0]]
print(f"  TV in-memory matcher ready: {len(FUZZY_NAMES):,} names in {time.time() - _t0:.1f}s")


def find_fuzzy_match(title: str, threshold: float = 0.75):
    """Custom sequence matching. Guarantees finding the best match without difflib's cutoff bugs."""
    if not FUZZY_NAMES:
        return None

    best_match = None
    best_score = 0.0
    title_lower = title.lower()

    for candidate in FUZZY_NAMES:
        score = difflib.SequenceMatcher(None, title_lower, candidate.lower()).ratio()
        if score > best_score:
            best_score = score
            best_match = candidate

    if best_score >= threshold:
        return best_match
    return None


def suggest_similar_titles(title: str, limit: int = 5):
    """In-memory suggestions. Zero DB I/O."""
    if not FUZZY_NAMES:
        return []
    words = [w for w in title.lower().split() if len(w) > 2]
    candidates = [t for t in FUZZY_NAMES if any(w in t.lower() for w in words)]
    if not candidates:
        candidates = FUZZY_NAMES
    return difflib.get_close_matches(title, candidates, n=limit, cutoff=0.4)


# ---------- Source show lookup ----------
def find_source_show(title: str):
    """Single query that tries exact → starts-with → contains in order."""
    q = text("""
        SELECT id, name, genres, created_by, primary_network, primary_production_company, original_language, vote_count, first_air_year
        FROM tv_shows
        WHERE LOWER(name) = LOWER(:t) OR LOWER(name) LIKE LOWER(:t) || '%' OR LOWER(name) LIKE '%' || LOWER(:t) || '%'
        ORDER BY 
            CASE 
                WHEN LOWER(name) = LOWER(:t) THEN 1
                WHEN LOWER(name) LIKE LOWER(:t) || '%' THEN 2
                ELSE 3
            END,
            CAST(vote_count AS INTEGER) DESC NULLS LAST
        LIMIT 1
    """)
    with engine.connect() as conn:
        row = conn.execute(q, {"t": title}).fetchone()
    if row:
        return dict(row._mapping)

    fuzzy = find_fuzzy_match(title)
    if fuzzy:
        q2 = text("""
            SELECT id, name, genres, created_by, primary_network, primary_production_company, original_language, vote_count, first_air_year
            FROM tv_shows WHERE name = :t ORDER BY CAST(vote_count AS INTEGER) DESC NULLS LAST LIMIT 1
        """)
        with engine.connect() as conn:
            row = conn.execute(q2, {"t": fuzzy}).fetchone()
        if row:
            return dict(row._mapping)

    return None


def fetch_from_tmdb_tv_live(title: str):
    if not TMDB_API_KEY: return None
    try:
        r = requests.get(
            f"{TMDB_BASE_URL}/search/tv",
            params={"api_key": TMDB_API_KEY, "query": title},
            timeout=4,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results: return None
        show = results[0]

        genres = ",".join(TMDB_TV_GENRE_MAP.get(gid, "") for gid in show.get("genre_ids", []))
        first_air_date = show.get("first_air_date") or ""
        year = int(first_air_date[:4]) if first_air_date[:4].isdigit() else None

        return {
            "name": show.get("name") or title,
            "year": year,
            "genres": genres,
        }
    except requests.RequestException as e:
        print(f"TMDB TV live lookup failed for '{title}': {e}")
        return None


# ---------- Routes ----------
@tv_bp.route("/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "healthy",
        "total_shows": 250000,
        "recommender_ready": True,
    })


@tv_bp.route("/model-metadata", methods=["GET"])
def model_metadata():
    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT payload FROM analytics_cache WHERE content_type='tv' AND key='model_metadata'"
            )).fetchone()
        meta = row[0] if row else {}
    except Exception:
        meta = {}
    return jsonify({**meta, "recommender_ready": True})


@tv_bp.route("/summary-stats", methods=["GET"])
def summary_stats():
    return jsonify(CACHED_SUMMARY_STATS)


@tv_bp.route("/show-rankings", methods=["GET"])
def show_rankings():
    return jsonify(CACHED_RANKINGS)


@tv_bp.route("/genre-distribution", methods=["GET"])
def genre_distribution():
    return jsonify(CACHED_GENRE_DISTRIBUTION)


@tv_bp.route("/decade-trends", methods=["GET"])
def decade_trends():
    return jsonify(CACHED_DECADE_TRENDS)


@tv_bp.route("/network-performance", methods=["GET"])
def network_performance():
    return jsonify(CACHED_NETWORK_PERFORMANCE)


@tv_bp.route("/production-companies-performance", methods=["GET"])
def production_companies_performance():
    return jsonify(CACHED_COMPANY_PERFORMANCE)


@tv_bp.route("/production-countries-performance", methods=["GET"])
def production_countries_performance():
    return jsonify(CACHED_COUNTRY_PERFORMANCE)


@tv_bp.route("/cult-classics", methods=["GET"])
def cult_classics():
    return jsonify(CACHED_CULT_CLASSICS)


@tv_bp.route("/recommend", methods=["GET"])
def recommend():
    title = request.args.get("title", "").strip()
    n = int(request.args.get("n", 10))
    if not title:
        return jsonify({"error": "Pass a ?title= query param"}), 400

    source_row = find_source_show(title)

    if not source_row:
        suggestions = []

        fuzzy_title = find_fuzzy_match(title, threshold=0.75)
        if fuzzy_title:
            suggestions.append(fuzzy_title)

        for s in suggest_similar_titles(title, limit=4):
            if s not in suggestions:
                suggestions.append(s)

        msg = f"No show found matching '{title}'."
        if suggestions:
            msg += f" Did you mean: {', '.join(suggestions[:3])}?"

        return jsonify({
            "error": msg,
            "suggestions": suggestions
        }), 404

    source_title = source_row["name"]
    source_id = source_row["id"]

    try:
        res = tv_index.query(
            id=str(int(source_id)),
            top_k=n + 1,
            include_metadata=True,
        )
    except Exception as e:
        return jsonify({"error": f"Pinecone query failed: {e}"}), 500

    matches = [m for m in res.get("matches", []) if str(m["id"]) != str(int(source_id))]
    matches = [m for m in matches if m["score"] >= MIN_SIMILARITY]
    matches = matches[:n]

    if not matches:
        return jsonify({
            "source_title": source_title,
            "source": "pinecone",
            "recommendations": [],
            "accuracy_note": "No close match found."
        })

    ids = [int(m["id"]) for m in matches]
    enrich_q = text("SELECT id, vote_count, first_air_year FROM tv_shows WHERE id::bigint = ANY(:ids)")
    with engine.connect() as conn:
        rows = conn.execute(enrich_q, {"ids": ids}).fetchall()
    enrich = {str(r[0]): {"vote_count": r[1], "first_air_year": r[2]} for r in rows}

    return jsonify({
        "source_title": source_title,
        "source": "pinecone",
        "recommendations": [
            {
                "name": m["metadata"].get("title"),
                "year": safe_int(enrich.get(str(m["id"]), {}).get("first_air_year")),
                "match": safe_float(m["score"] * 100, 1),
                "weighted_rating": safe_float(m["metadata"].get("weighted_rating"), 2),
                "vote_count": safe_int(enrich.get(str(m["id"]), {}).get("vote_count")),
            }
            for m in matches
        ],
    })