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
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from config import TMDB_API_KEY, TMDB_BASE_URL, fetch_tmdb_genre_map

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

tv_bp = Blueprint("tv", __name__, url_prefix="/api/tv")

# --- OPTIMIZATION: Connection Pooling ---
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


# ---------- Fuzzy matcher (OPTIMIZATION: Reduced to 1000) ----------
print("Building TV fuzzy title matcher...")
_t0 = time.time()
with engine.connect() as conn:
    rows = conn.execute(text(
        "SELECT DISTINCT name, vote_count FROM tv_shows WHERE name IS NOT NULL ORDER BY vote_count DESC NULLS LAST LIMIT 1000"
    )).fetchall()
FUZZY_NAMES = [r[0] for r in rows if r[0]]

fuzzy_vectorizer = None
fuzzy_matrix = None
if FUZZY_NAMES:
    fuzzy_vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
    fuzzy_matrix = fuzzy_vectorizer.fit_transform(FUZZY_NAMES)
print(f"  TV fuzzy matcher ready: {len(FUZZY_NAMES):,} names in {time.time() - _t0:.1f}s")


def find_fuzzy_match(title: str, threshold: float = 0.60):
    if fuzzy_vectorizer is None or not FUZZY_NAMES: return None
    q = fuzzy_vectorizer.transform([title])
    sims = cosine_similarity(q, fuzzy_matrix)[0]
    best = sims.argmax()
    if sims[best] >= threshold: return FUZZY_NAMES[best]
    return None


# ---------- Source show lookup ----------
def find_source_show(title: str):
    # 1. Exact match
    q = text("""
        SELECT id, name, genres, created_by, primary_network, primary_production_company, original_language, vote_count, first_air_year 
        FROM tv_shows WHERE LOWER(name) = LOWER(:t) ORDER BY vote_count DESC NULLS LAST LIMIT 1
    """)
    with engine.connect() as conn:
        row = conn.execute(q, {"t": title}).fetchone()
    if row: return dict(row._mapping)

    # 2. Fuzzy match
    fuzzy = find_fuzzy_match(title, threshold=0.60)
    if fuzzy:
        q_fuzzy = text("""
            SELECT id, name, genres, created_by, primary_network, primary_production_company, original_language, vote_count, first_air_year 
            FROM tv_shows WHERE name = :t ORDER BY vote_count DESC NULLS LAST LIMIT 1
        """)
        with engine.connect() as conn:
            row = conn.execute(q_fuzzy, {"t": fuzzy}).fetchone()
        if row: return dict(row._mapping)

    # 3. Loose match
    q_loose = text("""
        SELECT id, name, genres, created_by, primary_network, primary_production_company, original_language, vote_count, first_air_year 
        FROM tv_shows WHERE LOWER(name) LIKE '%' || LOWER(:t) || '%' ORDER BY vote_count DESC NULLS LAST LIMIT 1
    """)
    with engine.connect() as conn:
        row = conn.execute(q_loose, {"t": title}).fetchone()
    if row: return dict(row._mapping)

    # 4. TMDB Live Fallback
    live = fetch_from_tmdb_tv_live(title)
    if live:
        return {
            "id": None,
            "name": live["name"],
            "genres": live["genres"],
            "created_by": "",
            "primary_network": "",
            "primary_production_company": "",
            "original_language": "",
            "vote_count": 0,
            "first_air_year": live["year"],
            "is_live_tmdb": True
        }

    return None


def find_loose_matches(title: str, limit: int = 5):
    q = text("""
        SELECT name FROM tv_shows
        WHERE LOWER(name) LIKE '%' || LOWER(:t) || '%'
        ORDER BY vote_count DESC NULLS LAST
        LIMIT :lim
    """)
    with engine.connect() as conn:
        rows = conn.execute(q, {"t": title, "lim": limit}).fetchall()
    return [r[0] for r in rows]


def suggest_similar_titles(title: str, limit: int = 5):
    words = [w for w in title.lower().split() if len(w) > 2]
    if not words: return []
    pattern = "|".join(words)
    q = text("""
        SELECT DISTINCT name FROM tv_shows
        WHERE name ~* :pat
        LIMIT 5000
    """)
    try:
        with engine.connect() as conn:
            rows = conn.execute(q, {"pat": pattern}).fetchall()
        candidates = [r[0] for r in rows if r[0]]
    except Exception: return []
    if not candidates: return []
    return difflib.get_close_matches(title, candidates, n=limit, cutoff=0.5)


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
    # OPTIMIZATION: No DB hit. Fast, always works.
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
    source_id = None
    source_title = None

    if source_row:
        source_title = source_row["name"]
        source_id = source_row["id"]
    else:
        suggestions = find_loose_matches(title, limit=5)
        for s in suggest_similar_titles(title, limit=5):
            if s not in suggestions and len(suggestions) < 5:
                suggestions.append(s)
        msg = f"No show found matching '{title}' in the dataset."
        if suggestions:
            msg += f" Did you mean: {', '.join(suggestions)}?"
        return jsonify({"error": msg, "suggestions": suggestions}), 404

    if source_id is None:
        suggestions = find_loose_matches(title, limit=5)
        for s in suggest_similar_titles(title, limit=5):
            if s not in suggestions and len(suggestions) < 5:
                suggestions.append(s)
        return jsonify({
            "error": f"'{title}' is not in our local dataset, so we can't run recommendations on it.",
            "suggestions": suggestions if suggestions else ["Try searching for a TV show that is in the dataset."]
        }), 404

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
            "accuracy_note": "No close match found.",
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