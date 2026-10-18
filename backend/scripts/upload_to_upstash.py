"""
Uploads movie vectors to Upstash Vector. TV stays on Pinecone (untouched).

Resumable: skips vectors already present in Upstash, so re-runs after the
daily write limit resets only upload the missing ones.
"""
import os
import time
import joblib
import pandas as pd
from dotenv import load_dotenv
from upstash_vector import Index

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
BACKEND = os.path.join(os.path.dirname(__file__), '..')

BATCH = 20

index = Index(
    url=os.getenv('UPSTASH_VECTOR_REST_URL'),
    token=os.getenv('UPSTASH_VECTOR_REST_TOKEN'),
)


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


def get_existing_ids(ids_batch):
    """Returns the subset of ids_batch that already exist in Upstash."""
    try:
        results = index.fetch(ids=ids_batch)
        # upstash-vector returns a list of Vector objects (or None entries)
        existing = set()
        for r in results:
            if r is not None:
                existing.add(r.id)
        return existing
    except Exception as e:
        print(f"  ⚠️  fetch() failed: {str(e)[:80]}. Assuming none exist.")
        return set()


def upload_movies():
    print("\n=== Uploading movies to Upstash ===")
    df = pd.read_parquet(os.path.join(BACKEND, 'global_movies.parquet'))
    vectorizer = joblib.load(os.path.join(BACKEND, 'tfidf_vectorizer_v2.pkl'))
    print(f"  Loaded {len(df):,} rows | vocab {len(vectorizer.vocabulary_)}")

    min_votes = max(int(df["vote_count"].quantile(0.98)), 50)
    df = df[df["vote_count"] >= min_votes].copy()
    if len(df) > 30_000:
        df = df.nlargest(30_000, "vote_count")
    df = df.reset_index(drop=True)
    print(f"  Filtered pool: {len(df):,} rows")

    df["soup"] = df.apply(build_soup, axis=1)
    print("  Vectorizing...")
    matrix = vectorizer.transform(df["soup"])
    print(f"  Matrix: {matrix.shape}")

    total = matrix.shape[0]
    skipped = 0
    uploaded_this_run = 0

    for start in range(0, total, BATCH):
        end = min(start + BATCH, total)

        # Build the batch
        batch_ids = [str(int(df.iloc[i]["id"])) for i in range(start, end)]

        # Check which already exist (skip them, don't waste daily quota)
        existing = get_existing_ids(batch_ids)
        if existing:
            skipped += len(existing)

        vectors = []
        for i in range(start, end):
            vid = str(int(df.iloc[i]["id"]))
            if vid in existing:
                continue
            vec = matrix[i].toarray().flatten().tolist()
            vectors.append((
                vid,
                vec,
                {
                    "title": str(df.iloc[i].get("title", "")),
                    "weighted_rating": float(df.iloc[i].get("weighted_rating", 0) or 0),
                },
            ))

        if not vectors:
            print(f"  ⏭️  {end:,}/{total:,} (all already present)")
            continue

        # Retry up to 5 times with exponential backoff
        success = False
        for attempt in range(5):
            try:
                index.upsert(vectors=vectors)
                success = True
                break
            except Exception as e:
                wait = 2 ** attempt
                print(f"  ⚠️  Batch {start}-{end} failed ({str(e)[:60]}). Retry in {wait}s...")
                time.sleep(wait)

        if not success:
            print(f"  ❌ Gave up on batch {start}-{end} after 5 attempts")
            print(f"  Progress this run: {uploaded_this_run} uploaded, {skipped} skipped.")
            print(f"  Re-run tomorrow to resume.")
            raise SystemExit(1)

        uploaded_this_run += len(vectors)
        print(f"  ⬆️  {end:,}/{total:,}  (uploaded={uploaded_this_run}, skipped={skipped})")
        time.sleep(0.3)

    print(f"\n  ✅ Movies upload complete!")
    print(f"     Uploaded this run: {uploaded_this_run}")
    print(f"     Skipped (already there): {skipped}")


if __name__ == "__main__":
    upload_movies()
    print("\n🎉 Done!")