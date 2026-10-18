"""
One-time: dumps Supabase `analytics_cache` rows to local JSON files.
Re-run whenever analytics change (not on every deploy).
"""
import os
import json
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
BACKEND = os.path.join(os.path.dirname(__file__), '..')
CACHE_DIR = os.path.join(BACKEND, 'analytics_cache')
os.makedirs(CACHE_DIR, exist_ok=True)

engine = create_engine(os.getenv('SUPABASE_DB_URI'))

print("Exporting analytics cache to disk...")
with engine.connect() as conn:
    rows = conn.execute(text(
        "SELECT content_type, key, payload FROM analytics_cache"
    )).fetchall()

print(f"  Found {len(rows)} rows")
for content_type, key, payload in rows:
    path = os.path.join(CACHE_DIR, f"{content_type}_{key}.json")
    with open(path, 'w') as f:
        json.dump(payload, f)
    size = os.path.getsize(path)
    print(f"  ✅ {content_type}/{key} → {size:,} bytes")

print(f"\nDone. Files written to: {CACHE_DIR}")