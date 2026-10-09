"""
csv_to_parquet_tv.py — converts the asaniczka TMDb TV Shows dataset CSV into
a compact Parquet file, mirroring csv_to_parquet.py's approach for movies.

Run:
    pip install pandas pyarrow
    python csv_to_parquet_tv.py full_tmdb_tv_shows_dataset.csv global_tv_shows.parquet

Differences from the movie conversion script (real schema, not guessed):
- No `keywords` column at all on the TV side.
- Title field is `name`, not `title`.
- Dates are DD/MM/YYYY ("17/04/2011"), not the movie file's format — parsed
  with dayfirst=True explicitly, since silently misparsing day/month would
  corrupt every derived year/decade otherwise.
- No budget/revenue — TMDB doesn't track box-office-style figures for TV.
- `episode_run_time` is frequently 0 for major, well-documented shows (Game
  of Thrones, Stranger Things) — treated as "missing", same as the movies
  pipeline treats runtime == 0.
- Adds `networks` (HBO, Netflix, etc.) — a TV-only concept, no movie
  equivalent — as its own primary_network column, alongside
  primary_production_company/primary_production_country (same pattern as
  the movies script).
- TV genre taxonomy is TMDB's own separate TV genre list (e.g. "Sci-Fi &
  Fantasy", "Action & Adventure") — different category names than movies
  use, kept as-is rather than remapped, since that's the real taxonomy.
"""

import sys

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

DROP_COLUMNS = ["backdrop_path", "poster_path", "homepage", "tagline", "overview"]
CHUNK_SIZE = 200_000

# Statuses with essentially no real data yet — analogous to filtering out
# unreleased movies. Everything else (including "Returning Series", which
# just means "still airing") is kept, since ongoing shows still have real
# votes and ratings.
EXCLUDED_STATUSES = {"Planned", "Pilot"}

# The dataset's `adult` column was never checked — nothing filtered it out,
# which is how an entry like "Live XXX TV" ended up ranked in Bottom 10
# Shows. Excluded entirely, same as any general-audience dashboard would.


# Columns worth reporting missing-value counts for — not every column (some,
# like tagline, are dropped entirely before this matters; others, like
# created_by, are fine to be missing and don't need calling out).
REPORT_COLUMNS = ["name", "vote_average", "vote_count", "genres", "first_air_date",
                   "networks", "production_companies", "production_countries",
                   "original_language", "episode_run_time"]


