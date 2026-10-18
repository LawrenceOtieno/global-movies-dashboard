import os
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))

print("\n=== MOVIE INDEX: query by Inception (id=27205) ===")
idx = pc.Index('movie-recommender')
r = idx.query(id='27205', top_k=5, include_metadata=True)
for m in r['matches']:
    print(f"  id={m['id']}, score={m['score']:.3f}, meta={m['metadata']}")

print("\n=== TV INDEX: query by Breaking Bad (id=1396) ===")
idx = pc.Index('tv-recommender')
r = idx.query(id='1396', top_k=5, include_metadata=True)
for m in r['matches']:
    print(f"  id={m['id']}, score={m['score']:.3f}, meta={m['metadata']}")