#!/usr/bin/env python3
from __future__ import annotations

import os
import sqlite3
import traceback
from pathlib import Path
from typing import Dict, Any

from flask import Flask, request, jsonify
from flask_cors import CORS

from engines.engine_akinator import (
    load_genres,
    discover_movies,
    default_questions,
    build_dynamic_keyword_questions,
    build_dynamic_questions,
    build_dynamic_year_questions,
    build_top_validation_questions,
    build_binary_disambiguation_questions,
    init_state,
    sort_candidates,
    choose_best_question,
    update_state_with_answer,
    should_enter_guess_mode,
    score_of,
    short_movie_str,
)

app = Flask(__name__)

CORS(app, resources={
    r"/*": {
        "origins": ["https://origanire.github.io"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"],
    }
})

OPTIONS_UI = ["Oui", "Non", "Je ne sais pas", "Probablement", "Probablement pas"]

UI_TO_ENGINE = {
    "Oui": "y",
    "Non": "n",
    "Je ne sais pas": "?",
    "Probablement": "py",
    "Probablement pas": "pn",
    "y": "y",
    "n": "n",
    "?": "?",
    "py": "py",
    "pn": "pn",
}

# Session: on ne stocke PAS les questions (car elles capturent conn)
game_state: Dict[str, Dict[str, Any]] = {}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def db_path() -> str:
    return str(repo_root() / "movies.db")


def open_db() -> sqlite3.Connection:
    p = db_path()
    if not os.path.exists(p):
        raise FileNotFoundError(f"movies.db introuvable: {p}")

    conn = sqlite3.connect(p, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA synchronous = OFF")
    conn.execute("PRAGMA journal_mode = MEMORY")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA cache_size = 10000")
    return conn


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


def build_all_questions(conn, state):
    """Construit l'ensemble complet des questions disponibles pour l'état courant."""
    static_qs = default_questions(conn)
    dyn_kw = build_dynamic_keyword_questions(conn, state.candidates, state.asked, top_k=80)
    dyn_people = build_dynamic_questions(conn, state.candidates, state.asked, top_k=60)
    dyn_years = build_dynamic_year_questions(state.candidates, state.asked)
    validation_qs = build_top_validation_questions(conn, state.candidates, state.asked)
    binary_qs = build_binary_disambiguation_questions(conn, state.candidates, state.asked)
    # Ordre de priorité: validation > binaire > dynamiques > statiques
    return validation_qs + binary_qs + dyn_kw + dyn_people + dyn_years + static_qs


@app.get("/")
def health():
    return jsonify({"status": "ok", "service": "Akinator API", "db": db_path()}), 200


@app.post("/start")
def start_game():
    try:
        conn = open_db()
        try:
            load_genres(conn)

            movies = discover_movies(conn)
            state = init_state(movies)
            sort_candidates(state)

            all_questions = build_all_questions(conn, state)

            q = choose_best_question(
                state.candidates,
                all_questions,
                state.asked,
                is_first_question=True,
                state=state,
            )
            if q is None:
                return jsonify({"error": "Aucune question trouvée"}), 400

            gid = new_game_id()

            game_state[gid] = {
                "state": state,
                "current_qkey": q.key,
            }

            return jsonify(
                {
                    "game_id": gid,
                    "question": q.text,
                    "question_key": q.key,
                    "options": OPTIONS_UI,
                    "candidates_count": len(state.candidates),
                    "finished": False,
                }
            ), 200
        finally:
            conn.close()
    except Exception as e:
        return internal_error("start_game", e)


@app.post("/answer")
def answer():
    try:
        data = request.get_json(silent=True) or {}
        gid = data.get("game_id")
        ui_answer = data.get("answer")
        q_key = data.get("question_key")

        if not gid:
            return jsonify({"error": "game_id manquant"}), 400
        if gid not in game_state:
            return jsonify({"error": "Partie non trouvée"}), 404

        if ui_answer not in UI_TO_ENGINE:
            return jsonify({"error": "Réponse invalide", "got": ui_answer}), 400

        session = game_state[gid]
        state = session["state"]

        if not q_key:
            q_key = session.get("current_qkey")
        if not q_key:
            return jsonify({"error": "question_key manquant"}), 400

        conn = open_db()
        try:
            load_genres(conn)

            # Chercher la question dans TOUTES les questions disponibles
            all_questions = build_all_questions(conn, state)
            q = next((qq for qq in all_questions if qq.key == q_key), None)
            
            # Fallback sur les questions statiques si non trouvée
            if q is None:
                static_qs = default_questions(conn)
                q = next((qq for qq in static_qs if qq.key == q_key), None)
            
            if q is None:
                return jsonify({"error": "Question introuvable", "question_key": q_key}), 400

            engine_answer = UI_TO_ENGINE[ui_answer]

            state.asked.add(q.key)
            state.question_count += 1

            update_state_with_answer(state, q, engine_answer, max_strikes=3)
            sort_candidates(state)

            return _next_step(conn, state, session)

        finally:
            conn.close()

    except Exception as e:
        return internal_error("answer", e)


def _next_step(conn, state, session):
    """Logique commune pour déterminer: proposer question ou film.
    AMÉLIORÉ: Utilise should_enter_guess_mode pour une convergence plus intelligente.
    """
    
    if not state.candidates:
        return jsonify({"finished": True, "guess": "Désolé, j'ai échoué! 😅"}), 200
    
    # AMÉLIORATION: Utiliser la même logique que le mode CLI
    if should_enter_guess_mode(state):
        film = state.candidates[0]
        session["proposed_film_id"] = film.get("id")
        return jsonify({
            "finished": False,
            "asking_confirmation": True,
            "guess": film.get("title", "Inconnu"),
            "guess_year": film.get("release_date", "")[:4] if film.get("release_date") else "",
            "guess_id": film.get("id"),
            "candidates_count": len(state.candidates),
            "question_count": state.question_count,
            "confirmation_options": ["Oui, c'est ça!", "Non, continuer"]
        }), 200
    
    # Construire toutes les questions disponibles
    all_questions = build_all_questions(conn, state)
    
    q2 = choose_best_question(
        state.candidates,
        all_questions,
        state.asked,
        is_first_question=False,
        state=state,
    )

    if q2 is None:
        # Plus de questions → proposer le top film
        film = state.candidates[0]
        session["proposed_film_id"] = film.get("id")
        return jsonify({
            "finished": False,
            "asking_confirmation": True,
            "guess": film.get("title", "Inconnu"),
            "guess_year": film.get("release_date", "")[:4] if film.get("release_date") else "",
            "guess_id": film.get("id"),
            "candidates_count": len(state.candidates),
            "question_count": state.question_count,
            "confirmation_options": ["Oui, c'est ça!", "Non, continuer"]
        }), 200

    session["current_qkey"] = q2.key
    return jsonify({
        "finished": False,
        "question": q2.text,
        "question_key": q2.key,
        "options": OPTIONS_UI,
        "candidates_count": len(state.candidates),
        "question_count": state.question_count,
    }), 200


@app.post("/confirm")
def confirm_guess():
    try:
        data = request.get_json(silent=True) or {}
        gid = data.get("game_id")
        confirmed = data.get("confirmed")

        if not gid or gid not in game_state:
            return jsonify({"error": "game_id manquant ou invalide"}), 400
        if not isinstance(confirmed, bool):
            return jsonify({"error": "confirmed doit être true ou false"}), 400

        session = game_state[gid]
        state = session["state"]

        if confirmed:
            film = state.candidates[0] if state.candidates else {}
            return jsonify({
                "finished": True,
                "guess": film.get("title", "Inconnu"),
                "message": "Bien joué! 🎬"
            }), 200

        # Rejeter le film proposé et l'éliminer du pool
        if state.candidates:
            rejected_id = session.get("proposed_film_id")
            if rejected_id:
                state.candidates = [m for m in state.candidates if m.get("id") != rejected_id]
                state.scores.pop(rejected_id, None)
                state.strikes.pop(rejected_id, None)
            else:
                state.candidates = state.candidates[1:]
            sort_candidates(state)

        if not state.candidates:
            return jsonify({
                "finished": True,
                "guess": "Désolé, j'ai échoué! 😅"
            }), 200

        # Continuer avec des questions
        conn = open_db()
        try:
            load_genres(conn)
            return _next_step(conn, state, session)
        finally:
            conn.close()

    except Exception as e:
        return internal_error("confirm_guess", e)


@app.get("/debug/<gid>")
def debug_state(gid: str):
    """Endpoint de debug pour voir l'état actuel d'une partie."""
    if gid not in game_state:
        return jsonify({"error": "Partie non trouvée"}), 404
    state = game_state[gid]["state"]
    top5 = [
        {
            "title": m.get("title"),
            "year": m.get("release_date", "")[:4],
            "score": state.scores.get(m.get("id"), 0.0),
        }
        for m in state.candidates[:5]
    ]
    return jsonify({
        "candidates_count": len(state.candidates),
        "question_count": state.question_count,
        "top5": top5,
    }), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True, use_reloader=False)
