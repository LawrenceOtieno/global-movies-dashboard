"""
routes/movies.py — movie endpoints backed by Supabase + Upstash Vector.
"""

import difflib
import json
import os
import time

import joblib
import requests
from flask import Blueprint, jsonify, request
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from upstash_vector import Index

from config import TMDB_API_KEY, TMDB_BASE_URL, fetch_tmdb_genre_map
from extensions import limiter

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

movies_bp = Blueprint("movies", __name__)

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

upstash_index = Index(
    url=os.getenv('UPSTASH_VECTOR_REST_URL'),
    token=os.getenv('UPSTASH_VECTOR_REST_TOKEN'),
)

VECTORIZER_PATH = os.path.join(os.path.dirname(__file__), '..', 'tfidf_vectorizer_v2.pkl')
try:
    _movie_vectorizer = joblib.load(VECTORIZER_PATH)
    print(f"Movie query vectorizer loaded (vocab={len(_movie_vectorizer.vocabulary_)})")
except Exception as e:
    print(f"WARNING: could not load movie vectorizer: {e}")
    _movie_vectorizer = None

TMDB_GENRE_MAP = fetch_tmdb_genre_map("movie")
if TMDB_GENRE_MAP:
    print(f"Movie TMDB live lookup enabled ({len(TMDB_GENRE_MAP)} genres loaded).")

MIN_SIMILARITY = 0.40


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


print("Loading movie analytics from disk...")
_t0 = time.time()
CACHED_SUMMARY_STATS = load_cached('movie', 'summary_stats', {})
CACHED_GENRE_DISTRIBUTION = load_cached('movie', 'genre_distribution', {"genres": [], "uncategorized_count": 0, "uncategorized_percentage": 0.0})
CACHED_DECADE_TRENDS = load_cached('movie', 'decade_trends', [])
CACHED_COMPANY_PERFORMANCE = load_cached('movie', 'production_companies_performance', [])
CACHED_COUNTRY_PERFORMANCE = load_cached('movie', 'production_countries_performance', [])
CACHED_RANKINGS = load_cached('movie', 'movie_rankings', {"top": [], "bottom": []})
CACHED_CULT_CLASSICS = load_cached('movie', 'cult_classics', {"hidden_gems": [], "overrated": [], "all_points": []})
print(f"  Loaded analytics in {time.time() - _t0:.2f}s")


# ---------- Fast In-Memory Title Matcher ----------
print("Loading titles for in-memory matcher...")
_t0 = time.time()
with engine.connect() as conn:
    # FIX: Cast vote_count (TEXT) to INTEGER for comparison
    rows = conn.execute(text(
        "SELECT DISTINCT title FROM movies WHERE title IS NOT NULL AND CAST(vote_count AS INTEGER) >= 5"
    )).fetchall()
FUZZY_TITLES = [r[0] for r in rows if r[0]]
print(f"  In-memory matcher ready: {len(FUZZY_TITLES):,} titles in {time.time() - _t0:.1f}s")


def find_fuzzy_match(title: str, threshold: float = 0.75):
    """Custom sequence matching. Guarantees finding the best match without difflib's cutoff bugs."""
    if not FUZZY_TITLES:
        return None

    best_match = None
    best_score = 0.0
    title_lower = title.lower()

    for candidate in FUZZY_TITLES:
        score = difflib.SequenceMatcher(None, title_lower, candidate.lower()).ratio()
        if score > best_score:
            best_score = score
            best_match = candidate

    if best_score >= threshold:
        return best_match
    return None


def suggest_similar_titles(title: str, limit: int = 5):
    """In-memory suggestions. Zero DB I/O."""
    if not FUZZY_TITLES:
        return []
    words = [w for w in title.lower().split() if len(w) > 2]
    candidates = [t for t in FUZZY_TITLES if any(w in t.lower() for w in words)]
    if not candidates:
        candidates = FUZZY_TITLES
    return difflib.get_close_matches(title, candidates, n=limit, cutoff=0.4)


FULL_SELECT = """
    SELECT id, title, genres, keywords, primary_production_company,
           original_language, production_countries, spoken_languages,
           original_title, vote_count, release_year
    FROM movies
"""


