"""
csv_to_parquet.py — converts TMDB_movie_dataset_v11.csv into a compact,
lossless Parquet file for the dashboard/model to load.

Run:
    pip install pandas pyarrow
    python csv_to_parquet.py TMDB_movie_dataset_v11.csv global_movies.parquet

What this does:
- Streams the CSV in chunks (safe for 500MB+ files on modest RAM).
- Drops columns the dashboard/model never use (backdrop_path, poster_path,
  homepage, tagline, overview) — these are large free-text/URL columns that
  bloat the file without adding analytical value here. Comment out any of
  these in DROP_COLUMNS if you actually want them (e.g. for movie posters).
- Filters to status == 'Released' (upcoming/cancelled entries have no real
  ratings and just add noise).
- Derives release_year / decade once, at conversion time, so every endpoint
  and the model can just read a column instead of re-parsing dates.
- Compresses losslessly with zstd (best balance of size vs. speed for a
  dataset this size).
"""

import sys

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

DROP_COLUMNS = ["backdrop_path", "poster_path", "homepage", "tagline", "overview"]
CHUNK_SIZE = 200_000


def process_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    chunk.columns = chunk.columns.str.strip().str.lower()
    chunk = chunk.drop(columns=[c for c in DROP_COLUMNS if c in chunk.columns], errors="ignore")

    chunk = chunk[chunk.get("status", "Released") == "Released"]

    chunk["release_date"] = pd.to_datetime(chunk["release_date"], errors="coerce")
    chunk["release_year"] = chunk["release_date"].dt.year
    chunk["decade"] = (chunk["release_year"] // 10 * 10).astype("Int64")

    # Primary (first-listed) company/country — used for grouping/aggregation
    # endpoints; the full comma-separated field is kept too for the recommender.
    chunk["primary_production_company"] = (
        chunk["production_companies"].astype(str).str.split(",").str[0].str.strip()
    )
    chunk["primary_production_country"] = (
        chunk["production_countries"].astype(str).str.split(",").str[0].str.strip()
    )

    # Drop rows with no title or no rating — useless for the dashboard/model either way.
    chunk = chunk.dropna(subset=["title", "vote_average"])

    return chunk


def main(csv_path: str, out_path: str):
    writer = None
    total_rows = 0

    for chunk in pd.read_csv(csv_path, chunksize=CHUNK_SIZE, low_memory=False):
        chunk = process_chunk(chunk)
        if chunk.empty:
            continue

        table = pa.Table.from_pandas(chunk, preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(out_path, table.schema, compression="zstd", compression_level=15)
        else:
            # Later chunks can infer slightly different dtypes for sparse columns
            # (e.g. an all-null chunk); align to the writer's original schema.
            table = table.cast(writer.schema)

        writer.write_table(table)
        total_rows += len(chunk)
        print(f"  written {total_rows:,} rows so far")

    if writer:
        writer.close()

    print(f"\nDone. {total_rows:,} rows written to {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python csv_to_parquet.py <input.csv> <output.parquet>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
