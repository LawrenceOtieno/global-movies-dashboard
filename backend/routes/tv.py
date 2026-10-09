"""
routes/tv.py — all TV-show endpoints, as a Flask Blueprint, parallel to
routes/movies.py but entirely independent: its own dataset
(global_tv_shows.parquet), its own trained recommender (tv_*.pkl files),
its own in-memory state. Nothing here reads or writes anything movies.py
touches, and nothing in movies.py changed to make room for this file.

KEY SCHEMA DIFFERENCES FROM MOVIES (real, not arbitrary):
- No revenue/budget exist for TV at all — company/network "performance" is
  ranked by show count + average rating instead (the same pattern already
  used for movies' production-countries-performance, which was never
  revenue-based to begin with).
- No `keywords` column — the recommender's soup uses `created_by` instead
  (see train_tv_model.py).
- Title field is `name`, not `title`; first-air info instead of release info.
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

tv_bp = Blueprint("tv", __name__, url_prefix="/api/tv")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_BACKEND_DIR = os.path.dirname(BASE_DIR)

TMDB_TV_GENRE_MAP = fetch_tmdb_genre_map("tv")
if TMDB_TV_GENRE_MAP:
    print(f"TV TMDB live lookup enabled ({len(TMDB_TV_GENRE_MAP)} genres loaded).")

PARQUET_PATH = os.path.join(PROJECT_BACKEND_DIR, "..", "global_tv_shows.parquet")
if not os.path.exists(PARQUET_PATH):
    PARQUET_PATH = os.path.join(PROJECT_BACKEND_DIR, "global_tv_shows.parquet")

VECTORIZER_PATH = os.path.join(PROJECT_BACKEND_DIR, "tv_tfidf_vectorizer.pkl")
NN_MODEL_PATH = os.path.join(PROJECT_BACKEND_DIR, "tv_recommender_nn.pkl")
REC_INDEX_PATH = os.path.join(PROJECT_BACKEND_DIR, "tv_recommender_index.parquet")
METADATA_PATH = os.path.join(PROJECT_BACKEND_DIR, "tv_model_metadata.json")

# --- Recommendation quality floor (mirrors routes/movies.py) ---
MIN_SIMILARITY = 0.15

try:
    df = pd.read_parquet(PARQUET_PATH)
except Exception as e:
    print(f"Warning: Could not load TV dataset parquet: {e}")
    df = pd.DataFrame()

try:
    vectorizer = joblib.load(VECTORIZER_PATH)
    nn_model = joblib.load(NN_MODEL_PATH)
    rec_index = pd.read_parquet(REC_INDEX_PATH)
except Exception as e:
    print(f"Warning: Could not load TV recommender: {e}")
    vectorizer = None
    nn_model = None
    rec_index = pd.DataFrame()

try:
    with open(METADATA_PATH) as f:
        MODEL_METADATA = json.load(f)
except FileNotFoundError:
    MODEL_METADATA = {}
    print("Warning: tv_model_metadata.json not found — run train_tv_model.py first.")


def safe_int(value):
    """Convert a possibly-NaN pandas/numpy numeric to a Python int, or None.
    JSON-safety guard: raw pandas NaN serializes to the literal text `NaN`
    via Flask's jsonify, which is NOT valid JSON and blows up JSON.parse
    on the frontend. Every scalar that goes into a response goes through
    one of these helpers."""
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


# --- Fuzzy title matcher (typo tolerance for /api/tv/recommend) ---
FUZZY_NAMES = []
fuzzy_vectorizer = None
fuzzy_matrix = None
if not df.empty:
    _t0 = time.time()
    FUZZY_NAMES = df["name"].dropna().unique().tolist()
    fuzzy_vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
    fuzzy_matrix = fuzzy_vectorizer.fit_transform(FUZZY_NAMES)
    print(f"Fuzzy title matcher built: {len(FUZZY_NAMES):,} distinct show names "
          f"in {time.time() - _t0:.1f}s.")


def find_fuzzy_match(title: str, threshold: float = 0.70):
    if fuzzy_vectorizer is None or not FUZZY_NAMES:
        return None
    query_vec = fuzzy_vectorizer.transform([title])
    sims = cosine_similarity(query_vec, fuzzy_matrix)[0]
    best_idx = sims.argmax()
    if sims[best_idx] >= threshold:
        return FUZZY_NAMES[best_idx]
    return None


CACHED_SUMMARY_STATS = {}
CACHED_GENRE_DISTRIBUTION = {"genres": [], "uncategorized_count": 0, "uncategorized_percentage": 0.0}
CACHED_DECADE_TRENDS = []
CACHED_NETWORK_PERFORMANCE = []
CACHED_COMPANY_PERFORMANCE = []
CACHED_COUNTRY_PERFORMANCE = []
CACHED_RANKINGS = {"top": [], "bottom": []}

if not df.empty:
    print("Precomputing cached TV dashboard data...")

    total_shows = int(len(df))

    rated = df[df["vote_count"] > 0]
    avg_rating = float(rated["vote_average"].mean()) if not rated.empty else 0.0

    timed = df[df["episode_run_time"] > 0]
    avg_episode_runtime = float(timed["episode_run_time"].mean()) if not timed.empty else 0.0

    highly_rated = int((df["vote_average"] >= 7.0).sum())

    # fillna("") BEFORE astype(str) matters here: missing values in an
    # object-dtype column can surface as actual Python None when read back
    # from parquet, and str(None) == "None" — a real string that then slips
    # straight past a `!= ""` filter and, with enough missing-genre shows
    # behind it, can out-rank every real genre. This is exactly why "Top
    # Genre by Show Count" was showing "None" with 66,230 shows.
    genre_count_df = df[["genres"]].copy()
    genre_count_df["genres"] = genre_count_df["genres"].fillna("").astype(str).replace({"nan": "", "None": ""}).str.split(",")
    genre_exploded = genre_count_df.explode("genres")
    genre_exploded["genres"] = genre_exploded["genres"].str.strip()
    genre_exploded = genre_exploded[genre_exploded["genres"] != ""]
    genre_show_counts = genre_exploded["genres"].value_counts()
    top_genre_by_count = None
    if not genre_show_counts.empty:
        top_genre_by_count = [genre_show_counts.index[0], int(genre_show_counts.iloc[0])]

    CACHED_SUMMARY_STATS = {
        "total_shows": total_shows,
        "average_rating": round(avg_rating, 2),
        "average_episode_runtime_minutes": round(avg_episode_runtime, 1),
        "highly_rated_count": highly_rated,
        "other_count": total_shows - highly_rated,
        "top_genre_by_show_count": top_genre_by_count,
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

    min_votes_for_quality = max(int(df["vote_count"].quantile(0.90)), 50)
    quality_pool = df[df["vote_count"] >= min_votes_for_quality]

    if "primary_network" in df.columns:
        networks = (
            quality_pool[quality_pool["primary_network"].notna() & (quality_pool["primary_network"] != "nan")]
            .groupby("primary_network")
            .agg(show_count=("vote_average", "count"), avg_rating=("vote_average", "mean"))
            .reset_index()
            .sort_values(by="show_count", ascending=False)
            .head(8)
            .sort_values(by="avg_rating", ascending=False)
        )
        networks.columns = ["network", "show_count", "avg_rating"]
        networks["avg_rating"] = networks["avg_rating"].round(2)
        CACHED_NETWORK_PERFORMANCE = networks.to_dict(orient="records")

    total_production_companies = 0
    if "primary_production_company" in df.columns:
        valid_companies = quality_pool[quality_pool["primary_production_company"].notna()
                                        & (quality_pool["primary_production_company"] != "nan")]
        total_production_companies = int(valid_companies["primary_production_company"].nunique())
        companies = (
            valid_companies
            .groupby("primary_production_company")
            .agg(show_count=("vote_average", "count"), avg_rating=("vote_average", "mean"))
            .reset_index()
            .sort_values(by="show_count", ascending=False)
            .head(5)
            .sort_values(by="avg_rating", ascending=False)
        )
        companies.columns = ["production_company", "show_count", "avg_rating"]
        companies["avg_rating"] = companies["avg_rating"].round(2)
        CACHED_COMPANY_PERFORMANCE = companies.to_dict(orient="records")
    CACHED_SUMMARY_STATS["total_production_companies"] = total_production_companies

    if "primary_production_country" in df.columns:
        countries = (
            quality_pool[quality_pool["primary_production_country"].notna()
                          & (quality_pool["primary_production_country"] != "nan")]
            .groupby("primary_production_country")
            .agg(show_count=("vote_average", "count"), avg_rating=("vote_average", "mean"))
            .reset_index()
            .sort_values(by="show_count", ascending=False)
            .head(8)
            .sort_values(by="avg_rating", ascending=False)
        )
        countries.columns = ["production_country", "show_count", "avg_rating"]
        countries["avg_rating"] = countries["avg_rating"].round(2)
        CACHED_COUNTRY_PERFORMANCE = countries.to_dict(orient="records")

    if "weighted_rating" in df.columns:
        ranking_pool = quality_pool[
            (quality_pool["number_of_seasons"] > 0) & quality_pool["first_air_year"].notna()
        ]

        def _ranking_rows(sub):
            return [
                {
                    "id": safe_int(r.id),
                    "name": safe_str(r.name),
                    "year": safe_int(r.first_air_year),
                    "rating": safe_float(r.vote_average),
                    "weighted_rating": safe_float(r.weighted_rating, 2),
                    "vote_count": safe_int(r.vote_count),
                    "seasons": safe_int(r.number_of_seasons),
                }
                for r in sub.itertuples()
            ]

        cols = ["id", "name", "first_air_year", "vote_average", "weighted_rating", "vote_count", "number_of_seasons"]
        if not ranking_pool.empty:
            CACHED_RANKINGS = {
                "top": _ranking_rows(ranking_pool.nlargest(10, "weighted_rating")[cols]),
                "bottom": _ranking_rows(ranking_pool.nsmallest(10, "weighted_rating")[cols]),
            }
        print(f"  TV rankings pool: {len(ranking_pool):,} shows "
              f"(vote_count >= {min_votes_for_quality}, seasons > 0, has air date).")

        if TMDB_API_KEY:
            refreshed = 0
            for side in ("top", "bottom"):
                for show in CACHED_RANKINGS[side]:
                    if show.get("id") is None:
                        continue
                    try:
                        resp = requests.get(
                            f"{TMDB_BASE_URL}/tv/{show['id']}",
                            params={"api_key": TMDB_API_KEY},
                            timeout=4,
                        )
                        if resp.ok:
                            live_seasons = resp.json().get("number_of_seasons")
                            if live_seasons is not None and live_seasons != show["seasons"]:
                                show["seasons"] = live_seasons
                                show["seasons_live_updated"] = True
                                refreshed += 1
                    except requests.RequestException:
                        pass  # keep the local (possibly stale) value
            print(f"  Live TMDB season refresh: {refreshed} of "
                  f"{len(CACHED_RANKINGS['top']) + len(CACHED_RANKINGS['bottom'])} ranked shows updated.")

        for side in ("top", "bottom"):
            for show in CACHED_RANKINGS[side]:
                show.pop("id", None)

    print("TV precomputation done.")


def build_tv_soup(row) -> str:
    genres = str(row.get("genres", "")).replace(",", " ")
    created_by = str(row.get("created_by", "")).replace(",", " ")
    network = str(row.get("primary_network", ""))
    company = str(row.get("primary_production_company", ""))
    language = str(row.get("original_language", ""))
    return f"{genres} {genres} {genres} {created_by} {network} {company} {language}"


@tv_bp.route("/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "healthy",
        "total_shows": len(df),
        "recommender_ready": nn_model is not None and vectorizer is not None,
    })


@tv_bp.route("/model-metadata", methods=["GET"])
def model_metadata():
    if not MODEL_METADATA:
        return jsonify({"error": "TV model metadata not found — run train_tv_model.py"}), 503
    return jsonify({**MODEL_METADATA, "recommender_ready": nn_model is not None})


@tv_bp.route("/summary-stats", methods=["GET"])
def summary_stats():
    if not CACHED_SUMMARY_STATS:
        return jsonify({"error": "TV dataset not available"}), 500
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
    if df.empty or "hidden_gem_score" not in df.columns:
        return jsonify({"hidden_gems": [], "overrated": [], "all_points": []})

    limit = int(request.args.get("limit", 15))
    sample_size = int(request.args.get("sample_size", 1500))
    pool = df.dropna(subset=["hidden_gem_score", "popularity_percentile", "rating_percentile"])

    # JSON-safety fix: every field is explicitly coerced via safe_int /
    # safe_float. Raw pandas NaN from to_dict(orient="records") serializes
    # to the literal text `NaN` via Flask's jsonify — invalid JSON that
    # breaks JSON.parse in the browser (this was exactly what killed both
    # scatter charts before). Manual iteration guarantees a JSON-clean
    # payload every time.
    def point_rows(sub):
        return [
            {
                "name": safe_str(r.name),
                "year": safe_int(r.first_air_year),
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

    scatter_pool = pool.sample(n=min(sample_size, len(pool)), random_state=42)
    all_points = [
        {
            "name": safe_str(r.name),
            "year": safe_int(r.first_air_year),
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


def find_source_show(title: str):
    title_lower = title.lower()

    for pool, is_full in [(rec_index, False), (df, True)]:
        exact = pool[pool["name"].str.lower() == title_lower]
        if not exact.empty:
            chosen = _best_by_votes(exact if is_full else df[df["id"].isin(exact["id"])])
            return chosen if is_full else df[df["id"] == chosen.iloc[0]["id"]]

    for pool, is_full in [(rec_index, False), (df, True)]:
        starts_with = pool[pool["name"].str.lower().str.startswith(title_lower, na=False)]
        if not starts_with.empty:
            chosen = _best_by_votes(starts_with if is_full else df[df["id"].isin(starts_with["id"])])
            return chosen if is_full else df[df["id"] == chosen.iloc[0]["id"]]

    fuzzy_name = find_fuzzy_match(title)
    if fuzzy_name is not None:
        matches = df[df["name"] == fuzzy_name]
        if not matches.empty:
            return _best_by_votes(matches)

    return df.iloc[0:0]


def find_loose_matches(title: str, limit: int = 5):
    title_lower = title.lower()
    contains = df[df["name"].str.lower().str.contains(title_lower, na=False, regex=False)]
    if contains.empty:
        return []
    return contains.nlargest(limit, "vote_count")["name"].tolist()


def fetch_from_tmdb_tv_live(title: str):
    if not TMDB_API_KEY:
        return None
    try:
        search_resp = requests.get(
            f"{TMDB_BASE_URL}/search/tv",
            params={"api_key": TMDB_API_KEY, "query": title},
            timeout=4,
        )
        search_resp.raise_for_status()
        results = search_resp.json().get("results", [])
        if not results:
            return None
        show = results[0]

        genres = ",".join(TMDB_TV_GENRE_MAP.get(gid, "") for gid in show.get("genre_ids", []))

        first_air_date = show.get("first_air_date") or ""
        year = int(first_air_date[:4]) if first_air_date[:4].isdigit() else None

        return {
            "name": show.get("name") or title,
            "year": year,
            "soup": f"{genres} {genres} {genres} {show.get('original_language', '')}",
        }
    except requests.RequestException as e:
        print(f"TMDB TV live lookup failed for '{title}': {e}")
        return None


def suggest_similar_titles(title: str, limit: int = 5):
    words = [w for w in title.lower().split() if len(w) > 2]
    if not words:
        return []
    pattern = "|".join(w for w in words)
    candidates = df[df["name"].str.contains(pattern, case=False, na=False, regex=True)]["name"]
    candidates = candidates.dropna().unique().tolist()[:5000]
    if not candidates:
        return []
    return difflib.get_close_matches(title, candidates, n=limit, cutoff=0.5)


@tv_bp.route("/recommend", methods=["GET"])
def recommend():
    """Same shape and logic as /api/recommend for movies — exact-match /
    starts-with tiers only auto-select; loose substring matches become
    suggestions, not silent answers; live TMDB TV fallback as a last resort;
    match % absolute (not rescaled). See routes/movies.py's recommend() for
    the full reasoning behind each of these choices — identical here."""
    if nn_model is None or vectorizer is None:
        return jsonify({"error": "TV recommender not loaded — run train_tv_model.py first"}), 503

    title = request.args.get("title", "").strip()
    n = int(request.args.get("n", 10))
    if not title:
        return jsonify({"error": "Pass a ?title= query param"}), 400

    source_row = find_source_show(title)
    live_source = None
    source_id = None

    if not source_row.empty:
        row = source_row.iloc[0]
        soup = build_tv_soup(row)
        source_title = row["name"]
        source_id = row["id"]
    else:
        live_source = fetch_from_tmdb_tv_live(title)
        if live_source is None:
            suggestions = find_loose_matches(title, limit=5)
            for s in suggest_similar_titles(title, limit=5):
                if s not in suggestions and len(suggestions) < 5:
                    suggestions.append(s)
            error_msg = f"No show found matching '{title}' in the dataset."
            if suggestions:
                error_msg += f" Did you mean: {', '.join(suggestions)}?"
            return jsonify({"error": error_msg, "suggestions": suggestions}), 404
        soup = live_source["soup"]
        source_title = live_source["name"]

    query_vec = vectorizer.transform([soup])
    distances, indices = nn_model.kneighbors(query_vec, n_neighbors=min(n * 3, len(rec_index)))

    candidates = rec_index.iloc[indices[0]].copy()
    candidates["similarity"] = 1 - distances[0]
    if source_id is not None:
        candidates = candidates[candidates["id"] != source_id]

    # --- Confidence threshold (see movies.py for full reasoning) ---
    candidates = candidates[candidates["similarity"] >= MIN_SIMILARITY]

    # --- Year enrichment: tv_recommender_index.parquet doesn't carry
    # first_air_year; join back to the full df on id ---
    year_lookup = df[["id", "first_air_year"]].drop_duplicates(subset=["id"])
    candidates = candidates.merge(year_lookup, on="id", how="left")

    if candidates.empty:
        return jsonify({
            "source_title": source_title,
            "source": "live_tmdb_lookup" if live_source else "local_dataset",
            "recommendations": [],
            "accuracy_note": (
                "No close genre/creator/network match was found for this show "
                "in the dataset. Returning nothing is more honest than "
                "returning unrelated shows as guesses."
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
                "name": safe_str(c.name),
                "year": safe_int(c.first_air_year),
                "match": safe_float(c.match, 1),
                "weighted_rating": safe_float(c.weighted_rating, 2),
                "vote_count": safe_int(c.vote_count),
            }
            for c in candidates.itertuples()
        ],
    })