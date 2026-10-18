"""
Generates all precomputed analytics for movies + TV from parquet and uploads
them to Supabase's `analytics_cache` table. Run once (and re-run whenever the
parquet data changes).
"""
import os
import json
import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
DB_URI = os.getenv('SUPABASE_DB_URI')
BACKEND = os.path.join(os.path.dirname(__file__), '..')


def safe(v, ndigits=None):
    if v is None or pd.isna(v):
        return None
    if ndigits is not None:
        return round(float(v), ndigits)
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


# =========================================================
# MOVIE ANALYTICS
# =========================================================
def generate_movie_analytics():
    print("\n📊 Generating movie analytics...")
    df = pd.read_parquet(os.path.join(BACKEND, 'global_movies.parquet'))
    analytics = {}

    # --- Summary stats ---
    total_movies = int(len(df))
    total_revenue = float(df['revenue'].sum())
    rated = df[df['vote_count'] > 0]
    avg_rating = float(rated['vote_average'].mean()) if not rated.empty else 0.0
    timed = df[df['runtime'] > 0]
    avg_runtime = float(timed['runtime'].mean()) if not timed.empty else 0.0
    highly_rated = int((df['vote_average'] >= 7.0).sum())

    # Top genre by revenue
    genre_rev = df[['genres', 'revenue']].copy()
    genre_rev['genres'] = genre_rev['genres'].fillna("").astype(str).replace({"nan": "", "None": ""}).str.split(",")
    exploded = genre_rev.explode('genres')
    exploded['genres'] = exploded['genres'].str.strip()
    exploded = exploded[exploded['genres'] != ""]
    totals = exploded.groupby('genres')['revenue'].sum()
    top_genre = [totals.idxmax(), round(float(totals.max()), 2)] if not totals.empty else None

    total_companies = 0
    if 'primary_production_company' in df.columns:
        valid = df[df['primary_production_company'].notna() & (df['primary_production_company'] != "nan")]
        total_companies = int(valid['primary_production_company'].nunique())

    analytics['summary_stats'] = {
        "total_movies": total_movies,
        "average_rating": round(avg_rating, 2),
        "total_revenue": round(total_revenue, 2),
        "average_runtime_minutes": round(avg_runtime, 1),
        "highly_rated_count": highly_rated,
        "other_count": total_movies - highly_rated,
        "top_genre_by_revenue": top_genre,
        "total_production_companies": total_companies,
    }

    # --- Genre distribution ---
    genres_series = df['genres'].fillna("").astype(str).replace({"nan": "", "None": ""})
    tags = genres_series.str.split(",").explode().str.strip()
    is_uncat = tags == ""
    uncat_count = int(is_uncat.sum())
    tags = tags[~is_uncat]
    counts = tags.value_counts()
    total = int(counts.sum()) + uncat_count
    analytics['genre_distribution'] = {
        "genres": [
            {"genre": g, "count": int(c), "percentage": round(c / total * 100, 1)}
            for g, c in counts.head(8).items()
        ],
        "uncategorized_count": uncat_count,
        "uncategorized_percentage": round(uncat_count / total * 100, 1) if total else 0.0,
    }

    # --- Decade trends ---
    if 'decade' in df.columns:
        trends = df.dropna(subset=['decade']).groupby('decade')['vote_average'].mean().reset_index()
        trends.columns = ['decade', 'avg_rating']
        trends = trends.sort_values('decade')
        trends['avg_rating'] = trends['avg_rating'].round(2)
        trends['decade'] = trends['decade'].astype(int)
        analytics['decade_trends'] = trends.to_dict(orient="records")
    else:
        analytics['decade_trends'] = []

    # --- Production company performance ---
    if 'primary_production_company' in df.columns:
        valid = df[df['primary_production_company'].notna() & (df['primary_production_company'] != "nan")]
        company_rev = (valid.groupby('primary_production_company')['revenue'].sum()
                       .sort_values(ascending=False).head(5))
        analytics['production_companies_performance'] = [
            {
                "production_company": name,
                "total_revenue": float(rev),
                "percentage_of_total": round(float(rev) / total_revenue * 100, 1) if total_revenue else 0.0,
            }
            for name, rev in company_rev.items()
        ]
    else:
        analytics['production_companies_performance'] = []

    # --- Country performance ---
    min_votes = max(int(df['vote_count'].quantile(0.90)), 50)
    if 'primary_production_country' in df.columns:
        country_rated = df[df['vote_count'] >= min_votes]
        countries = (country_rated[country_rated['primary_production_country'].notna()
                                    & (country_rated['primary_production_country'] != "nan")]
                     .groupby('primary_production_country')
                     .agg(movie_count=('vote_average', 'count'), avg_rating=('vote_average', 'mean'))
                     .reset_index()
                     .sort_values(by='movie_count', ascending=False).head(8)
                     .sort_values(by='avg_rating', ascending=False))
        countries.columns = ['production_country', 'movie_count', 'avg_rating']
        countries['avg_rating'] = countries['avg_rating'].round(2)
        analytics['production_countries_performance'] = countries.to_dict(orient="records")
    else:
        analytics['production_countries_performance'] = []

    # --- Movie rankings ---
    if 'weighted_rating' in df.columns:
        pool = df[(df['vote_count'] >= min_votes) & (df['revenue'] > 0)]

        def rows(sub):
            return [
                {
                    "title": str(r.title),
                    "year": safe(r.release_year),
                    "rating": safe(r.vote_average),
                    "weighted_rating": safe(r.weighted_rating, 2),
                    "vote_count": safe(r.vote_count),
                    "revenue": safe(r.revenue),
                }
                for r in sub.itertuples()
            ]

        cols = ['title', 'release_year', 'vote_average', 'weighted_rating', 'vote_count', 'revenue']
        analytics['movie_rankings'] = {
            "top": rows(pool.nlargest(10, 'weighted_rating')[cols]),
            "bottom": rows(pool.nsmallest(10, 'weighted_rating')[cols]),
        }
    else:
        analytics['movie_rankings'] = {"top": [], "bottom": []}

    # --- Cult classics ---
    if 'hidden_gem_score' in df.columns:
        pool = df.dropna(subset=['hidden_gem_score', 'popularity_percentile', 'rating_percentile'])

        def points(sub):
            return [
                {
                    "title": str(r.title),
                    "year": safe(r.release_year),
                    "popularity": safe(r.popularity),
                    "rating": safe(r.vote_average),
                    "weighted_rating": safe(r.weighted_rating, 2),
                    "vote_count": safe(r.vote_count),
                    "popularity_percentile": safe(r.popularity_percentile, 1),
                    "rating_percentile": safe(r.rating_percentile, 1),
                }
                for r in sub.itertuples()
            ]

        scatter = pool.sample(n=min(1500, len(pool)), random_state=42)
        analytics['cult_classics'] = {
            "hidden_gems": points(pool.nlargest(15, 'hidden_gem_score')),
            "overrated": points(pool.nlargest(15, 'overrated_score')),
            "all_points": points(scatter),
        }
    else:
        analytics['cult_classics'] = {"hidden_gems": [], "overrated": [], "all_points": []}

    print(f"  ✅ Generated {len(analytics)} movie analytics blobs")
    return analytics


