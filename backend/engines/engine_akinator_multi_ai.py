#!/usr/bin/env python3
import argparse
import json
import os
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import requests

# =========================
# CONFIGURATION MULTI-IA
# =========================

# Choix de l'IA (peut être configuré via variable d'environnement)
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini")  # Options: "claude", "gemini", "openai"

# Clés API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# URLs API
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
GOOGLE_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

# Modèles
CLAUDE_MODEL = "claude-sonnet-4-20250514"
GEMINI_MODEL = "gemini-2.0-flash-exp"
OPENAI_MODEL = "gpt-4o-mini"

# =========================
# SQLITE ACCESS
# =========================

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "movies.db")
_conn: Optional[sqlite3.Connection] = None

GENRE_MAP: Dict[int, str] = {}
DETAILS_CACHE: Dict[int, dict] = {}

def get_connection(db_path: str) -> sqlite3.Connection:
    """Obtient ou crée la connexion à la base de données avec optimisations SQLite."""
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(db_path)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA synchronous = OFF")
        _conn.execute("PRAGMA journal_mode = MEMORY")
        _conn.execute("PRAGMA temp_store = MEMORY")
        _conn.execute("PRAGMA cache_size = 10000")
    return _conn

def close_connection() -> None:
    """Ferme la connexion à la base de données."""
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None

def load_genres(conn: sqlite3.Connection) -> None:
    """Charge les genres depuis la base de données."""
    global GENRE_MAP
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, name FROM genres")
        GENRE_MAP = {row["id"]: row["name"] for row in cursor.fetchall()}
    except sqlite3.OperationalError:
        GENRE_MAP = {}

def discover_movies(conn: sqlite3.Connection, pages: Optional[int] = None) -> List[dict]:
    """Charge les films avec leurs genres depuis les tables relationnelles."""
    cursor = conn.cursor()
    cursor.execute("SELECT movie_id, genre_id FROM movie_genres")
    genre_rows = cursor.fetchall()
    
    movie_genres_map: Dict[int, List[int]] = {}
    for row in genre_rows:
        mid = row["movie_id"]
        gid = row["genre_id"]
        if mid not in movie_genres_map:
            movie_genres_map[mid] = []
        movie_genres_map[mid].append(gid)

    if pages:
        limit = pages * 20
        cursor.execute("SELECT * FROM movies ORDER BY popularity DESC LIMIT ?", (limit,))
    else:
        cursor.execute("SELECT * FROM movies ORDER BY popularity DESC")

    movies: List[dict] = []
    rows = cursor.fetchall()
    
    for row in rows:
        movie = dict(row)
        movie_id = movie.get("id")
        movie["genre_ids"] = movie_genres_map.get(movie_id, [])
        movies.append(movie)

    return movies

# =========================
# CLASSE IA MULTI-PROVIDER
# =========================

