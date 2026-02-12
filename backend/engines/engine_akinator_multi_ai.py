#!/usr/bin/env python3
import os
import sqlite3
import time
from typing import Dict, List, Optional, Tuple
import requests

# =========================
# CONFIGURATION
# =========================

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
OPENAI_API_URL    = "https://api.openai.com/v1/chat/completions"
GEMINI_BASE_URL   = "https://generativelanguage.googleapis.com/v1beta/models"

CLAUDE_MODEL = "claude-opus-4-5-20251101"
OPENAI_MODEL = "gpt-4o-mini"

# Modèles Gemini dans l'ordre de fallback
GEMINI_MODELS = [
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
    "gemini-flash-latest",
]

# Nombre max de tentatives sur erreur 503
MAX_RETRIES = 3
RETRY_DELAY = 2  # secondes entre les tentatives

# =========================
# SQLITE ACCESS
# =========================

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "movies.db")
GENRE_MAP: Dict[int, str] = {}

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

def discover_movies(db_path: str, limit: int = 200) -> List[dict]:
    """Charge les films les plus populaires. Limité à 200 pour réduire la taille du prompt."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT movie_id, genre_id FROM movie_genres")
    movie_genres_map: Dict[int, List[int]] = {}
    for row in cursor.fetchall():
        movie_genres_map.setdefault(row["movie_id"], []).append(row["genre_id"])

    cursor.execute("SELECT id, title, release_date FROM movies ORDER BY popularity DESC LIMIT ?", (limit,))
    movies = []
    for row in cursor.fetchall():
        movie = dict(row)
        movie["genre_ids"] = movie_genres_map.get(movie.get("id"), [])
        movies.append(movie)

    conn.close()
    return movies

# =========================
# PROVIDER IA
# =========================

class MultiAIProvider:

    def __init__(self, provider: str = "gemini"):
        self.provider = provider.lower()
        self.conversation_history: List[dict] = []
        if self.provider not in ("claude", "gemini", "openai"):
            raise ValueError(f"Provider '{provider}' non supporté. Options: claude, gemini, openai")

    @property
    def _google_key(self) -> str:
        return os.getenv("GOOGLE_API_KEY", "")

    @property
    def _anthropic_key(self) -> str:
        return os.getenv("ANTHROPIC_API_KEY", "")

    @property
    def _openai_key(self) -> str:
        return os.getenv("OPENAI_API_KEY", "")

    def _post_with_retry(self, url: str, payload: dict, headers: dict = None, max_retries: int = MAX_RETRIES) -> requests.Response:
        """Fait un POST avec retry automatique sur 503/429."""
        kwargs = {"json": payload, "timeout": 20}
        if headers:
            kwargs["headers"] = headers

        for attempt in range(max_retries):
            resp = requests.post(url, **kwargs)

            # Succès
            if resp.ok:
                return resp

            # Erreur temporaire → retry
            if resp.status_code in (503, 429):
                if attempt < max_retries - 1:
                    wait = RETRY_DELAY * (attempt + 1)
                    print(f"⚠️  HTTP {resp.status_code} (tentative {attempt+1}/{max_retries}), retry dans {wait}s...")
                    time.sleep(wait)
                    continue

            # Erreur définitive
            return resp

        return resp

    def _call_gemini(self, user_message: str) -> str:
        api_key = self._google_key
        if not api_key:
            raise ValueError("GOOGLE_API_KEY non configurée dans .env")

        # Construire le contenu (historique + nouveau message)
        contents = []
        for msg in self.conversation_history:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})
        contents.append({"role": "user", "parts": [{"text": user_message}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.1,    # Très bas = réponses prévisibles et formatées
                "maxOutputTokens": 150, # Assez pour "QUESTION: Est-ce un film d'animation ?"
            },
        }

        last_error = None
        for model in GEMINI_MODELS:
            url = f"{GEMINI_BASE_URL}/{model}:generateContent?key={api_key}"
            resp = self._post_with_retry(url, payload)

            if resp.status_code == 429:
                print(f"⚠️  Quota dépassé sur {model}, modèle suivant...")
                last_error = f"Quota 429 sur {model}"
                continue

            if resp.status_code == 503:
                print(f"⚠️  {model} indisponible (503), modèle suivant...")
                last_error = f"Indisponible 503 sur {model}"
                continue

            if not resp.ok:
                raise RuntimeError(f"Gemini/{model} HTTP {resp.status_code}: {resp.text[:200]}")

            data = resp.json()
            # Vérifier que la réponse est valide
            candidates = data.get("candidates", [])
            if not candidates:
                print(f"⚠️  Réponse vide de {model}, modèle suivant...")
                last_error = f"Réponse vide de {model}"
                continue

            text = candidates[0]["content"]["parts"][0]["text"].strip()
            if not text:
                continue

            self.conversation_history.append({"role": "user",      "content": user_message})
            self.conversation_history.append({"role": "assistant", "content": text})
            print(f"✅ [{model}] répondu en {len(text)} chars")
            return text

        raise RuntimeError(
            f"Tous les modèles Gemini ont échoué. Dernier: {last_error}. "
            f"Réessayez dans quelques minutes."
        )

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
            "max_tokens": 150,
            "messages": self.conversation_history,
        }

        resp = self._post_with_retry(ANTHROPIC_API_URL, payload, headers)
        if not resp.ok:
            raise RuntimeError(f"Claude HTTP {resp.status_code}: {resp.text[:200]}")

        text = resp.json()["content"][0]["text"].strip()
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
            "max_tokens": 150,
            "temperature": 0.1,
        }

        resp = self._post_with_retry(OPENAI_API_URL, payload, headers)
        if not resp.ok:
            raise RuntimeError(f"OpenAI HTTP {resp.status_code}: {resp.text[:200]}")

        text = resp.json()["choices"][0]["message"]["content"].strip()
        self.conversation_history.append({"role": "assistant", "content": text})
        return text

    def call_ai(self, user_message: str) -> str:
        try:
            if self.provider == "gemini":
                return self._call_gemini(user_message)
            elif self.provider == "claude":
                return self._call_claude(user_message)
            elif self.provider == "openai":
                return self._call_openai(user_message)
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"Erreur IA ({self.provider}): {e}") from e


# =========================
# MOTEUR AKINATOR
# =========================

class AkinatorAI:

    # Prompt système minimal envoyé UNE SEULE FOIS au début
    SYSTEM_PROMPT = """Tu joues à Akinator pour deviner un film.

