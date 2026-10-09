"""
train_model.py — builds the recommendation engine used by app.py's
/api/recommend, plus the weighted-rating scores used by /api/cult-classics.

WHY THIS REPLACES THE OLD HIT/MISS CLASSIFIER:
The old model tried to predict whether a movie would be a hit from
pre-release features, and — even honestly reported — never beat baseline by
much. A recommender is a better fit for what this dataset is actually good
at: real TMDB ratings, real vote counts, real genre/keyword/company data,
none of it synthetic.

WHY NO DIRECTOR / LEAD-ACTOR FEATURES:
TMDB_movie_dataset_v11 doesn't have them. The categorical signal here is
genres, keywords, production_companies and original_language — so that's
what the recommender is built on.

WHAT IT COMPUTES:
1. A content-based recommender: each movie becomes a TF-IDF "soup" of its
   genres + keywords + production companies + language, and recommendations
   are the nearest neighbors by cosine similarity, re-ranked by a weighted
   rating so a merely-similar-but-bad movie doesn't outrank a merely-similar
   -but-excellent one.

2. weighted_rating (IMDB-style Bayesian average): raw vote_average is
   unreliable for movies with few votes (a 10.0 from 3 voters means nothing).
   weighted_rating pulls low-vote-count movies toward the dataset mean,
   proportional to how few votes they have:

       WR = (v / (v + m)) * R + (m / (v + m)) * C

   where v = vote_count, R = vote_average, m = the 90th-percentile vote
   count (movies need to clear this bar for their rating to be trusted
   mostly on its own), C = the mean vote_average across the dataset.

3. Cult-classic / overrated percentile scores, used directly by
   /api/cult-classics:
   - popularity_percentile: where a movie's popularity ranks (0-100)
   - rating_percentile: where its weighted_rating ranks (0-100)
   - hidden_gem_score = rating_percentile - popularity_percentile
     (high = a movie people loved that never got much attention)
   - overrated_score = popularity_percentile - rating_percentile
     (high = a movie that got a lot of attention but underwhelmed)
   Only movies with vote_count >= MIN_VOTES_FOR_TENSION are eligible for
   either — otherwise "hidden gem" just means "nobody rated it."

Run:
    pip install -r requirements.txt
    python train_model.py
    python app.py
"""

import json
import os

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARQUET_PATH = os.path.join(BASE_DIR, "..", "global_movies.parquet")

print("Loading dataset...")
df = pd.read_parquet(PARQUET_PATH)
print(f"Loaded {len(df):,} rows.")

# Vote-count thresholds, computed from the loaded data with a hard floor and
# (for the recommender) a hard cap.
#
# TMDB's full dataset turns out to be dominated by a huge cluster of
# vote_count == 0 placeholder entries — a plain percentile (e.g. "median")
# can land IN that cluster and effectively apply no filter at all, which is
# what let both the recommender and the rankings get flooded with junk. A
# high percentile PLUS a floor guards against that regardless of how skewed
# the distribution turns out to be.
#
# MIN_VOTES_FOR_RECOMMENDER: only the most-voted slice of the dataset
# qualifies — both for recommendation quality (better-populated metadata)
# and for query speed. MAX_RECOMMENDER_POOL then hard-caps the pool size
# directly, so NearestNeighbors queries stay fast (a few tens of thousands of
# rows, brute-force cosine over sparse TF-IDF, is near-instant) no matter how
# large the source dataset is.
MIN_VOTES_FOR_RECOMMENDER = max(int(df["vote_count"].quantile(0.98)), 50)
MAX_RECOMMENDER_POOL = 30_000

# MIN_VOTES_FOR_TENSION: a lower bar than the recommender's, so genuinely
# under-the-radar movies can still register as hidden gems — but still well
# clear of the zero-vote placeholder cluster.
MIN_VOTES_FOR_TENSION = max(int(df["vote_count"].quantile(0.60)), 20)

