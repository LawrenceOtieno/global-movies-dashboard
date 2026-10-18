import os
import time
import joblib
import pandas as pd
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
BACKEND = os.path.join(os.path.dirname(__file__), '..')
pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))

BATCH = 50


def build_soup_movie(row) -> str:
    genres = str(row.get("genres", "")).replace(",", " ")
    keywords = str(row.get("keywords", "")).replace(",", " ")
    company = str(row.get("primary_production_company", ""))
    language = str(row.get("original_language", ""))
    return f"{genres} {genres} {genres} {keywords} {company} {language}"


def build_soup_tv(row) -> str:
    genres = str(row.get("genres", "")).replace(",", " ")
    created_by = str(row.get("created_by", "")).replace(",", " ")
    network = str(row.get("primary_network", ""))
    company = str(row.get("primary_production_company", ""))
    language = str(row.get("original_language", ""))
    return f"{genres} {genres} {genres} {created_by} {network} {company} {language}"


def upload(parquet_file, vectorizer_file, index_name, label, build_soup, name_col):
    print(f"\n=== Uploading {label} ===")
    df = pd.read_parquet(os.path.join(BACKEND, parquet_file))
    vectorizer = joblib.load(os.path.join(BACKEND, vectorizer_file))
    print(f"  Loaded {len(df):,} raw rows | vocab {len(vectorizer.vocabulary_)}")

    min_votes = max(int(df["vote_count"].quantile(0.98)), 50)
    df = df[df["vote_count"] >= min_votes].copy()
    if len(df) > 30_000:
        df = df.nlargest(30_000, "vote_count")
    df = df.reset_index(drop=True)
    print(f"  Filtered pool: {len(df):,} rows (min_votes={min_votes})")

    df["soup"] = df.apply(build_soup, axis=1)
    print("  Vectorizing...")
    matrix = vectorizer.transform(df["soup"])
    print(f"  Matrix: {matrix.shape}")

    index = pc.Index(index_name)
    total = matrix.shape[0]
    for start in range(0, total, BATCH):
        end = min(start + BATCH, total)
        vectors = []
        for i in range(start, end):
            vec = matrix[i].toarray().flatten().tolist()
            title = str(df.iloc[i].get(name_col, ""))
            vectors.append({
                "id": str(int(df.iloc[i]["id"])),
                "values": vec,
                "metadata": {
                    "title": title,
                    "weighted_rating": float(df.iloc[i].get("weighted_rating", 0) or 0),
                },
            })
        index.upsert(vectors=vectors)
        print(f"  ⬆️  {end:,}/{total:,}")
        time.sleep(0.1)
    print(f"  ✅ Done {label}")


if __name__ == "__main__":
    # Movies: use 'title'
    upload(
        'global_movies.parquet',
        'tfidf_vectorizer.pkl',
        os.getenv('PINECONE_MOVIE_INDEX'),
        'movies',
        build_soup_movie,
        'title',
    )
    # TV: use 'name'
    upload(
        'global_tv_shows.parquet',
        'tv_tfidf_vectorizer.pkl',
        os.getenv('PINECONE_TV_INDEX'),
        'tv',
        build_soup_tv,
        'name',
    )
    print("\n🎉 All vectors uploaded!")