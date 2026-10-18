import os
import io
import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
DB_URI = os.getenv('SUPABASE_DB_URI')
BACKEND = os.path.join(os.path.dirname(__file__), '..')

BATCH_SIZE = 100_000  # tune: 50k–200k works well


def upload(parquet_file: str, table_name: str):
    path = os.path.join(BACKEND, parquet_file)
    print(f"\n📦 Loading {parquet_file} ...")
    df = pd.read_parquet(path)
    print(f"   Rows: {len(df):,} | Cols: {len(df.columns)}")

    # Clean column names
    df.columns = [
        c.lower().replace(' ', '_').replace('-', '_').replace('.', '_')
        for c in df.columns
    ]

    # Stringify any list/dict cells
    for col in df.columns:
        if df[col].dtype == 'object':
            df[col] = df[col].apply(
                lambda x: str(x) if isinstance(x, (list, dict)) else x
            )

    conn = psycopg2.connect(DB_URI)
    cur = conn.cursor()
    # Disable per-query timeout for our session (may or may not be allowed on free tier)
    try:
        cur.execute("SET statement_timeout = 0")
        conn.commit()
    except Exception:
        conn.rollback()

    # Fresh table
    cur.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')
    cols_def = ", ".join([f'"{c}" TEXT' for c in df.columns])
    cur.execute(f'CREATE TABLE "{table_name}" ({cols_def})')
    conn.commit()

    # Batch COPY
    total = len(df)
    for start in range(0, total, BATCH_SIZE):
        end = min(start + BATCH_SIZE, total)
        chunk = df.iloc[start:end]
        buf = io.StringIO()
        chunk.to_csv(buf, index=False, header=False, sep='\t', na_rep='\\N')
        buf.seek(0)
        cur.copy_expert(
            f'COPY "{table_name}" FROM STDIN WITH (FORMAT csv, DELIMITER E\'\\t\', NULL \'\\N\')',
            buf
        )
        conn.commit()
        print(f"   ⬆️  {end:,} / {total:,} rows uploaded")

    cur.close()
    conn.close()
    print(f"   ✅ Done: {table_name}")


if __name__ == "__main__":
    upload('global_movies.parquet', 'movies')
    upload('global_tv_shows.parquet', 'tv_shows')
    print("\n🎉 All uploads complete!")