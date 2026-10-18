"""
Retrains movie TF-IDF with enriched soup + 1536 dims (Upstash free tier).
"""
import os
import json
import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

BACKEND = os.path.join(os.path.dirname(__file__), '..')
PARQUET = os.path.join(BACKEND, 'global_movies.parquet')

MAX_FEATURES = 1536


def build_soup(row) -> str:
    genres = str(row.get("genres", "")).replace(",", " ")
    keywords = str(row.get("keywords", "")).replace(",", " ")
    company = str(row.get("primary_production_company", ""))
    countries = str(row.get("production_countries", "")).replace(",", " ")
    languages = str(row.get("spoken_languages", "")).replace(",", " ")
    original_title = str(row.get("original_title", ""))
    return (
        f"{genres} {genres} {genres} "
        f"{keywords} "
        f"{company} "
        f"{countries} "
        f"{languages} "
        f"{original_title} {original_title}"
    )


print("Loading parquet...")
df = pd.read_parquet(PARQUET)
print(f"  {len(df):,} rows loaded")

min_votes = max(int(df["vote_count"].quantile(0.98)), 50)
pool = df[df["vote_count"] >= min_votes].copy()
if len(pool) > 30_000:
    pool = pool.nlargest(30_000, "vote_count")
pool = pool.reset_index(drop=True)
print(f"  Filtered pool: {len(pool):,} rows (min_votes={min_votes})")

print("Building soup...")
pool["soup"] = pool.apply(build_soup, axis=1)

print(f"Fitting vectorizer (max_features={MAX_FEATURES})...")
vectorizer = TfidfVectorizer(
    stop_words="english",
    min_df=2,
    max_features=MAX_FEATURES,
    ngram_range=(1, 2),
    sublinear_tf=True,
)
matrix = vectorizer.fit_transform(pool["soup"])
print(f"  Matrix: {matrix.shape}  (dimensions = {matrix.shape[1]})")

joblib.dump(vectorizer, os.path.join(BACKEND, "tfidf_vectorizer_v2.pkl"))
print(f"  Saved: tfidf_vectorizer_v2.pkl")

pool[["id", "title", "weighted_rating"]].to_parquet(
    os.path.join(BACKEND, "movie_pool_v2.parquet")
)
print(f"  Saved: movie_pool_v2.parquet")

meta = {
    "vocab_size": int(matrix.shape[1]),
    "pool_size": int(len(pool)),
    "min_votes": int(min_votes),
    "max_features": MAX_FEATURES,
    "ngram_range": [1, 2],
}
with open(os.path.join(BACKEND, "movie_model_v2_meta.json"), "w") as f:
    json.dump(meta, f, indent=2)
print("\nDone. Metadata:")
print(json.dumps(meta, indent=2))