def find_source_movie(title: str):
    """Single query that tries exact → starts-with → contains in order."""
    q = text(FULL_SELECT + """
        WHERE LOWER(title) = LOWER(:t) OR LOWER(title) LIKE LOWER(:t) || '%' OR LOWER(title) LIKE '%' || LOWER(:t) || '%'
        ORDER BY 
            CASE 
                WHEN LOWER(title) = LOWER(:t) THEN 1
                WHEN LOWER(title) LIKE LOWER(:t) || '%' THEN 2
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
        q2 = text(FULL_SELECT + " WHERE title = :t ORDER BY CAST(vote_count AS INTEGER) DESC NULLS LAST LIMIT 1")
        with engine.connect() as conn:
            row = conn.execute(q2, {"t": fuzzy}).fetchone()
        if row:
            return dict(row._mapping)

    return None


def fetch_from_tmdb_live(title: str):
    if not TMDB_API_KEY: return None
    try:
        r = requests.get(
            f"{TMDB_BASE_URL}/search/movie",
            params={"api_key": TMDB_API_KEY, "query": title},
            timeout=4,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results: return None
        movie = results[0]

        genres = ",".join(TMDB_GENRE_MAP.get(gid, "") for gid in movie.get("genre_ids", []))
        keywords = ""
        try:
            kw = requests.get(
                f"{TMDB_BASE_URL}/movie/{movie['id']}/keywords",
                params={"api_key": TMDB_API_KEY},
                timeout=4,
            )
            if kw.ok:
                keywords = ",".join(k["name"] for k in kw.json().get("keywords", []))
        except requests.RequestException:
            pass

        release_date = movie.get("release_date") or ""
        year = int(release_date[:4]) if release_date[:4].isdigit() else None

        return {
            "title": movie.get("title") or title,
            "year": year,
            "genres": genres,
            "keywords": keywords,
            "original_language": movie.get("original_language", ""),
            "original_title": movie.get("original_title", ""),
        }
    except requests.RequestException as e:
        print(f"TMDB live lookup failed for '{title}': {e}")
        return None


def build_soup_from_row(row) -> str:
    genres = str(row.get("genres") or "").replace(",", " ")
    keywords = str(row.get("keywords") or "").replace(",", " ")
    company = str(row.get("primary_production_company") or "")
    countries = str(row.get("production_countries") or "").replace(",", " ")
    languages = str(row.get("spoken_languages") or "").replace(",", " ")
    original_title = str(row.get("original_title") or "")
    return (
        f"{genres} {genres} {genres} {keywords} {company} {countries} {languages} {original_title} {original_title}"
    )


# ---------- Routes ----------
@movies_bp.route("/api/health", methods=["GET"])
@limiter.exempt
def health_check():
    return jsonify({
        "status": "healthy",
        "total_movies": 1136706,
        "recommender_ready": _movie_vectorizer is not None,
        "vector_backend": "upstash",
    })


@movies_bp.route("/api/model-metadata", methods=["GET"])
def model_metadata():
    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT payload FROM analytics_cache WHERE content_type='movie' AND key='model_metadata'"
            )).fetchone()
        meta = row[0] if row else {}
    except Exception:
        meta = {}
    return jsonify({**meta, "recommender_ready": _movie_vectorizer is not None})


@movies_bp.route("/api/summary-stats", methods=["GET"])
def summary_stats():
    return jsonify(CACHED_SUMMARY_STATS)


@movies_bp.route("/api/movie-rankings", methods=["GET"])
def movie_rankings():
    return jsonify(CACHED_RANKINGS)


@movies_bp.route("/api/genre-distribution", methods=["GET"])
def genre_distribution():
    return jsonify(CACHED_GENRE_DISTRIBUTION)


@movies_bp.route("/api/decade-trends", methods=["GET"])
def decade_trends():
    return jsonify(CACHED_DECADE_TRENDS)


@movies_bp.route("/api/production-companies-performance", methods=["GET"])
def production_companies_performance():
    return jsonify(CACHED_COMPANY_PERFORMANCE)


@movies_bp.route("/api/production-countries-performance", methods=["GET"])
def production_countries_performance():
    return jsonify(CACHED_COUNTRY_PERFORMANCE)


@movies_bp.route("/api/cult-classics", methods=["GET"])
def cult_classics():
    return jsonify(CACHED_CULT_CLASSICS)


@movies_bp.route("/api/recommend", methods=["GET"])
@limiter.limit("15 per minute")
def recommend():
    title = request.args.get("title", "").strip()
    n = int(request.args.get("n", 10))
    if not title:
        return jsonify({"error": "Pass a ?title= query param"}), 400

    if _movie_vectorizer is None:
        return jsonify({"error": "Movie vectorizer not loaded"}), 503

    source_row = find_source_movie(title)

    if not source_row:
        suggestions = []

        fuzzy_title = find_fuzzy_match(title, threshold=0.75)
        if fuzzy_title:
            suggestions.append(fuzzy_title)

        for s in suggest_similar_titles(title, limit=4):
            if s not in suggestions:
                suggestions.append(s)

        msg = f"No movie found matching '{title}'."
        if suggestions:
            msg += f" Did you mean: {', '.join(suggestions[:3])}?"

        return jsonify({
            "error": msg,
            "suggestions": suggestions
        }), 404

    source_title = source_row["title"]
    source_id = source_row["id"]
    soup = build_soup_from_row(source_row)

    query_vec = _movie_vectorizer.transform([soup]).toarray().flatten().tolist()

    try:
        res = upstash_index.query(
            vector=query_vec,
            top_k=n + 1,
            include_metadata=True,
            include_vectors=False,
        )
    except Exception as e:
        return jsonify({"error": f"Upstash query failed: {e}"}), 500

    matches = []
    for m in res:
        if str(m.id) == str(source_id):
            continue
        if m.score is None or m.score < MIN_SIMILARITY:
            continue
        matches.append(m)
        if len(matches) >= n:
            break

    if not matches:
        return jsonify({
            "source_title": source_title,
            "source": "upstash",
            "recommendations": [],
            "accuracy_note": "No close match found."
        })

    ids = [int(m.id) for m in matches]
    enrich_q = text("SELECT id, vote_count, release_year FROM movies WHERE id::bigint = ANY(:ids)")
    with engine.connect() as conn:
        rows = conn.execute(enrich_q, {"ids": ids}).fetchall()
    enrich = {str(r[0]): {"vote_count": r[1], "release_year": r[2]} for r in rows}

    return jsonify({
        "source_title": source_title,
        "source": "upstash",
        "recommendations": [
            {
                "title": m.metadata.get("title"),
                "year": safe_int(enrich.get(str(m.id), {}).get("release_year")),
                "match": safe_float((m.score or 0) * 100, 1),
                "weighted_rating": safe_float(m.metadata.get("weighted_rating"), 2),
                "vote_count": safe_int(enrich.get(str(m.id), {}).get("vote_count")),
            }
            for m in matches
        ],
    })