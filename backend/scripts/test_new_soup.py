"""
Offline experiment: compare OLD soup vs NEW soup on a handful of movies.
Uses the same pool/vectorizer settings as train_model.py so the comparison
is apples-to-apples. Prints top-5 neighbors for each test query.
"""
import os
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

BACKEND = os.path.join(os.path.dirname(__file__), '..')
PARQUET = os.path.join(BACKEND, 'global_movies.parquet')

TEST_MOVIES = [
    "Inception",
    "The Dark Knight",
    "Toy Story",
    "The Godfather",
    "Spirited Away",
]


def build_soup_old(row) -> str:
    genres = str(row.get("genres", "")).replace(",", " ")
    keywords = str(row.get("keywords", "")).replace(",", " ")
    company = str(row.get("primary_production_company", ""))
    language = str(row.get("original_language", ""))
    return f"{genres} {genres} {genres} {keywords} {company} {language}"


def build_soup_new(row) -> str:
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


def evaluate(name, soup_fn, vectorizer_kwargs):
    print(f"\n{'='*70}")
    print(f"  {name}")
    print(f"{'='*70}")

    df = pd.read_parquet(PARQUET)
    min_votes = max(int(df["vote_count"].quantile(0.98)), 50)
    pool = df[df["vote_count"] >= min_votes].copy()
    if len(pool) > 30_000:
        pool = pool.nlargest(30_000, "vote_count")
    pool = pool.reset_index(drop=True)

    pool["soup"] = pool.apply(soup_fn, axis=1)
    vec = TfidfVectorizer(**vectorizer_kwargs)
    matrix = vec.fit_transform(pool["soup"])
    print(f"Vocab size: {matrix.shape[1]:,}  |  Pool: {len(pool):,}")

    # Precompute similarity one row at a time (fast for a few queries)
    for title in TEST_MOVIES:
        matches = pool[pool["title"] == title]
        if matches.empty:
            print(f"\n[skip] '{title}' not in pool")
            continue
        idx = matches.index[0]
        sims = cosine_similarity(matrix[idx], matrix).flatten()
        top = sims.argsort()[::-1][1:6]  # exclude self
        print(f"\n  Query: {title}")
        for t in top:
            print(f"    {sims[t]:.3f}  {pool.iloc[t]['title']}")


if __name__ == "__main__":
    # OLD: unigrams only, no sublinear_tf
    evaluate(
        "OLD SOUP (current)",
        build_soup_old,
        dict(stop_words="english", min_df=2, max_features=20000, ngram_range=(1, 1)),
    )

    # NEW: rich soup + bigrams + sublinear_tf
    evaluate(
        "NEW SOUP (proposed)",
        build_soup_new,
        dict(stop_words="english", min_df=2, max_features=20000, ngram_range=(1, 2), sublinear_tf=True),
    )