"""
routes/movies.py — all movie-related endpoints, as a Flask Blueprint.

This is the SAME logic that used to live directly in app.py — moved here
unchanged (not rewritten) as part of splitting the backend into movies/tv
Blueprints so app.py stays a thin entry point as TV endpoints join it. Every
route path is identical to before (still /api/..., not /api/movies/...) so
nothing on the frontend needs to change because of this move.

See the module docstring history in git/previous versions for the full story
on each fix (performance caching, the zero-vote placeholder bug, the
weighted-rating formula, etc.) — preserved in the comments below, unchanged.
"""

import difflib
import json
import os
import time

import joblib
import pandas as pd
import requests
from flask import Blueprint, jsonify, request
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from config import TMDB_API_KEY, TMDB_BASE_URL, fetch_tmdb_genre_map

movies_bp = Blueprint("movies", __name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_BACKEND_DIR = os.path.dirname(BASE_DIR)  # routes/ -> backend/

TMDB_GENRE_MAP = fetch_tmdb_genre_map("movie")
if TMDB_GENRE_MAP:
    print(f"Movie TMDB live lookup enabled ({len(TMDB_GENRE_MAP)} genres loaded).")

PARQUET_PATH = os.path.join(PROJECT_BACKEND_DIR, "global_movies.parquet")

VECTORIZER_PATH = os.path.join(PROJECT_BACKEND_DIR, "tfidf_vectorizer.pkl")
NN_MODEL_PATH = os.path.join(PROJECT_BACKEND_DIR, "recommender_nn.pkl")
REC_INDEX_PATH = os.path.join(PROJECT_BACKEND_DIR, "recommender_index.parquet")
METADATA_PATH = os.path.join(PROJECT_BACKEND_DIR, "model_metadata.json")

# --- Recommendation quality floor ---
# See the previous version of this file for the full reasoning. Below this
# cosine similarity, neighbors are genre-noise; returning them silently was
# the "guessing" behavior this constant exists to prevent.
MIN_SIMILARITY = 0.15

try:
    df = pd.read_parquet(PARQUET_PATH)
except Exception as e:
    print(f"Warning: Could not load movie dataset parquet: {e}")
    df = pd.DataFrame()

try:
    vectorizer = joblib.load(VECTORIZER_PATH)
    nn_model = joblib.load(NN_MODEL_PATH)
    rec_index = pd.read_parquet(REC_INDEX_PATH)
except Exception as e:
    print(f"Warning: Could not load movie recommender: {e}")
    vectorizer = None
    nn_model = None
    rec_index = pd.DataFrame()

try:
    with open(METADATA_PATH) as f:
        MODEL_METADATA = json.load(f)
except FileNotFoundError:
    MODEL_METADATA = {}
    print("Warning: movie model_metadata.json not found — run train_model.py first.")


def safe_int(value):
    """Convert a possibly-NaN pandas/numpy numeric to a Python int, or None.
    This is the JSON-safety guard: raw pandas NaN serializes to the literal
    text `NaN` via Flask's jsonify, which is NOT valid JSON and blows up
    JSON.parse on the frontend. Every scalar that goes into a response goes
    through one of these helpers."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return int(value)


def safe_float(value, ndigits=None):
    """Same idea as safe_int, for floats. Optionally rounds to ndigits."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    v = float(value)
    return round(v, ndigits) if ndigits is not None else v


def safe_str(value):
    """None/NaN-safe string. Returns None for missing values (not "nan")."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


# --- Fuzzy title matcher (typo tolerance for /api/recommend) ---
FUZZY_TITLES = []
fuzzy_vectorizer = None
fuzzy_matrix = None
if not df.empty:
    _t0 = time.time()
    FUZZY_TITLES = df["title"].dropna().unique().tolist()
    fuzzy_vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
    fuzzy_matrix = fuzzy_vectorizer.fit_transform(FUZZY_TITLES)
    print(f"Fuzzy title matcher built: {len(FUZZY_TITLES):,} distinct titles "
          f"in {time.time() - _t0:.1f}s.")


def find_fuzzy_match(title: str, threshold: float = 0.70):
    if fuzzy_vectorizer is None or not FUZZY_TITLES:
        return None
    query_vec = fuzzy_vectorizer.transform([title])
    sims = cosine_similarity(query_vec, fuzzy_matrix)[0]
    best_idx = sims.argmax()
    if sims[best_idx] >= threshold:
        return FUZZY_TITLES[best_idx]
    return None


# ============================================================================
# PRECOMPUTED, CACHED RESPONSES
# ============================================================================

CACHED_SUMMARY_STATS = {}
CACHED_GENRE_DISTRIBUTION = {"genres": [], "uncategorized_count": 0, "uncategorized_percentage": 0.0}
CACHED_DECADE_TRENDS = []
CACHED_COMPANY_PERFORMANCE = []
CACHED_COUNTRY_PERFORMANCE = []
CACHED_RANKINGS = {"top": [], "bottom": []}

if not df.empty:
    print("Precomputing cached movie dashboard data...")

    total_movies = int(len(df))
    total_revenue = float(df["revenue"].sum())

    rated = df[df["vote_count"] > 0]
    avg_rating = float(rated["vote_average"].mean()) if not rated.empty else 0.0

    timed = df[df["runtime"] > 0]
    avg_runtime = float(timed["runtime"].mean()) if not timed.empty else 0.0

    highly_rated = int((df["vote_average"] >= 7.0).sum())

    genre_revenue_df = df[["genres", "revenue"]].copy()
    genre_revenue_df["genres"] = genre_revenue_df["genres"].fillna("").astype(str).replace({"nan": "", "None": ""}).str.split(",")
    genre_revenue_exploded = genre_revenue_df.explode("genres")
    genre_revenue_exploded["genres"] = genre_revenue_exploded["genres"].str.strip()
    genre_revenue_exploded = genre_revenue_exploded[genre_revenue_exploded["genres"] != ""]
    genre_revenue_totals = genre_revenue_exploded.groupby("genres")["revenue"].sum()
    top_genre_by_revenue = None
    if not genre_revenue_totals.empty:
        top_g = genre_revenue_totals.idxmax()
        top_genre_by_revenue = [top_g, round(float(genre_revenue_totals[top_g]), 2)]

    CACHED_SUMMARY_STATS = {
        "total_movies": total_movies,
        "average_rating": round(avg_rating, 2),
        "total_revenue": round(total_revenue, 2),
        "average_runtime_minutes": round(avg_runtime, 1),
        "highly_rated_count": highly_rated,
        "other_count": total_movies - highly_rated,
        "top_genre_by_revenue": top_genre_by_revenue,
    }

    genres_series = df["genres"].fillna("").astype(str).replace({"nan": "", "None": ""})
    genre_tags = genres_series.str.split(",").explode().str.strip()
    is_uncategorized = genre_tags == ""
    uncategorized_count = int(is_uncategorized.sum())
    genre_tags = genre_tags[~is_uncategorized]

    genre_counts = genre_tags.value_counts()
    genre_total = int(genre_counts.sum()) + uncategorized_count
    CACHED_GENRE_DISTRIBUTION = {
        "genres": [
            {"genre": g, "count": int(c), "percentage": round(c / genre_total * 100, 1)}
            for g, c in genre_counts.head(8).items()
        ],
        "uncategorized_count": uncategorized_count,
        "uncategorized_percentage": round(uncategorized_count / genre_total * 100, 1) if genre_total else 0.0,
    }

    if "decade" in df.columns:
        trends = df.dropna(subset=["decade"]).groupby("decade")["vote_average"].mean().reset_index()
        trends.columns = ["decade", "avg_rating"]
        trends = trends.sort_values("decade")
        trends["avg_rating"] = trends["avg_rating"].round(2)
        trends["decade"] = trends["decade"].astype(int)
        CACHED_DECADE_TRENDS = trends.to_dict(orient="records")

    total_production_companies = 0
    if "primary_production_company" in df.columns:
        valid_companies = df[df["primary_production_company"].notna()
                              & (df["primary_production_company"] != "nan")]
        total_production_companies = int(valid_companies["primary_production_company"].nunique())

        company_rev = (
            valid_companies
            .groupby("primary_production_company")["revenue"]
            .sum()
            .sort_values(ascending=False)
            .head(5)
        )
        CACHED_COMPANY_PERFORMANCE = [
            {
                "production_company": name,
                "total_revenue": float(rev),
                "percentage_of_total": round(float(rev) / total_revenue * 100, 1) if total_revenue else 0.0,
            }
            for name, rev in company_rev.items()
        ]
    CACHED_SUMMARY_STATS["total_production_companies"] = total_production_companies

    min_votes_for_quality = max(int(df["vote_count"].quantile(0.90)), 50)

    if "primary_production_country" in df.columns:
        country_rated = df[df["vote_count"] >= min_votes_for_quality]
        countries = (
            country_rated[country_rated["primary_production_country"].notna()
                           & (country_rated["primary_production_country"] != "nan")]
            .groupby("primary_production_country")
            .agg(movie_count=("vote_average", "count"), avg_rating=("vote_average", "mean"))
            .reset_index()
            .sort_values(by="movie_count", ascending=False)
            .head(8)
            .sort_values(by="avg_rating", ascending=False)
        )
        countries.columns = ["production_country", "movie_count", "avg_rating"]
        countries["avg_rating"] = countries["avg_rating"].round(2)
        CACHED_COUNTRY_PERFORMANCE = countries.to_dict(orient="records")

    if "weighted_rating" in df.columns:
        ranking_pool = df[(df["vote_count"] >= min_votes_for_quality) & (df["revenue"] > 0)]

        def _ranking_rows(sub):
            return [
                {
                    "title": r.title,
                    "year": safe_int(r.release_year),
                    "rating": safe_float(r.vote_average),
                    "weighted_rating": safe_float(r.weighted_rating, 2),
                    "vote_count": safe_int(r.vote_count),
                    "revenue": safe_float(r.revenue),
                }
                for r in sub.itertuples()
            ]

        cols = ["title", "release_year", "vote_average", "weighted_rating", "vote_count", "revenue"]
        if not ranking_pool.empty:
            CACHED_RANKINGS = {
                "top": _ranking_rows(ranking_pool.nlargest(10, "weighted_rating")[cols]),
                "bottom": _ranking_rows(ranking_pool.nsmallest(10, "weighted_rating")[cols]),
            }
        print(f"  Movie rankings pool: {len(ranking_pool):,} movies "
              f"(vote_count >= {min_votes_for_quality}, revenue > 0).")

    print("Movie precomputation done.")


def build_soup(row) -> str:
    genres = str(row.get("genres", "")).replace(",", " ")
    keywords = str(row.get("keywords", "")).replace(",", " ")
    company = str(row.get("primary_production_company", ""))
    language = str(row.get("original_language", ""))
    return f"{genres} {genres} {genres} {keywords} {company} {language}"


@movies_bp.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "healthy",
        "total_movies": len(df),
        "recommender_ready": nn_model is not None and vectorizer is not None,
    })


@movies_bp.route("/api/model-metadata", methods=["GET"])
def model_metadata():
    if not MODEL_METADATA:
        return jsonify({"error": "Model metadata not found — run train_model.py"}), 503
    return jsonify({**MODEL_METADATA, "recommender_ready": nn_model is not None})


@movies_bp.route("/api/summary-stats", methods=["GET"])
def summary_stats():
    if not CACHED_SUMMARY_STATS:
        return jsonify({"error": "Dataset not available"}), 500
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
    if df.empty or "hidden_gem_score" not in df.columns:
        return jsonify({"hidden_gems": [], "overrated": [], "all_points": []})

    limit = int(request.args.get("limit", 15))
    sample_size = int(request.args.get("sample_size", 1500))
    pool = df.dropna(subset=["hidden_gem_score", "popularity_percentile", "rating_percentile"])

    # JSON-safety fix: every field is explicitly coerced via safe_int /
    # safe_float. Raw pandas NaN from to_dict(orient="records") serializes
    # to the literal text `NaN` via Flask's jsonify — invalid JSON that
    # breaks JSON.parse in the browser. Building the dicts manually with
    # these helpers guarantees a JSON-clean payload every time.
    def point_rows(sub):
        return [
            {
                "title": r.title,
                "year": safe_int(r.release_year),
                "popularity": safe_float(r.popularity),
                "rating": safe_float(r.vote_average),
                "weighted_rating": safe_float(r.weighted_rating, 2),
                "vote_count": safe_int(r.vote_count),
                "popularity_percentile": safe_float(r.popularity_percentile, 1),
                "rating_percentile": safe_float(r.rating_percentile, 1),
            }
            for r in sub.itertuples()
        ]

    hidden_gems = pool.nlargest(limit, "hidden_gem_score")
    overrated = pool.nlargest(limit, "overrated_score")

    # all_points gets the same treatment — the previous version used
    # to_dict(orient="records") and then renamed release_year -> year
    # after the fact, which left NaN untouched in every other numeric
    # column and, worse, sometimes still in `year` itself if the rename
    # check ran against a numpy.float64 NaN in an older pandas. Explicit
    # iteration with safe_* helpers removes the whole class of bug.
    scatter_pool = pool.sample(n=min(sample_size, len(pool)), random_state=42)
    all_points = [
        {
            "title": r.title,
            "year": safe_int(r.release_year),
            "popularity": safe_float(r.popularity),
            "rating": safe_float(r.vote_average),
            "weighted_rating": safe_float(r.weighted_rating, 2),
            "vote_count": safe_int(r.vote_count),
            "popularity_percentile": safe_float(r.popularity_percentile, 1),
            "rating_percentile": safe_float(r.rating_percentile, 1),
        }
        for r in scatter_pool.itertuples()
    ]

    return jsonify({
        "hidden_gems": point_rows(hidden_gems),
        "overrated": point_rows(overrated),
        "all_points": all_points,
    })


def _best_by_votes(candidates_df):
    return candidates_df.nlargest(1, "vote_count") if "vote_count" in candidates_df.columns else candidates_df.head(1)


def find_source_movie(title: str):
    title_lower = title.lower()

    for pool, is_full in [(rec_index, False), (df, True)]:
        exact = pool[pool["title"].str.lower() == title_lower]
        if not exact.empty:
            chosen = _best_by_votes(exact if is_full else df[df["id"].isin(exact["id"])])
            return chosen if is_full else df[df["id"] == chosen.iloc[0]["id"]]

    for pool, is_full in [(rec_index, False), (df, True)]:
        starts_with = pool[pool["title"].str.lower().str.startswith(title_lower, na=False)]
        if not starts_with.empty:
            chosen = _best_by_votes(starts_with if is_full else df[df["id"].isin(starts_with["id"])])
            return chosen if is_full else df[df["id"] == chosen.iloc[0]["id"]]

    fuzzy_title = find_fuzzy_match(title)
    if fuzzy_title is not None:
        matches = df[df["title"] == fuzzy_title]
        if not matches.empty:
            return _best_by_votes(matches)

    return df.iloc[0:0]


def find_loose_matches(title: str, limit: int = 5):
    title_lower = title.lower()
    contains = df[df["title"].str.lower().str.contains(title_lower, na=False, regex=False)]
    if contains.empty:
        return []
    return contains.nlargest(limit, "vote_count")["title"].tolist()


def fetch_from_tmdb_live(title: str):
    if not TMDB_API_KEY:
        return None
    try:
        search_resp = requests.get(
            f"{TMDB_BASE_URL}/search/movie",
            params={"api_key": TMDB_API_KEY, "query": title},
            timeout=4,
        )
        search_resp.raise_for_status()
        results = search_resp.json().get("results", [])
        if not results:
            return None
        movie = results[0]

        genres = ",".join(TMDB_GENRE_MAP.get(gid, "") for gid in movie.get("genre_ids", []))

        keywords = ""
        try:
            kw_resp = requests.get(
                f"{TMDB_BASE_URL}/movie/{movie['id']}/keywords",
                params={"api_key": TMDB_API_KEY},
                timeout=4,
            )
            if kw_resp.ok:
                keywords = ",".join(k["name"] for k in kw_resp.json().get("keywords", []))
        except requests.RequestException:
            pass

        release_date = movie.get("release_date") or ""
        year = int(release_date[:4]) if release_date[:4].isdigit() else None

        return {
            "title": movie.get("title") or title,
            "year": year,
            "soup": f"{genres} {genres} {genres} {keywords} {movie.get('original_language', '')}",
        }
    except requests.RequestException as e:
        print(f"TMDB live lookup failed for '{title}': {e}")
        return None


def suggest_similar_titles(title: str, limit: int = 5):
    words = [w for w in title.lower().split() if len(w) > 2]
    if not words:
        return []
    pattern = "|".join(w for w in words)
    candidates = df[df["title"].str.contains(pattern, case=False, na=False, regex=True)]["title"]
    candidates = candidates.dropna().unique().tolist()[:5000]
    if not candidates:
        return []
    return difflib.get_close_matches(title, candidates, n=limit, cutoff=0.5)


@movies_bp.route("/api/recommend", methods=["GET"])
def recommend():
    if nn_model is None or vectorizer is None:
        return jsonify({"error": "Recommender not loaded — run train_model.py first"}), 503

    title = request.args.get("title", "").strip()
    n = int(request.args.get("n", 10))
    if not title:
        return jsonify({"error": "Pass a ?title= query param"}), 400

    source_row = find_source_movie(title)
    live_source = None
    source_id = None

    if not source_row.empty:
        row = source_row.iloc[0]
        soup = build_soup(row)
        source_title = row["title"]
        source_id = row["id"]
    else:
        live_source = fetch_from_tmdb_live(title)
        if live_source is None:
            suggestions = find_loose_matches(title, limit=5)
            for s in suggest_similar_titles(title, limit=5):
                if s not in suggestions and len(suggestions) < 5:
                    suggestions.append(s)
            error_msg = f"No movie found matching '{title}' in the dataset."
            if suggestions:
                error_msg += f" Did you mean: {', '.join(suggestions)}?"
            return jsonify({"error": error_msg, "suggestions": suggestions}), 404
        soup = live_source["soup"]
        source_title = live_source["title"]

    query_vec = vectorizer.transform([soup])
    distances, indices = nn_model.kneighbors(query_vec, n_neighbors=min(n * 3, len(rec_index)))

    candidates = rec_index.iloc[indices[0]].copy()
    candidates["similarity"] = 1 - distances[0]
    if source_id is not None:
        candidates = candidates[candidates["id"] != source_id]

    # --- Confidence threshold: drop low-signal neighbors ---
    candidates = candidates[candidates["similarity"] >= MIN_SIMILARITY]

    # --- Year enrichment: rec_index doesn't carry release_year ---
    year_lookup = df[["id", "release_year"]].drop_duplicates(subset=["id"])
    candidates = candidates.merge(year_lookup, on="id", how="left")

    if candidates.empty:
        return jsonify({
            "source_title": source_title,
            "source": "live_tmdb_lookup" if live_source else "local_dataset",
            "recommendations": [],
            "accuracy_note": (
                "No close genre/keyword match was found for this title in the "
                "dataset. Returning nothing is more honest than returning "
                "unrelated movies as guesses."
            ),
        })

    max_wr = candidates["weighted_rating"].max() or 1
    candidates["final_score"] = candidates["similarity"] * 0.7 + (candidates["weighted_rating"] / max_wr) * 0.3
    candidates = candidates.sort_values("final_score", ascending=False).head(n)

    # --- Absolute match % (no rescaling) ---
    candidates["match"] = (candidates["similarity"] * 100).clip(upper=100)

    return jsonify({
        "source_title": source_title,
        "source": "live_tmdb_lookup" if live_source else "local_dataset",
        "recommendations": [
            {
                "title": c.title,
                "year": safe_int(c.release_year),
                "match": safe_float(c.match, 1),
                "weighted_rating": safe_float(c.weighted_rating, 2),
                "vote_count": safe_int(c.vote_count),
            }
            for c in candidates.itertuples()
        ],
    })