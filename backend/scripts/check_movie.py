import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
e = create_engine(os.getenv('SUPABASE_DB_URI'))

with e.connect() as c:
    print("\n=== Inception (id=27205) in Supabase ===")
    print(c.execute(text("SELECT id, title, vote_count, release_year FROM movies WHERE id = '27205'")).fetchall())

    print("\n=== First 3 rows (confirm data is sane) ===")
    print(c.execute(text("SELECT id, title, vote_count FROM movies LIMIT 3")).fetchall())