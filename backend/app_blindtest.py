from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import os
import random
from pathlib import Path

app = Flask(__name__)

FRONTEND_ORIGIN = "https://origanire.github.io"

CORS(
    app,
    resources={r"/*": {"origins": [FRONTEND_ORIGIN]}},
    supports_credentials=False,
)

@app.get("/")
def home():
    return jsonify({
        "status": "ok",
        "service": "BlindTest API",
        "base_path": "/blindtest (si monté via DispatcherMiddleware)",
        "routes": [
            "/api/quiz/random",
            "/api/quiz/all",
            "/api/quiz/<id>/answer",
            "/api/quiz/random-set",
            "/api/stats",
            "/api/audio/<id>",
        ],
    })

SOUNDTRACKS = [
    {"id": 1, "title": "Titanic", "composer": "James Horner", "year": 1997, "difficulty": "easy", "movie_id": 597},
    {"id": 2, "title": "Interstellar", "composer": "Hans Zimmer", "year": 2014, "difficulty": "medium", "movie_id": 157336},
    {"id": 3, "title": "Inception", "composer": "Hans Zimmer", "year": 2010, "difficulty": "medium", "movie_id": 27205},
    {"id": 4, "title": "The Dark Knight", "composer": "Hans Zimmer, James Newton Howard", "year": 2008, "difficulty": "hard", "movie_id": 155},
    {"id": 5, "title": "Forrest Gump", "composer": "Alan Silvestri", "year": 1994, "difficulty": "easy", "movie_id": 13},
    {"id": 6, "title": "Le roi lion", "composer": "Elton John, Tim Rice", "year": 1994, "difficulty": "easy", "movie_id": 8587},
    {"id": 7, "title": "Gladiator", "composer": "Hans Zimmer, Lisa Gerrard", "year": 2000, "difficulty": "medium", "movie_id": 98},
    {"id": 8, "title": "The Avengers", "composer": "Alan Silvestri", "year": 2012, "difficulty": "hard", "movie_id": 24428},
    {"id": 9, "title": "Jurassic Park", "composer": "John Williams", "year": 1993, "difficulty": "easy", "movie_id": 329},
    {"id": 10, "title": "Star Wars: A New Hope", "composer": "John Williams", "year": 1977, "difficulty": "easy", "movie_id": 11},
]

@app.get("/api/quiz/random")
def get_random_quiz():
    difficulty = request.args.get("difficulty")
    pool = [q for q in SOUNDTRACKS if q["difficulty"] == difficulty] if difficulty else SOUNDTRACKS
    if not pool:
        return jsonify({"error": "Aucune question disponible"}), 404

    q = random.choice(pool)
    return jsonify({k: q[k] for k in ["id", "title", "composer", "year", "difficulty"]})

@app.get("/api/quiz/all")
def get_all_quiz():
    return jsonify(SOUNDTRACKS)

@app.post("/api/quiz/<int:quiz_id>/answer")
def check_answer(quiz_id: int):
    data = request.get_json(silent=True) or {}
    user_answer = (data.get("answer") or "").strip().lower()

    question = next((q for q in SOUNDTRACKS if q["id"] == quiz_id), None)
    if not question:
        return jsonify({"error": "Question non trouvée"}), 404

    correct_title = question["title"].lower()
    is_correct = user_answer == correct_title or user_answer in correct_title

    return jsonify({
        "correct": is_correct,
        "answer": question["title"],
        "composer": question["composer"],
        "year": question["year"],
    })

@app.get("/api/quiz/random-set")
def get_random_set():
    num_questions = request.args.get("count", 10, type=int)
    difficulty = request.args.get("difficulty")

    available = [q for q in SOUNDTRACKS if q["difficulty"] == difficulty] if difficulty else SOUNDTRACKS
    if not available:
        return jsonify([])

    num_questions = min(num_questions, len(available))
    questions = random.sample(available, num_questions)

    return jsonify([{k: q[k] for k in ["id", "title", "composer", "year", "difficulty"]} for q in questions])

@app.post("/api/stats")
def save_stats():
    data = request.get_json(silent=True) or {}
    score = int(data.get("score", 0))
    total = int(data.get("total", 0))

    return jsonify({
        "success": True,
        "score": score,
        "total": total,
        "percentage": round((score / total * 100) if total > 0 else 0, 2),
    })

@app.get("/api/audio/<int:quiz_id>")
def get_audio(quiz_id: int):
    question = next((q for q in SOUNDTRACKS if q["id"] == quiz_id), None)
    if not question:
        return jsonify({"error": "Question non trouvée"}), 404

    # Met tes mp3 dans: backend/soundtracks/<id>.mp3
    audio_path = Path(__file__).resolve().parent / "soundtracks" / f"{quiz_id}.mp3"

    if audio_path.exists():
        return send_file(str(audio_path), mimetype="audio/mpeg")

    return jsonify({
        "error": "Fichier audio non trouvé",
        "expected_path": str(audio_path),
        "hint": "Ajoute le fichier dans backend/soundtracks/<id>.mp3 puis redeploy.",
    }), 404

if __name__ == "__main__":
    port = int(os.getenv("BLINDTEST_PORT", "5002"))
    app.run(host="0.0.0.0", port=port, debug=True)
