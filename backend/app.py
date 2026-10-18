"""
app.py — thin Flask entry point.

All actual logic lives in routes/movies.py and routes/tv.py as Blueprints —
this file just creates the app, enables CORS, registers both Blueprints,
and runs the dev server.

threaded=True matters: without it, Flask's dev server handles one request
at a time, so a single slow call blocks every other request.
"""

from flask import Flask
from flask_compress import Compress
from flask_cors import CORS

from routes.movies import movies_bp
from routes.tv import tv_bp

app = Flask(__name__)
CORS(app)
Compress(app)

app.register_blueprint(movies_bp)
app.register_blueprint(tv_bp)

if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)