# =========================================================
# TV ANALYTICS
# =========================================================
def generate_tv_analytics():
    print("\n📺 Generating TV analytics...")
    df = pd.read_parquet(os.path.join(BACKEND, 'global_tv_shows.parquet'))
    analytics = {}

    total_shows = int(len(df))
    rated = df[df['vote_count'] > 0]
    avg_rating = float(rated['vote_average'].mean()) if not rated.empty else 0.0
    timed = df[df['episode_run_time'] > 0]
    avg_runtime = float(timed['episode_run_time'].mean()) if not timed.empty else 0.0
    highly_rated = int((df['vote_average'] >= 7.0).sum())

    genre_df = df[['genres']].copy()
    genre_df['genres'] = genre_df['genres'].fillna("").astype(str).replace({"nan": "", "None": ""}).str.split(",")
    exploded = genre_df.explode('genres')
    exploded['genres'] = exploded['genres'].str.strip()
    exploded = exploded[exploded['genres'] != ""]
    counts = exploded['genres'].value_counts()
    top_genre = [counts.index[0], int(counts.iloc[0])] if not counts.empty else None

    analytics['summary_stats'] = {
        "total_shows": total_shows,
        "average_rating": round(avg_rating, 2),
        "average_episode_runtime_minutes": round(avg_runtime, 1),
        "highly_rated_count": highly_rated,
        "other_count": total_shows - highly_rated,
        "top_genre_by_show_count": top_genre,
    }

    # Genre distribution
    gs = df['genres'].fillna("").astype(str).replace({"nan": "", "None": ""})
    tags = gs.str.split(",").explode().str.strip()
    is_uncat = tags == ""
    uncat_count = int(is_uncat.sum())
    tags = tags[~is_uncat]
    counts2 = tags.value_counts()
    total = int(counts2.sum()) + uncat_count
    analytics['genre_distribution'] = {
        "genres": [
            {"genre": g, "count": int(c), "percentage": round(c / total * 100, 1)}
            for g, c in counts2.head(8).items()
        ],
        "uncategorized_count": uncat_count,
        "uncategorized_percentage": round(uncat_count / total * 100, 1) if total else 0.0,
    }

    if 'decade' in df.columns:
        trends = df.dropna(subset=['decade']).groupby('decade')['vote_average'].mean().reset_index()
        trends.columns = ['decade', 'avg_rating']
        trends = trends.sort_values('decade')
        trends['avg_rating'] = trends['avg_rating'].round(2)
        trends['decade'] = trends['decade'].astype(int)
        analytics['decade_trends'] = trends.to_dict(orient="records")
    else:
        analytics['decade_trends'] = []

    min_votes = max(int(df['vote_count'].quantile(0.90)), 50)
    pool = df[df['vote_count'] >= min_votes]

    # Network performance
    if 'primary_network' in df.columns:
        nets = (pool[pool['primary_network'].notna() & (pool['primary_network'] != "nan")]
                .groupby('primary_network')
                .agg(show_count=('vote_average', 'count'), avg_rating=('vote_average', 'mean'))
                .reset_index().sort_values(by='show_count', ascending=False).head(8)
                .sort_values(by='avg_rating', ascending=False))
        nets.columns = ['network', 'show_count', 'avg_rating']
        nets['avg_rating'] = nets['avg_rating'].round(2)
        analytics['network_performance'] = nets.to_dict(orient="records")
    else:
        analytics['network_performance'] = []

    # Company performance
    total_companies = 0
    if 'primary_production_company' in df.columns:
        valid = pool[pool['primary_production_company'].notna() & (pool['primary_production_company'] != "nan")]
        total_companies = int(valid['primary_production_company'].nunique())
        comps = (valid.groupby('primary_production_company')
                 .agg(show_count=('vote_average', 'count'), avg_rating=('vote_average', 'mean'))
                 .reset_index().sort_values(by='show_count', ascending=False).head(5)
                 .sort_values(by='avg_rating', ascending=False))
        comps.columns = ['production_company', 'show_count', 'avg_rating']
        comps['avg_rating'] = comps['avg_rating'].round(2)
        analytics['production_companies_performance'] = comps.to_dict(orient="records")
    else:
        analytics['production_companies_performance'] = []
    analytics['summary_stats']['total_production_companies'] = total_companies

    # Country performance
    if 'primary_production_country' in df.columns:
        countries = (pool[pool['primary_production_country'].notna() & (pool['primary_production_country'] != "nan")]
                     .groupby('primary_production_country')
                     .agg(show_count=('vote_average', 'count'), avg_rating=('vote_average', 'mean'))
                     .reset_index().sort_values(by='show_count', ascending=False).head(8)
                     .sort_values(by='avg_rating', ascending=False))
        countries.columns = ['production_country', 'show_count', 'avg_rating']
        countries['avg_rating'] = countries['avg_rating'].round(2)
        analytics['production_countries_performance'] = countries.to_dict(orient="records")
    else:
        analytics['production_countries_performance'] = []

    # Rankings
    if 'weighted_rating' in df.columns:
        ranking_pool = pool[(pool['number_of_seasons'] > 0) & pool['first_air_year'].notna()]

        def rows(sub):
            return [
                {
                    "name": str(r.name),
                    "year": safe(r.first_air_year),
                    "rating": safe(r.vote_average),
                    "weighted_rating": safe(r.weighted_rating, 2),
                    "vote_count": safe(r.vote_count),
                    "seasons": safe(r.number_of_seasons),
                }
                for r in sub.itertuples()
            ]

        cols = ['name', 'first_air_year', 'vote_average', 'weighted_rating', 'vote_count', 'number_of_seasons']
        analytics['show_rankings'] = {
            "top": rows(ranking_pool.nlargest(10, 'weighted_rating')[cols]),
            "bottom": rows(ranking_pool.nsmallest(10, 'weighted_rating')[cols]),
        }
    else:
        analytics['show_rankings'] = {"top": [], "bottom": []}

    # Cult classics
    if 'hidden_gem_score' in df.columns:
        cult_pool = df.dropna(subset=['hidden_gem_score', 'popularity_percentile', 'rating_percentile'])

        def points(sub):
            return [
                {
                    "name": str(r.name),
                    "year": safe(r.first_air_year),
                    "popularity": safe(r.popularity),
                    "rating": safe(r.vote_average),
                    "weighted_rating": safe(r.weighted_rating, 2),
                    "vote_count": safe(r.vote_count),
                    "popularity_percentile": safe(r.popularity_percentile, 1),
                    "rating_percentile": safe(r.rating_percentile, 1),
                }
                for r in sub.itertuples()
            ]

        scatter = cult_pool.sample(n=min(1500, len(cult_pool)), random_state=42)
        analytics['cult_classics'] = {
            "hidden_gems": points(cult_pool.nlargest(15, 'hidden_gem_score')),
            "overrated": points(cult_pool.nlargest(15, 'overrated_score')),
            "all_points": points(scatter),
        }
    else:
        analytics['cult_classics'] = {"hidden_gems": [], "overrated": [], "all_points": []}

    print(f"  ✅ Generated {len(analytics)} TV analytics blobs")
    return analytics


