#!/usr/bin/env python3
from __future__ import annotations

import os
import sqlite3
import traceback
from pathlib import Path
from typing import Dict, Any

# ==============================
# CHARGEMENT DU FICHIER .env
# ==============================
def load_env_file():
    """Charge le fichier .env manuellement (sans dépendance python-dotenv)."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        print(f"⚠️  Fichier .env non trouvé: {env_path}")
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            # Ignorer les commentaires et lignes vides
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Ne pas écraser les variables déjà définies dans l'environnement
                if key and value and key not in os.environ:
                    os.environ[key] = value

load_env_file()
# ==============================

from flask import Flask, request, jsonify
from flask_cors import CORS

# Import du moteur IA au lieu de l'ancien
from engines.engine_akinator_multi_ai import AkinatorSession

app = Flask(__name__)

CORS(app, resources={
    r"/*": {
        "origins": ["https://origanire.github.io"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"],
    }
})

OPTIONS_UI = ["Oui", "Non", "Je ne sais pas"]

UI_TO_ENGINE = {
    "Oui": "y",
    "Non": "n",
    "Je ne sais pas": "?",
    "y": "y",
    "n": "n",
    "?": "?",
}

# Sessions stockées en mémoire (utilise l'IA)
game_sessions: Dict[str, AkinatorSession] = {}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def db_path() -> str:
    return str(repo_root() / "movies.db")


def new_game_id() -> str:
    return os.urandom(8).hex()


def internal_error(where: str, exc: Exception):
    return (
        jsonify(
            {
                "error": "Internal error",
                "where": where,
                "detail": str(exc),
                "trace": traceback.format_exc(),
                "db_path": db_path(),
            }
        ),
        500,
    )


@app.get("/")
def health():
    # Récupérer le provider configuré
    provider = os.getenv("AI_PROVIDER", "gemini")
    
    # Vérifier quelle clé API est configurée
    api_status = {
        "gemini": bool(os.getenv("GOOGLE_API_KEY")),
        "claude": bool(os.getenv("ANTHROPIC_API_KEY")),
        "openai": bool(os.getenv("OPENAI_API_KEY"))
    }
    
    return jsonify({
        "status": "ok", 
        "service": "Akinator API (IA)", 
        "db": db_path(),
        "ai_provider": provider,
        "api_configured": api_status.get(provider, False)
    }), 200


@app.post("/start")
def start_game():
    try:
        gid = new_game_id()
        
        # Créer une session IA
        provider = os.getenv("AI_PROVIDER", "gemini")
        session = AkinatorSession(db_path=db_path(), provider=provider)
        
        # Démarrer le jeu
        result = session.start()
        
        if result.get("status") != "ok":
            return jsonify({"error": "Erreur lors du démarrage"}), 500
        
        # Stocker la session
        game_sessions[gid] = session
        
        # Formater la réponse au format attendu par le frontend
        return jsonify({
            "game_id": gid,
            "question": result["content"],
            "question_key": str(result["question_number"]),
            "options": OPTIONS_UI,
            "finished": False,
        }), 200
        
    except Exception as e:
        return internal_error("start_game", e)


@app.post("/answer")
def answer():
    try:
        data = request.get_json(silent=True) or {}
        gid = data.get("game_id")
        ui_answer = data.get("answer")

        if not gid:
            return jsonify({"error": "game_id manquant"}), 400
        if gid not in game_sessions:
            return jsonify({"error": "Partie non trouvée"}), 404

        if ui_answer not in UI_TO_ENGINE:
            return jsonify({"error": "Réponse invalide", "got": ui_answer}), 400

        session = game_sessions[gid]
        engine_answer = UI_TO_ENGINE[ui_answer]

        # Envoyer la réponse à l'IA
        result = session.answer(engine_answer)
        
        if result.get("status") != "ok":
            return jsonify({"error": "Erreur lors du traitement"}), 500

        # Si l'IA propose un film (guess)
        if result.get("action") == "guess":
            return jsonify({
                "finished": False,
                "asking_confirmation": True,
                "guess": result["content"],
                "confirmation_options": ["Oui, c'est ça!", "Non, continuer"]
            }), 200
        
        # Sinon, c'est une nouvelle question
        return jsonify({
            "finished": False,
            "asking_confirmation": False,
            "question": result["content"],
            "question_key": str(result["question_number"]),
            "options": OPTIONS_UI,
        }), 200

    except Exception as e:
        return internal_error("answer", e)


@app.post("/confirm")
def confirm_guess():
    try:
        data = request.get_json(silent=True) or {}
        gid = data.get("game_id")
        confirmed = data.get("confirmed")

        if not gid or gid not in game_sessions:
            return jsonify({"error": "game_id manquant ou invalide"}), 400
        if not isinstance(confirmed, bool):
            return jsonify({"error": "confirmed doit être true ou false"}), 400

        session = game_sessions[gid]

        # Envoyer la confirmation à l'IA
        result = session.confirm(confirmed)
        
        if result.get("status") != "ok":
            return jsonify({"error": "Erreur lors de la confirmation"}), 500

        # Si trouvé
        if result.get("result") == "found":
            # Supprimer la session
            del game_sessions[gid]
            
            return jsonify({
                "finished": True,
                "guess": "Gagné!",
                "message": "Bien joué! 🎬"
            }), 200

        # Si continue
        if result.get("action") == "guess":
            # Nouvelle proposition
            return jsonify({
                "finished": False,
                "asking_confirmation": True,
                "guess": result["content"],
                "confirmation_options": ["Oui, c'est ça!", "Non, continuer"]
            }), 200
        else:
            # Nouvelle question
            return jsonify({
                "finished": False,
                "asking_confirmation": False,
                "question": result["content"],
                "question_key": str(result["question_number"]),
                "options": OPTIONS_UI
            }), 200

    except Exception as e:
        return internal_error("confirm_guess", e)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True, use_reloader=False)
