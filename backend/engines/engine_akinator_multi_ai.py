#!/usr/bin/env python3
import json
import os
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests

# =========================
# CONFIGURATION MULTI-IA
# =========================

# URLs API
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
OPENAI_API_URL    = "https://api.openai.com/v1/chat/completions"

# Modèles
CLAUDE_MODEL = "claude-opus-4-5-20251101"
GEMINI_MODEL = "gemini-2.0-flash"
OPENAI_MODEL = "gpt-4o-mini"

# NOTE: Les clés API sont lues dynamiquement via os.getenv() à chaque appel,
# pas au chargement du module, pour être sûr que le .env est déjà chargé.

# =========================
# SQLITE ACCESS
# =========================

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "movies.db")

GENRE_MAP:    Dict[int, str]  = {}
DETAILS_CACHE: Dict[int, dict] = {}

def load_genres_from_db(db_path: str) -> None:
    global GENRE_MAP
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM genres")
        GENRE_MAP = {row["id"]: row["name"] for row in cursor.fetchall()}
        conn.close()
    except Exception:
        GENRE_MAP = {}

def discover_movies(db_path: str, limit: int = 500) -> List[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT movie_id, genre_id FROM movie_genres")
    movie_genres_map: Dict[int, List[int]] = {}
    for row in cursor.fetchall():
        mid, gid = row["movie_id"], row["genre_id"]
        movie_genres_map.setdefault(mid, []).append(gid)

    cursor.execute("SELECT * FROM movies ORDER BY popularity DESC LIMIT ?", (limit,))
    movies = []
    for row in cursor.fetchall():
        movie = dict(row)
        movie["genre_ids"] = movie_genres_map.get(movie.get("id"), [])
        movies.append(movie)

    conn.close()
    return movies

# =========================
# CLASSE IA MULTI-PROVIDER
# =========================

class MultiAIProvider:

    def __init__(self, provider: str = "gemini"):
        self.provider = provider.lower()
        self.conversation_history: List[dict] = []

        if self.provider not in ("claude", "gemini", "openai"):
            raise ValueError(f"Provider '{provider}' non supporté. Options: claude, gemini, openai")

    # ---- clés lues dynamiquement ----
    @property
    def _google_key(self) -> str:
        return os.getenv("GOOGLE_API_KEY", "")

    @property
    def _anthropic_key(self) -> str:
        return os.getenv("ANTHROPIC_API_KEY", "")

    @property
    def _openai_key(self) -> str:
        return os.getenv("OPENAI_API_KEY", "")

    # ---- appels API ----
    def _call_gemini(self, user_message: str) -> str:
        api_key = self._google_key
        if not api_key:
            raise ValueError("GOOGLE_API_KEY non configurée dans .env")

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{GEMINI_MODEL}:generateContent?key={api_key}"
        )

        contents = []
        for msg in self.conversation_history:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})
        contents.append({"role": "user", "parts": [{"text": user_message}]})

        payload = {
            "contents": contents,
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 512},
        }

        resp = requests.post(url, json=payload, timeout=30)

        # Afficher la vraie erreur si ça échoue
        if not resp.ok:
            raise RuntimeError(f"Gemini HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]

        self.conversation_history.append({"role": "user",      "content": user_message})
        self.conversation_history.append({"role": "assistant", "content": text})
        return text

    def _call_claude(self, user_message: str) -> str:
        api_key = self._anthropic_key
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY non configurée dans .env")

        self.conversation_history.append({"role": "user", "content": user_message})

        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": CLAUDE_MODEL,
            "max_tokens": 512,
            "messages": self.conversation_history,
        }

        resp = requests.post(ANTHROPIC_API_URL, headers=headers, json=payload, timeout=30)
        if not resp.ok:
            raise RuntimeError(f"Claude HTTP {resp.status_code}: {resp.text[:300]}")

        text = resp.json()["content"][0]["text"]
        self.conversation_history.append({"role": "assistant", "content": text})
        return text

    def _call_openai(self, user_message: str) -> str:
        api_key = self._openai_key
        if not api_key:
            raise ValueError("OPENAI_API_KEY non configurée dans .env")

        self.conversation_history.append({"role": "user", "content": user_message})

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": OPENAI_MODEL,
            "messages": self.conversation_history,
            "max_tokens": 512,
            "temperature": 0.7,
        }

        resp = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=30)
        if not resp.ok:
            raise RuntimeError(f"OpenAI HTTP {resp.status_code}: {resp.text[:300]}")

        text = resp.json()["choices"][0]["message"]["content"]
        self.conversation_history.append({"role": "assistant", "content": text})
        return text

    def call_ai(self, user_message: str) -> str:
        """Appelle l'IA et remonte les erreurs lisiblement."""
        try:
            if self.provider == "gemini":
                return self._call_gemini(user_message)
            elif self.provider == "claude":
                return self._call_claude(user_message)
            elif self.provider == "openai":
                return self._call_openai(user_message)
        except Exception as e:
            # Afficher l'erreur complète dans les logs du serveur
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"Erreur IA ({self.provider}): {e}") from e


