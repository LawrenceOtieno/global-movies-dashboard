from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import joblib
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for communication with your React frontend

# Load dataset and saved ML artifacts
BASE_DIR = os.path.dirname(__file__)
DATA_PATH = os.path.join(BASE_DIR, 'global_movies_dataset_1950_2026.csv')
MODEL_PATH = os.path.join(BASE_DIR, 'movie_hit_model.pkl')
MLB_PATH = os.path.join(BASE_DIR, 'mlb_transformer.pkl')

# Safely load dataset
if os.path.exists(DATA_PATH):
    df = pd.read_csv(DATA_PATH)
else:
    df = None
    print(f"Warning: Dataset not found at {DATA_PATH}")

# Safely load machine learning artifacts if they exist
try:
    model = joblib.load(MODEL_PATH)
    mlb = joblib.load(MLB_PATH)
except Exception as e:
    model = None
    mlb = None
    print(f"Warning: ML models not loaded. Run your training cell in Jupyter first. Error: {e}")

@app.route('/api/health', methods=['GET'])
def health_check():
    """System health and dataset summary check."""
    return jsonify({
        "status": "healthy",
        "total_movies": len(df) if df is not None else 0,
        "model_loaded": model is not None
    })

@app.route('/api/summary-stats', methods=['GET'])
def get_summary_stats():
    """High-level metrics for dashboard header cards."""
    if df is None:
        return jsonify({"error": "Dataset not loaded"}), 500
        
    total_movies = len(df)
    avg_rating = float(df['imdb_rating'].mean()) if 'imdb_rating' in df.columns else 0.0
    total_revenue = float(df['revenue_million'].sum()) if 'revenue_million' in df.columns else 0.0
    avg_runtime = float(df['runtime'].mean()) if 'runtime' in df.columns else 0.0
    
    return jsonify({
        "total_movies": total_movies,
        "average_imdb_rating": round(avg_rating, 2),
        "total_revenue_million": round(total_revenue, 2),
        "average_runtime_minutes": round(avg_runtime, 1)
    })

@app.route('/api/decade-trends', methods=['GET'])
def get_decade_trends():
    """Aggregate movie metrics across release decades for time-series charts."""
    if df is None:
        return jsonify({"error": "Dataset not loaded"}), 500
        
    decade_trends = df.groupby('decade').agg(
        movie_count=('movie_id', 'count') if 'movie_id' in df.columns else ('title', 'count'),
        avg_imdb_rating=('imdb_rating', 'mean'),
        avg_audience_score=('audience_score', 'mean') if 'audience_score' in df.columns else ('imdb_rating', 'mean'),
        avg_revenue_million=('revenue_million', 'mean') if 'revenue_million' in df.columns else ('budget_million', 'mean')
    ).reset_index()
    
    return jsonify(decade_trends.to_dict(orient='records'))

@app.route('/api/streaming-performance', methods=['GET'])
def get_streaming_performance():
    """Aggregate performance stats by streaming platform."""
    if df is None:
        return jsonify({"error": "Dataset not loaded"}), 500
        
    if 'streaming_platform' in df.columns:
        streaming_perf = df.groupby('streaming_platform').agg(
            movie_count=('title', 'count'),
            total_revenue_million=('revenue_million', 'sum') if 'revenue_million' in df.columns else ('budget_million', 'sum'),
            avg_imdb_rating=('imdb_rating', 'mean')
        ).reset_index()
        return jsonify(streaming_perf.to_dict(orient='records'))
        
    return jsonify({"error": "streaming_platform column not found in dataset"}), 404

@app.route('/api/genre-distribution', methods=['GET'])
def get_genre_distribution():
    """Calculate overall movie counts per core genre using the dataset."""
    if df is None or 'genre' not in df.columns:
        return jsonify({"error": "Dataset or genre column not found"}), 500
        
    # Split pipe-separated genres and count occurrences
    all_genres = df['genre'].fillna('').apply(lambda x: [g.strip() for g in x.split('|') if g.strip()])
    flat_genres = [genre for sublist in all_genres for genre in sublist]
    genre_counts = pd.Series(flat_genres).value_counts().reset_index()
    genre_counts.columns = ['genre', 'count']
    
    return jsonify(genre_counts.to_dict(orient='records'))

@app.route('/api/directors-performance', methods=['GET'])
def get_directors_performance():
    """Aggregate top directors by cumulative box office revenue and average ratings."""
    if df is None:
        return jsonify({"error": "Dataset not loaded"}), 500
        
    if 'director' in df.columns:
        director_perf = df.groupby('director').agg(
            movie_count=('movie_id', 'count') if 'movie_id' in df.columns else ('title', 'count'),
            total_revenue_million=('revenue_million', 'sum') if 'revenue_million' in df.columns else ('budget_million', 'sum'),
            avg_imdb_rating=('imdb_rating', 'mean')
        ).reset_index().sort_values(by='total_revenue_million', ascending=False)
        
        return jsonify(director_perf.head(50).to_dict(orient='records'))
        
    return jsonify({"error": "director column not found in dataset"}), 404

@app.route('/api/predict', methods=['POST'])
def predict_movie_success():
    """Accepts feature payloads from React and runs live predictions via the trained Random Forest model."""
    if model is None or mlb is None:
        return jsonify({"error": "Machine learning model or binarizer not loaded on server."}), 500
        
    data = request.json
    try:
        # Extract features sent from the frontend
        genres = data.get('genres', []) # e.g. ["Action", "Sci-Fi"]
        runtime = float(data.get('runtime', 120))
        decade = int(data.get('decade', 2020))
        budget = float(data.get('budget_million', 50.0))
        vote_count = int(data.get('vote_count', 1000))
        revenue = float(data.get('revenue_million', 100.0))
        
        # Transform genres through the saved MultiLabelBinarizer
        genre_encoded = mlb.transform([genres])
        genre_df = pd.DataFrame(genre_encoded, columns=mlb.classes_)
        
        # Build numerical feature dataframe matching training columns
        numeric_data = pd.DataFrame([{
            'runtime': runtime,
            'vote_count': vote_count,
            'revenue_million': revenue,
            'decade': decade,
            'budget_million': budget
        }])
        
        # Concatenate features into the final input matrix shape
        X_input = pd.concat([genre_df.reset_index(drop=True), numeric_data.reset_index(drop=True)], axis=1)
        
        # Execute prediction
        prediction = int(model.predict(X_input)[0])
        probability = float(model.predict_proba(X_input)[0][1]) # Probability of being an IMDb >= 7.0 hit
        
        return jsonify({
            "is_hit": prediction,
            "hit_probability": round(probability * 100, 2)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True, port=5000)