RÈGLE ABSOLUE: chaque réponse doit être UNE SEULE ligne complète, exactement dans l'un de ces deux formats:
QUESTION: <question complète en français se terminant par ?> 
GUESS: <titre complet du film>

INTERDIT: répondre avec une phrase incomplète, couper la question, ajouter du texte en dehors du format.

Exemples CORRECTS:
QUESTION: Est-ce un film d'animation ?
QUESTION: Le film est-il sorti avant l'an 2000 ?
QUESTION: Y a-t-il des super-héros dans ce film ?
GUESS: Le Roi Lion
GUESS: Inception

Exemples INCORRECTS (ne jamais faire ça):
Est-ce
QUESTION: Est-
un film d'animation ?"""

    def __init__(self, provider: str = "gemini"):
        self.ai = MultiAIProvider(provider)
        self.questions_asked: List[str] = []

    def initialize_game(self, movies: List[dict], genre_map: Dict[int, str]) -> Tuple[str, str]:
        """
        Initialise la conversation.
        Le résumé des films est envoyé UNE SEULE FOIS ici, pas à chaque question.
        """
        self.ai.conversation_history = []
        self.questions_asked = []

        # Résumé compact : seulement titre + année + genres principaux
        # Limité à 50 films pour garder le prompt court
        lines = []
        for m in movies[:50]:
            title  = m.get("title", "?")
            year   = (m.get("release_date") or "")[:4] or "?"
            genres = [genre_map.get(gid, "") for gid in m.get("genre_ids", [])][:2]
            genre_str = "/".join(g for g in genres if g)
            lines.append(f"{title} ({year}){' - ' + genre_str if genre_str else ''}")

        movies_list = "\n".join(lines)

        # Ce premier message contient le contexte complet
        # Les suivants seront courts (juste la réponse oui/non)
        first_message = (
            f"{self.SYSTEM_PROMPT}\n\n"
            f"Films disponibles (extrait des {len(movies)} films de la base):\n"
            f"{movies_list}\n\n"
            f"Pose ta première question."
        )

        response = self.ai.call_ai(first_message)
        return self._parse(response)

    def answer(self, user_answer: str) -> Tuple[str, str]:
        """
        Envoie la réponse. Message très court = API rapide.
        """
        # Message minimaliste, l'historique contient déjà tout le contexte
        response = self.ai.call_ai(user_answer)
        return self._parse(response)

    def confirm(self, is_correct: bool) -> Tuple[str, str]:
        if is_correct:
            return ("end", "J'ai trouvé !")
        response = self.ai.call_ai("Non")
        return self._parse(response)

    def _parse(self, response: str) -> Tuple[str, str]:
        """
        Parse strict : cherche QUESTION: ou GUESS: dans la réponse.
        Si rien trouvé, force une nouvelle question via l'API.
        """
        # Nettoyer la réponse
        response = response.strip()

        # Chercher dans chaque ligne
        for line in response.splitlines():
            line = line.strip()
            if line.upper().startswith("GUESS:"):
                content = line[6:].strip().strip('"').strip("'")
                if content:
                    return ("guess", content)
            if line.upper().startswith("QUESTION:"):
                content = line[9:].strip()
                if content:
                    self.questions_asked.append(content)
                    return ("question", content)

        # Fallback : si l'IA a répondu n'importe quoi (ex: "ootopie 2*...")
        # On lui redemande en étant très directif
        print(f"⚠️  Réponse mal formatée: '{response[:50]}' → redemande...")
        correction = self.ai.call_ai(
            "Format incorrect. Réponds UNIQUEMENT avec:\n"
            "QUESTION: <ta question> ?\nou\nGUESS: <titre du film>"
        )
        for line in correction.splitlines():
            line = line.strip()
            if line.upper().startswith("GUESS:"):
                content = line[6:].strip().strip('"').strip("'")
                if content:
                    return ("guess", content)
            if line.upper().startswith("QUESTION:"):
                content = line[9:].strip()
                if content:
                    self.questions_asked.append(content)
                    return ("question", content)

        # Dernier recours absolu
        return ("question", "Est-ce un film sorti après 2010 ?")


# =========================
# SESSION POUR L'API FLASK
# =========================

class AkinatorSession:

    def __init__(self, db_path: str = DEFAULT_DB_PATH, provider: str = "gemini"):
        self.db_path  = db_path
        self.provider = provider
        self.ai: Optional[AkinatorAI] = None
        self.question_count = 0

    def start(self) -> dict:
        load_genres_from_db(self.db_path)
        movies = discover_movies(self.db_path, limit=200)

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

        norm = response.lower().strip()
        if norm in ("y", "yes", "oui"):
            msg = "Oui"
        elif norm in ("n", "no", "non"):
            msg = "Non"
        else:
            msg = "Je ne sais pas"

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