class MultiAIProvider:
    """Classe abstraite pour gérer différents providers IA."""
    
    def __init__(self, provider: str = "gemini"):
        self.provider = provider.lower()
        self.conversation_history = []
        
        # Valider le provider et la clé API
        if self.provider == "claude":
            if not ANTHROPIC_API_KEY:
                raise ValueError("ANTHROPIC_API_KEY non configurée")
            self.api_key = ANTHROPIC_API_KEY
            self.api_url = ANTHROPIC_API_URL
            self.model = CLAUDE_MODEL
        elif self.provider == "gemini":
            if not GOOGLE_API_KEY:
                raise ValueError("GOOGLE_API_KEY non configurée")
            self.api_key = GOOGLE_API_KEY
            self.api_url = f"{GOOGLE_API_URL}?key={GOOGLE_API_KEY}"
            self.model = GEMINI_MODEL
        elif self.provider == "openai":
            if not OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY non configurée")
            self.api_key = OPENAI_API_KEY
            self.api_url = OPENAI_API_URL
            self.model = OPENAI_MODEL
        else:
            raise ValueError(f"Provider '{provider}' non supporté. Options: claude, gemini, openai")
    
    def _call_claude(self, user_message: str) -> str:
        """Appelle l'API Anthropic Claude."""
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
        }
        
        payload = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": self.conversation_history
        }
        
        response = requests.post(self.api_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        assistant_message = result["content"][0]["text"]
        
        self.conversation_history.append({
            "role": "assistant",
            "content": assistant_message
        })
        
        return assistant_message
    
    def _call_gemini(self, user_message: str) -> str:
        """Appelle l'API Google Gemini."""
        # Gemini utilise un format différent pour l'historique
        contents = []
        
        # Ajouter l'historique
        for msg in self.conversation_history:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })
        
        # Ajouter le nouveau message
        contents.append({
            "role": "user",
            "parts": [{"text": user_message}]
        })
        
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 1024,
            }
        }
        
        response = requests.post(self.api_url, json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        assistant_message = result["candidates"][0]["content"]["parts"][0]["text"]
        
        # Mettre à jour l'historique
        self.conversation_history.append({"role": "user", "content": user_message})
        self.conversation_history.append({"role": "assistant", "content": assistant_message})
        
        return assistant_message
    
    def _call_openai(self, user_message: str) -> str:
        """Appelle l'API OpenAI."""
        messages = []
        
        # Convertir l'historique au format OpenAI
        for msg in self.conversation_history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        # Ajouter le nouveau message
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.7
        }
        
        response = requests.post(self.api_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        assistant_message = result["choices"][0]["message"]["content"]
        
        # Mettre à jour l'historique
        self.conversation_history.append({"role": "user", "content": user_message})
        self.conversation_history.append({"role": "assistant", "content": assistant_message})
        
        return assistant_message
    
    def call_ai(self, user_message: str) -> str:
        """Appelle l'IA selon le provider configuré."""
        try:
            if self.provider == "claude":
                return self._call_claude(user_message)
            elif self.provider == "gemini":
                return self._call_gemini(user_message)
            elif self.provider == "openai":
                return self._call_openai(user_message)
        except requests.exceptions.RequestException as e:
            print(f"Erreur API ({self.provider}): {e}")
            return "ERREUR: Impossible de contacter l'IA"


class AkinatorAI:
    """Classe pour gérer l'interaction avec l'IA pour le jeu Akinator."""
    
    def __init__(self, provider: str = "gemini"):
        self.ai = MultiAIProvider(provider)
        self.movies_database = []
        
    def initialize_game(self, movies: List[dict]):
        """Initialise le jeu avec la liste des films disponibles."""
        self.movies_database = movies
        self.ai.conversation_history = []
        
        movie_summary = self._create_movie_summary(movies[:500])
        
        system_prompt = f"""Tu es un assistant Akinator pour deviner des films. Tu as accès à une base de données de {len(movies)} films.

RÈGLES DU JEU:
1. Pose des questions FERMÉES (oui/non) pour éliminer des films progressivement
2. Les réponses possibles sont: "oui" (y), "non" (n), "je ne sais pas" (?)
3. Stratégie: commence par des questions larges (genre, époque) puis deviens plus précis
4. Quand tu es TRÈS CONFIANT (>90%), propose une réponse avec "GUESS: Titre du film"
5. Continue jusqu'à ce que tu trouves le film ou que tu n'aies plus de questions

EXEMPLES DE BONNES QUESTIONS:
- Est-ce un film d'action ?
- Le film est-il sorti après 2010 ?
- Y a-t-il des super-héros dans ce film ?
- Le film se passe-t-il dans l'espace ?
- Est-ce un film français ?

FORMAT DE RÉPONSE:
Pour poser une question: "QUESTION: Ta question ?"
Pour deviner: "GUESS: Titre du film"

Base de données (échantillon): {movie_summary}

Commence maintenant par poser ta première question !"""

        self.ai.conversation_history.append({
            "role": "user",
            "content": system_prompt
        })
        
    def _create_movie_summary(self, movies: List[dict], max_movies: int = 100) -> str:
        """Crée un résumé compact des films pour l'IA."""
        summary_parts = []
        for movie in movies[:max_movies]:
            title = movie.get("title", "Unknown")
            year = movie.get("release_date", "")[:4] if movie.get("release_date") else "N/A"
            genres = [GENRE_MAP.get(gid, str(gid)) for gid in movie.get("genre_ids", [])]
            genre_str = ", ".join(genres[:3]) if genres else "N/A"
            summary_parts.append(f"{title} ({year}) - {genre_str}")
        return "\n".join(summary_parts)
    
    def get_next_question(self, previous_answer: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """
        Obtient la prochaine question de l'IA ou une proposition de film.
        Returns: Tuple (type, content) où type est "question" ou "guess"
        """
        if previous_answer is not None:
            response = self.ai.call_ai(f"Réponse: {previous_answer}")
        else:
            response = self.ai.call_ai("Commence le jeu !")
        
        # Parser la réponse
        if "GUESS:" in response:
            guess = response.split("GUESS:")[1].strip().split("\n")[0].strip()
            return ("guess", guess)
        elif "QUESTION:" in response:
            question = response.split("QUESTION:")[1].strip().split("\n")[0].strip()
            return ("question", question)
        else:
            lines = response.strip().split("\n")
            for line in lines:
                if line.strip() and not line.startswith("#"):
                    if "?" in line:
                        return ("question", line.strip())
            return ("question", response.strip())
    
    def confirm_guess(self, is_correct: bool, correct_movie: Optional[str] = None):
        """Confirme si la proposition était correcte."""
        if is_correct:
            self.ai.call_ai("Bravo ! Tu as trouvé !")
        else:
            if correct_movie:
                self.ai.call_ai(f"Non, ce n'était pas ça. Le bon film était: {correct_movie}. Continue à poser des questions.")
            else:
                self.ai.call_ai("Non, ce n'était pas ça. Continue à poser des questions.")


# =========================
# MOTEUR DE JEU AVEC IA
# =========================

def play_with_ai(db_path: str = DEFAULT_DB_PATH, provider: str = "gemini"):
    """Lance une partie d'Akinator avec l'IA."""
    
    print(f"🎬 AKINATOR FILM - VERSION IA ({provider.upper()}) 🤖")
    print("=" * 50)
    print("L'IA va vous poser des questions pour deviner votre film !")
    print("Répondez par: y (oui), n (non), ? (je ne sais pas)")
    print("=" * 50)
    print()
    
    conn = get_connection(db_path)
    load_genres(conn)
    movies = discover_movies(conn, pages=None)
    
    print(f"📊 Base de données chargée: {len(movies)} films")
    print()
    
    try:
        ai = AkinatorAI(provider)
    except ValueError as e:
        print(f"❌ ERREUR: {e}")
        print(f"Configurez la clé API appropriée pour {provider}")
        return 1
    
    ai.initialize_game(movies)
    
    print("🚀 Démarrage du jeu...\n")
    
    question_count = 0
    previous_answer = None
    
    try:
        while True:
            action_type, content = ai.get_next_question(previous_answer)
            
            if action_type == "guess":
                print(f"\n💡 JE PENSE QUE C'EST: {content}")
                print()
                
                user_input = input("Est-ce correct ? (y/n) : ").strip().lower()
                
                if user_input == "y" or user_input == "yes" or user_input == "oui":
                    ai.confirm_guess(True)
                    print(f"\n✅ J'AI TROUVÉ en {question_count} questions !")
                    print(f"🎬 Film: {content}")
                    break
                else:
                    ai.confirm_guess(False)
                    print("\n❌ Dommage ! Je continue...\n")
                    previous_answer = "Non, ce n'est pas le bon film."
                    
            elif action_type == "question":
                question_count += 1
                print(f"❓ Question #{question_count}: {content}")
                print()
                
                user_input = input("Réponse (y/n/?) : ").strip().lower()
                
                if user_input == "y" or user_input == "yes" or user_input == "oui":
                    previous_answer = "oui"
                elif user_input == "n" or user_input == "no" or user_input == "non":
                    previous_answer = "non"
                elif user_input == "?" or user_input == "idk" or user_input == "ne sais pas":
                    previous_answer = "je ne sais pas"
                else:
                    print("Réponse non valide, interprété comme '?'")
                    previous_answer = "je ne sais pas"
                
                print()
    
    except KeyboardInterrupt:
        print("\n\n⚠️ Jeu interrompu par l'utilisateur")
        return 1
    
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        close_connection()
    
    return 0


# =========================
# CLASSE SESSION POUR API
# =========================

class AkinatorSession:
    """Classe pour gérer une session Akinator via API."""
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH, provider: str = "gemini"):
        self.db_path = db_path
        self.provider = provider
        self.ai: Optional[AkinatorAI] = None
        self.question_count = 0
        self.is_initialized = False
        
    def start(self) -> dict:
        """Démarre une nouvelle session et retourne la première question."""
        conn = get_connection(self.db_path)
        load_genres(conn)
        movies = discover_movies(conn, pages=None)
        
        self.ai = AkinatorAI(self.provider)
        self.ai.initialize_game(movies)
        self.is_initialized = True
        self.question_count = 0
        
        action_type, content = self.ai.get_next_question()
        
        return {
            "status": "ok",
            "action": action_type,
            "content": content,
            "question_number": self.question_count + 1,
            "total_movies": len(movies),
            "ai_provider": self.provider
        }
    
    def answer(self, response: str) -> dict:
        """Envoie une réponse et obtient la prochaine question ou proposition."""
        if not self.is_initialized or self.ai is None:
            return {"status": "error", "message": "Session non initialisée"}
        
        response = response.lower().strip()
        if response in ["y", "yes", "oui"]:
            answer = "oui"
        elif response in ["n", "no", "non"]:
            answer = "non"
        else:
            answer = "je ne sais pas"
        
        action_type, content = self.ai.get_next_question(answer)
        
        if action_type == "question":
            self.question_count += 1
        
        return {
            "status": "ok",
            "action": action_type,
            "content": content,
            "question_number": self.question_count
        }
    
    def confirm(self, is_correct: bool) -> dict:
        """Confirme si la proposition était correcte."""
        if not self.is_initialized or self.ai is None:
            return {"status": "error", "message": "Session non initialisée"}
        
        self.ai.confirm_guess(is_correct)
        
        if is_correct:
            return {
                "status": "ok",
                "result": "found",
                "questions_asked": self.question_count
            }
        else:
            action_type, content = self.ai.get_next_question()
            return {
                "status": "ok",
                "result": "continue",
                "action": action_type,
                "content": content,
                "question_number": self.question_count
            }


# =========================
# POINT D'ENTRÉE
# =========================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Akinator de films avec IA (Multi-provider)"
    )
    parser.add_argument("--db", type=str, default=DEFAULT_DB_PATH, help="Chemin vers la base de données SQLite")
    parser.add_argument("--provider", type=str, default=AI_PROVIDER, 
                       choices=["claude", "gemini", "openai"],
                       help="Provider IA à utiliser (claude/gemini/openai)")
    
    args = parser.parse_args()
    
    return play_with_ai(args.db, args.provider)


if __name__ == "__main__":
    raise SystemExit(main())