def process_chunk(chunk: pd.DataFrame, stats: dict, seen_ids: set) -> pd.DataFrame:
    chunk.columns = chunk.columns.str.strip().str.lower()
    chunk = chunk.drop(columns=[c for c in DROP_COLUMNS if c in chunk.columns], errors="ignore")

    stats["rows_seen"] += len(chunk)

    if "status" in chunk.columns:
        excluded = chunk["status"].isin(EXCLUDED_STATUSES)
        stats["dropped_excluded_status"] += int(excluded.sum())
        chunk = chunk[~excluded]

    if "adult" in chunk.columns:
        is_adult = chunk["adult"].astype(str).str.upper().isin(["TRUE", "1"])
        stats["dropped_adult"] = stats.get("dropped_adult", 0) + int(is_adult.sum())
        chunk = chunk[~is_adult]

    # Count missing values per column of interest BEFORE any further
    # cleaning touches them, so the report reflects the raw source data.
    for col in REPORT_COLUMNS:
        if col in chunk.columns:
            missing = chunk[col].isna().sum()
            if col == "episode_run_time":
                # 0 behaves as "missing" for this column (confirmed against
                # real shows like Game of Thrones, which legitimately has
                # episode_run_time == 0 despite having 60+ minute episodes —
                # TMDB just doesn't have the figure for every show).
                missing += int((chunk[col] == 0).sum())
            stats["missing_counts"][col] = stats["missing_counts"].get(col, 0) + int(missing)

    chunk["first_air_date"] = pd.to_datetime(chunk["first_air_date"], errors="coerce", dayfirst=True)
    chunk["first_air_year"] = chunk["first_air_date"].dt.year
    chunk["decade"] = (chunk["first_air_year"] // 10 * 10).astype("Int64")

    chunk["primary_network"] = chunk["networks"].astype(str).str.split(",").str[0].str.strip()
    chunk["primary_production_company"] = (
        chunk["production_companies"].astype(str).str.split(",").str[0].str.strip()
    )
    chunk["primary_production_country"] = (
        chunk["production_countries"].astype(str).str.split(",").str[0].str.strip()
    )

    # Drop rows with no name or no rating — these have nothing meaningful to
    # show or recommend on, same rationale as the movie script. Everything
    # else with a gap (missing genre, missing network, etc.) is KEPT and
    # handled gracefully downstream (e.g. the dashboard's "Uncategorized"
    # pattern for missing genres) rather than thrown away — a show missing
    # one field is still a real, useful row.
    before = len(chunk)
    chunk = chunk.dropna(subset=["name", "vote_average"])
    stats["dropped_no_name_or_rating"] += before - len(chunk)

    # The source CSV contains literal duplicate rows for the same id (e.g.
    # "Arsenal - Invincibles", id 238349, appeared three times, byte-for-
    # byte identical) — not different shows that happen to share a name,
    # the exact same row repeated. Left in, a duplicated show effectively
    # gets double or triple weight in every count/average/percentile
    # computed downstream. `seen_ids` is shared across every chunk (not just
    # within one), so this catches duplicates even if the file is large
    # enough that the two copies land in different 200k-row chunks.
    before = len(chunk)
    chunk = chunk[~chunk["id"].isin(seen_ids)]
    chunk = chunk.drop_duplicates(subset=["id"], keep="first")
    seen_ids.update(chunk["id"].tolist())
    stats["dropped_duplicate_id"] = stats.get("dropped_duplicate_id", 0) + (before - len(chunk))

    return chunk


def main(csv_path: str, out_path: str):
    writer = None
    total_rows = 0
    stats = {"rows_seen": 0, "dropped_excluded_status": 0, "dropped_adult": 0,
             "dropped_no_name_or_rating": 0, "dropped_duplicate_id": 0, "missing_counts": {}}
    seen_ids = set()

    for chunk in pd.read_csv(csv_path, chunksize=CHUNK_SIZE, low_memory=False, encoding="utf-8"):
        chunk = process_chunk(chunk, stats, seen_ids)
        if chunk.empty:
            continue

        table = pa.Table.from_pandas(chunk, preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(out_path, table.schema, compression="zstd", compression_level=15)
        else:
            table = table.cast(writer.schema)

        writer.write_table(table)
        total_rows += len(chunk)
        print(f"  written {total_rows:,} rows so far")

    if writer:
        writer.close()

    print(f"\nDone. {total_rows:,} rows written to {out_path}")
    print("\n--- Cleaning report ---")
    print(f"Rows in source file:                {stats['rows_seen']:,}")
    print(f"Dropped (status Planned/Pilot):      {stats['dropped_excluded_status']:,}")
    print(f"Dropped (adult content):             {stats['dropped_adult']:,}")
    print(f"Dropped (duplicate id):              {stats['dropped_duplicate_id']:,}")
    print(f"Dropped (no name or no rating):      {stats['dropped_no_name_or_rating']:,}")
    print(f"Rows kept:                           {total_rows:,}")
    print("\nMissing values by column (in the SOURCE data, before any cleaning —")
    print("most of these are kept, not dropped; see comments in process_chunk):")
    for col, count in stats["missing_counts"].items():
        pct = count / stats["rows_seen"] * 100 if stats["rows_seen"] else 0
        print(f"  {col:<24} {count:>10,}  ({pct:.1f}%)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python csv_to_parquet_tv.py <input.csv> <output.parquet>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