# MIN_VOTES_FOR_RANKING: rankings need the highest bar of the three — this
# feeds "Top/Bottom 10 movies," and without a real floor here, nsmallest()
# just pulls arbitrarily from the enormous tied cluster of zero-vote,
# zero-revenue placeholder rows (all of which collapse to the exact same
# weighted_rating == dataset mean, since they contribute no real signal).
MIN_VOTES_FOR_RANKING = max(int(df["vote_count"].quantile(0.90)), 50)

print(f"Computed thresholds from this dataset: "
      f"MIN_VOTES_FOR_RECOMMENDER={MIN_VOTES_FOR_RECOMMENDER}, "
      f"MIN_VOTES_FOR_TENSION={MIN_VOTES_FOR_TENSION}, "
      f"MIN_VOTES_FOR_RANKING={MIN_VOTES_FOR_RANKING}")

# --- Weighted (Bayesian) rating, computed over the full dataset ---
C = df["vote_average"].mean()
m = df["vote_count"].quantile(0.90)
df["weighted_rating"] = (
    df["vote_count"] / (df["vote_count"] + m) * df["vote_average"]
    + m / (df["vote_count"] + m) * C
)

# --- Cult-classic / overrated percentile scores ---
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
print(f"Building recommender over {len(rec_pool):,} movies "
      f"(vote_count >= {MIN_VOTES_FOR_RECOMMENDER}, capped at {MAX_RECOMMENDER_POOL:,}).")


def build_soup(row) -> str:
    genres = str(row.get("genres", "")).replace(",", " ")
    keywords = str(row.get("keywords", "")).replace(",", " ")
    # Primary company only (not the full comma-separated list) — a single
    # clean token per movie instead of a noisy multi-company string, which
    # keeps the vocabulary tighter and similarity scores more meaningful.
    company = str(row.get("primary_production_company", ""))
    language = str(row.get("original_language", ""))
    return f"{genres} {genres} {genres} {keywords} {company} {language}"
    # genres repeated 3x to weight it heavily above keywords/company/language
    # in the TF-IDF space — genre similarity should dominate the match.


rec_pool["soup"] = rec_pool.apply(build_soup, axis=1)

vectorizer = TfidfVectorizer(stop_words="english", min_df=2, max_features=20_000)
tfidf_matrix = vectorizer.fit_transform(rec_pool["soup"])
print(f"TF-IDF matrix: {tfidf_matrix.shape[0]:,} movies x {tfidf_matrix.shape[1]:,} terms.")

nn_model = NearestNeighbors(metric="cosine", algorithm="brute", n_neighbors=31)
nn_model.fit(tfidf_matrix)

joblib.dump(vectorizer, os.path.join(BASE_DIR, "tfidf_vectorizer.pkl"))
joblib.dump(nn_model, os.path.join(BASE_DIR, "recommender_nn.pkl"), compress=3)
rec_pool[["id", "title", "weighted_rating", "vote_count", "popularity"]].to_parquet(
    os.path.join(BASE_DIR, "recommender_index.parquet")
)

# Overwrite the full dataset with its new derived columns so app.py doesn't
# need to recompute weighted_rating / percentiles on every request.
df.to_parquet(PARQUET_PATH, compression="zstd", compression_level=15)

metadata = {
    "model_type": "content-based recommender (TF-IDF + cosine kNN)",
    "recommender_movie_count": int(len(rec_pool)),
    "recommender_vocab_size": int(tfidf_matrix.shape[1]),
    "min_votes_for_recommender": MIN_VOTES_FOR_RECOMMENDER,
    "min_votes_for_tension": MIN_VOTES_FOR_TENSION,
    "min_votes_for_ranking": MIN_VOTES_FOR_RANKING,
    "weighted_rating_formula": "WR = v/(v+m)*R + m/(v+m)*C",
    "weighted_rating_m_90th_pct_vote_count": round(float(m), 1),
    "weighted_rating_C_mean_vote_average": round(float(C), 3),
    "total_movies_in_dataset": int(len(df)),
}
with open(os.path.join(BASE_DIR, "model_metadata.json"), "w") as f:
    json.dump(metadata, f, indent=2)

print("\nSaved: tfidf_vectorizer.pkl, recommender_nn.pkl, recommender_index.parquet, model_metadata.json")
print(json.dumps(metadata, indent=2))
