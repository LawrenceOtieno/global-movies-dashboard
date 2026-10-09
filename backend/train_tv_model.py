"""
train_tv_model.py — builds the TV-show recommendation engine, mirroring
train_model.py's approach for movies. Entirely separate pipeline: reads
global_tv_shows.parquet, writes tv_-prefixed model files. Never touches any
movie file, and running this never needs to be paired with re-running
train_model.py.

WHAT'S DIFFERENT FROM THE MOVIE VERSION (real schema differences, not
arbitrary choices):
- No `keywords` column exists in this TV dataset at all — `created_by` is
  used in its place in the recommender's soup. Prolific creators/showrunners
  (Shonda Rhimes, Greg Berlanti, etc.) tend to make similarly-styled shows,
  so it's a reasonable stand-in signal, though a different kind of signal
  than plot keywords.
- Soup uses primary_network in addition to primary_production_company —
  network (HBO vs. Nickelodeon vs. Adult Swim) is a much stronger style
  signal for TV than it is for movies.
- No revenue/budget exist for TV, so there's no equivalent of the movie
  pipeline's revenue-based anything here.

Run:
    pip install -r requirements.txt
    python train_tv_model.py
    python app.py
"""

import json
import os

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARQUET_PATH = os.path.join(BASE_DIR, "..", "global_tv_shows.parquet")

print("Loading TV dataset...")
df = pd.read_parquet(PARQUET_PATH)
print(f"Loaded {len(df):,} rows.")

# Same robust floor-and-cap approach as the movie pipeline — computed fresh
# from whatever's actually in this file rather than assumed, since the real
# vote_count distribution shape won't necessarily match the movie dataset's.
MIN_VOTES_FOR_RECOMMENDER = max(int(df["vote_count"].quantile(0.98)), 50)
MAX_RECOMMENDER_POOL = 30_000
MIN_VOTES_FOR_TENSION = max(int(df["vote_count"].quantile(0.60)), 20)
MIN_VOTES_FOR_RANKING = max(int(df["vote_count"].quantile(0.90)), 50)

print(f"Computed thresholds: MIN_VOTES_FOR_RECOMMENDER={MIN_VOTES_FOR_RECOMMENDER}, "
      f"MIN_VOTES_FOR_TENSION={MIN_VOTES_FOR_TENSION}, MIN_VOTES_FOR_RANKING={MIN_VOTES_FOR_RANKING}")

# --- Weighted (Bayesian) rating — identical formula to the movie pipeline ---
C = df["vote_average"].mean()
m = df["vote_count"].quantile(0.90)
df["weighted_rating"] = (
    df["vote_count"] / (df["vote_count"] + m) * df["vote_average"]
    + m / (df["vote_count"] + m) * C
)

# --- Cult-classic / overrated percentile scores (same idea as movies) ---
tension_pool = df[df["vote_count"] >= MIN_VOTES_FOR_TENSION].copy()
tension_pool["popularity_percentile"] = tension_pool["popularity"].rank(pct=True) * 100
tension_pool["rating_percentile"] = tension_pool["weighted_rating"].rank(pct=True) * 100
tension_pool["hidden_gem_score"] = tension_pool["rating_percentile"] - tension_pool["popularity_percentile"]
tension_pool["overrated_score"] = tension_pool["popularity_percentile"] - tension_pool["rating_percentile"]

df = df.merge(
    tension_pool[["id", "popularity_percentile", "rating_percentile", "hidden_gem_score", "overrated_score"]],
    on="id",
    how="left",
)

# --- Content-based recommender ---
rec_pool = df[df["vote_count"] >= MIN_VOTES_FOR_RECOMMENDER]
if len(rec_pool) > MAX_RECOMMENDER_POOL:
    rec_pool = rec_pool.nlargest(MAX_RECOMMENDER_POOL, "vote_count")
rec_pool = rec_pool.reset_index(drop=True)
print(f"Building recommender over {len(rec_pool):,} shows "
      f"(vote_count >= {MIN_VOTES_FOR_RECOMMENDER}, capped at {MAX_RECOMMENDER_POOL:,}).")


def build_tv_soup(row) -> str:
    genres = str(row.get("genres", "")).replace(",", " ")
    created_by = str(row.get("created_by", "")).replace(",", " ")
    network = str(row.get("primary_network", ""))
    company = str(row.get("primary_production_company", ""))
    language = str(row.get("original_language", ""))
    return f"{genres} {genres} {genres} {created_by} {network} {company} {language}"


rec_pool["soup"] = rec_pool.apply(build_tv_soup, axis=1)

vectorizer = TfidfVectorizer(stop_words="english", min_df=2, max_features=20_000)
tfidf_matrix = vectorizer.fit_transform(rec_pool["soup"])
print(f"TF-IDF matrix: {tfidf_matrix.shape[0]:,} shows x {tfidf_matrix.shape[1]:,} terms.")

nn_model = NearestNeighbors(metric="cosine", algorithm="brute", n_neighbors=31)
nn_model.fit(tfidf_matrix)

joblib.dump(vectorizer, os.path.join(BASE_DIR, "tv_tfidf_vectorizer.pkl"))
joblib.dump(nn_model, os.path.join(BASE_DIR, "tv_recommender_nn.pkl"), compress=3)
rec_pool[["id", "name", "weighted_rating", "vote_count", "popularity"]].to_parquet(
    os.path.join(BASE_DIR, "tv_recommender_index.parquet")
)

df.to_parquet(PARQUET_PATH, compression="zstd", compression_level=15)

metadata = {
    "model_type": "content-based TV recommender (TF-IDF + cosine kNN)",
    "recommender_show_count": int(len(rec_pool)),
    "recommender_vocab_size": int(tfidf_matrix.shape[1]),
    "min_votes_for_recommender": MIN_VOTES_FOR_RECOMMENDER,
    "min_votes_for_tension": MIN_VOTES_FOR_TENSION,
    "min_votes_for_ranking": MIN_VOTES_FOR_RANKING,
    "weighted_rating_formula": "WR = v/(v+m)*R + m/(v+m)*C",
    "weighted_rating_m_90th_pct_vote_count": round(float(m), 1),
    "weighted_rating_C_mean_vote_average": round(float(C), 3),
    "total_shows_in_dataset": int(len(df)),
}
with open(os.path.join(BASE_DIR, "tv_model_metadata.json"), "w") as f:
    json.dump(metadata, f, indent=2)

print("\nSaved: tv_tfidf_vectorizer.pkl, tv_recommender_nn.pkl, tv_recommender_index.parquet, tv_model_metadata.json")
print(json.dumps(metadata, indent=2))
