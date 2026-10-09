"""
app.py — thin Flask entry point.

All actual logic lives in routes/movies.py and routes/tv.py as Blueprints —
this file just creates the app, enables CORS, registers both Blueprints,
and runs the dev server. Keeping this file small is the point: as more
content types get added later, each one is its own Blueprint file, and this
file barely grows.

Movie routes are still mounted at /api/... (unchanged from before this
split — nothing on the frontend needed to change). TV routes are mounted at
/api/tv/... (set via url_prefix on tv_bp itself, in routes/tv.py).

threaded=True matters at this dataset size: without it, Flask's dev server
handles one request at a time, so a single slow call blocks every other
request — including trivial ones — until it finishes.
"""

from flask import Flask
from flask_compress import Compress
from flask_cors import CORS

from routes.movies import movies_bp
from routes.tv import tv_bp

app = Flask(__name__)
CORS(app)

# Gzips every JSON response above ~500 bytes — the biggest win is on the
# cult-classics endpoints (a 1500-point scatter sample) and the larger
# ranking/distribution payloads, which compress very well as repetitive
# JSON. Pure backend change, nothing for the frontend to do differently.
Compress(app)

app.register_blueprint(movies_bp)
app.register_blueprint(tv_bp)

if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)