# =========================================================
# UPLOAD TO SUPABASE
# =========================================================
def upload_analytics():
    movie_analytics = generate_movie_analytics()
    tv_analytics = generate_tv_analytics()

    conn = psycopg2.connect(DB_URI)
    cur = conn.cursor()

    # Create table (drops existing)
    cur.execute('DROP TABLE IF EXISTS analytics_cache CASCADE')
    cur.execute('''
        CREATE TABLE analytics_cache (
            content_type TEXT NOT NULL,
            key TEXT NOT NULL,
            payload JSONB NOT NULL,
            PRIMARY KEY (content_type, key)
        )
    ''')

    print("\n⬆️  Uploading analytics to Supabase...")
    for key, payload in movie_analytics.items():
        cur.execute(
            "INSERT INTO analytics_cache (content_type, key, payload) VALUES (%s, %s, %s)",
            ('movie', key, json.dumps(payload))
        )
    for key, payload in tv_analytics.items():
        cur.execute(
            "INSERT INTO analytics_cache (content_type, key, payload) VALUES (%s, %s, %s)",
            ('tv', key, json.dumps(payload))
        )

    conn.commit()
    cur.close()
    conn.close()
    print("🎉 Analytics cache uploaded!")


if __name__ == "__main__":
    upload_analytics()