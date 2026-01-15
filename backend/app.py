from werkzeug.middleware.dispatcher import DispatcherMiddleware
from flask import Flask, jsonify
from flask_cors import CORS

from app_akinator import app as akinator_app
from app_moviegrid import app as moviegrid_app
from app_blindtest import app as blindtest_app

# Frontend GitHub Pages origin
FRONTEND_ORIGIN = "https://origanire.github.io"

root = Flask(__name__)

# CORS for root routes (/ and /health)
CORS(root, resources={r"/*": {"origins": [FRONTEND_ORIGIN]}})

@root.get("/")
def home():
    return jsonify({
        "status": "ok",
        "routes": {
            "health": "/health",
            "akinator": "/akinator",
            "moviegrid": "/moviegrid",
            "blindtest": "/blindtest",
        }
    })

@root.get("/health")
def health():
    return jsonify({"status": "ok"})

# CORS for sub-apps (important: each Flask app needs its own CORS config)
CORS(akinator_app, resources={r"/*": {"origins": [FRONTEND_ORIGIN]}})
CORS(moviegrid_app, resources={r"/*": {"origins": [FRONTEND_ORIGIN]}})
CORS(blindtest_app, resources={r"/*": {"origins": [FRONTEND_ORIGIN]}})

# WSGI app mounted for gunicorn: app:app
app = DispatcherMiddleware(root, {
    "/akinator": akinator_app,
    "/moviegrid": moviegrid_app,
    "/blindtest": blindtest_app,
})