# =========================
# MOTEUR DE JEU AKINATOR
# =========================

class AkinatorAI:

    def __init__(self, provider: str = "gemini"):
        self.ai = MultiAIProvider(provider)

    def initialize_game(self, movies: List[dict], genre_map: Dict[int, str]) -> str:
        """Initialise la conversation et retourne la première question."""
        self.ai.conversation_history = []

        # Résumé compact des films (100 premiers par popularité)
        lines = []
        for m in movies[:100]:
            title  = m.get("title", "?")
            year   = (m.get("release_date") or "")[:4] or "N/A"
            genres = [genre_map.get(gid, "") for gid in m.get("genre_ids", [])][:3]
            lines.append(f"{title} ({year}) - {', '.join(g for g in genres if g)}")
        summary = "\n".join(lines)

        system_prompt = (
            f"Tu es un Akinator de films. Tu dois deviner le film auquel l'utilisateur pense "
            f"en posant des questions oui/non.\n\n"
            f"RÈGLES STRICTES:\n"
            f"- Pose UNE seule question à la fois\n"
            f"- Format obligatoire pour une question : QUESTION: <ta question> ?\n"
            f"- Format obligatoire pour une proposition : GUESS: <titre exact du film>\n"
            f"- Commence large (genre, époque, pays) puis affine\n"
            f"- Propose un film quand tu es très confiant (après 5+ questions)\n"
            f"- Utilise UNIQUEMENT le format QUESTION: ou GUESS:, rien d'autre\n\n"
            f"Base de films disponibles ({len(movies)} films, échantillon):\n{summary}\n\n"
            f"Pose maintenant ta première question."
        )

        response = self.ai.call_ai(system_prompt)
        return self._parse_response(response)

    def answer(self, user_answer: str) -> Tuple[str, str]:
        """Envoie la réponse de l'utilisateur, retourne (type, contenu)."""
        response = self.ai.call_ai(f"Réponse: {user_answer}")
        return self._parse_response(response)

    def confirm(self, is_correct: bool) -> Tuple[str, str]:
        """Confirme ou infirme la proposition, retourne (type, contenu)."""
        if is_correct:
            return ("end", "Bravo, j'ai trouvé !")
        response = self.ai.call_ai("Non, ce n'est pas ce film. Continue à poser des questions.")
        return self._parse_response(response)

    def _parse_response(self, response: str) -> Tuple[str, str]:
        """Parse la réponse de l'IA → (type, contenu). type = 'question' ou 'guess'."""
        # Chercher GUESS: en premier
        if "GUESS:" in response:
            content = response.split("GUESS:")[1].strip().split("\n")[0].strip()
            return ("guess", content)

        # Chercher QUESTION:
        if "QUESTION:" in response:
            content = response.split("QUESTION:")[1].strip().split("\n")[0].strip()
            return ("question", content)

        # Fallback : prendre la première ligne qui contient un "?"
        for line in response.strip().splitlines():
            line = line.strip()
            if line and "?" in line:
                return ("question", line)

        # Dernier recours
        return ("question", response.strip()[:200])


# =========================
# SESSION POUR L'API FLASK
# =========================

class AkinatorSession:

    def __init__(self, db_path: str = DEFAULT_DB_PATH, provider: str = "gemini"):
        self.db_path   = db_path
        self.provider  = provider
        self.ai: Optional[AkinatorAI] = None
        self.question_count = 0

    def start(self) -> dict:
        load_genres_from_db(self.db_path)
        movies = discover_movies(self.db_path, limit=500)

        self.ai = AkinatorAI(self.provider)
        self.question_count = 0

        q_type, content = self.ai.initialize_game(movies, GENRE_MAP)

        if q_type == "question":
            self.question_count += 1

        return {
            "status": "ok",
            "action": q_type,
            "content": content,
            "question_number": self.question_count,
            "total_movies": len(movies),
        }

    def answer(self, response: str) -> dict:
        if self.ai is None:
            return {"status": "error", "message": "Session non initialisée"}

        # Normaliser la réponse
        norm = response.lower().strip()
        if norm in ("y", "yes", "oui"):
            msg = "oui"
        elif norm in ("n", "no", "non"):
            msg = "non"
        else:
            msg = "je ne sais pas"

        q_type, content = self.ai.answer(msg)
        if q_type == "question":
            self.question_count += 1

        return {
            "status": "ok",
            "action": q_type,
            "content": content,
            "question_number": self.question_count,
        }

    def confirm(self, is_correct: bool) -> dict:
        if self.ai is None:
            return {"status": "error", "message": "Session non initialisée"}

        q_type, content = self.ai.confirm(is_correct)

        if q_type == "end":
            return {"status": "ok", "result": "found", "questions_asked": self.question_count}

        if q_type == "question":
            self.question_count += 1

        return {
            "status": "ok",
            "result": "continue",
            "action": q_type,
            "content": content,
            "question_number": self.question_count,
        }
