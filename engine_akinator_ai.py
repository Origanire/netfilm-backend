#!/usr/bin/env python3
import argparse
import math
import json
import os
import random
import re
import sqlite3
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple, Set, Any
import requests

# =========================
# CONFIGURATION IA
# =========================

# URL de l'API Anthropic Claude
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")  # À configurer via variable d'environnement

# Modèle à utiliser
AI_MODEL = "claude-sonnet-4-20250514"

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
        # OPTIMISATIONS pour vitesse maximale
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
    """
    Charge les films avec leurs genres depuis les tables relationnelles.
    """
    cursor = conn.cursor()

    # Charger tous les genres en UNE requête
    cursor.execute("SELECT movie_id, genre_id FROM movie_genres")
    genre_rows = cursor.fetchall()
    
    # Construire un dictionnaire movie_id -> [genre_ids]
    movie_genres_map: Dict[int, List[int]] = {}
    for row in genre_rows:
        mid = row["movie_id"]
        gid = row["genre_id"]
        if mid not in movie_genres_map:
            movie_genres_map[mid] = []
        movie_genres_map[mid].append(gid)

    # Charger les films
    if pages:
        limit = pages * 20
        cursor.execute(
            "SELECT * FROM movies ORDER BY popularity DESC LIMIT ?",
            (limit,),
        )
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

def get_details(conn: sqlite3.Connection, movie_id: int) -> dict:
    """
    Récupère les détails complets d'un film depuis la base de données.
    """
    if movie_id in DETAILS_CACHE:
        return DETAILS_CACHE[movie_id]

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM movies WHERE id = ?", (movie_id,))
    row = cursor.fetchone()
    if row is None:
        return {}

    details = dict(row)

    # Genres
    cursor.execute(
        """
        SELECT g.id, g.name
        FROM movie_genres mg
        JOIN genres g ON mg.genre_id = g.id
        WHERE mg.movie_id = ?
        """,
        (movie_id,),
    )
    genre_rows = cursor.fetchall()
    details["genre_ids"] = [r["id"] for r in genre_rows]
    details["genres"] = [{"id": r["id"], "name": r["name"]} for r in genre_rows]

    # Keywords
    cursor.execute(
        """
        SELECT k.id, k.name
        FROM movie_keywords mk
        JOIN keywords k ON mk.keyword_id = k.id
        WHERE mk.movie_id = ?
        """,
        (movie_id,),
    )
    keyword_rows = cursor.fetchall()
    details["keywords"] = {
        "keywords": [{"id": r["id"], "name": r["name"]} for r in keyword_rows]
    }

    # Cast
    cursor.execute(
        """
        SELECT p.id, p.name, mc.character, mc.cast_order
        FROM movie_cast mc
        JOIN people p ON mc.person_id = p.id
        WHERE mc.movie_id = ?
        ORDER BY mc.cast_order
        """,
        (movie_id,),
    )
    cast_rows = cursor.fetchall()

    # Crew
    cursor.execute(
        """
        SELECT p.id, p.name, cr.job, cr.department
        FROM movie_crew cr
        JOIN people p ON cr.person_id = p.id
        WHERE cr.movie_id = ?
        """,
        (movie_id,),
    )
    crew_rows = cursor.fetchall()

    details["credits"] = {
        "cast": [
            {
                "id": r["id"],
                "name": r["name"],
                "character": r["character"],
                "order": r["cast_order"],
            }
            for r in cast_rows
        ],
        "crew": [
            {"id": r["id"], "name": r["name"], "job": r["job"], "department": r["department"]}
            for r in crew_rows
        ],
    }

    # Production countries
    countries_str = details.get("countries")
    if countries_str:
        try:
            countries = json.loads(countries_str)
            details["production_countries"] = [{"iso_3166_1": c, "name": c} for c in countries]
        except Exception:
            details["production_countries"] = []
    else:
        details["production_countries"] = []

    # Collection
    if details.get("collection_id"):
        details["belongs_to_collection"] = {
            "id": details["collection_id"],
            "name": details.get("collection_name"),
        }

    DETAILS_CACHE[movie_id] = details
    return details

# =========================
# CLASSE IA CHATBOT
# =========================

class AkinatorAI:
    """Classe pour gérer l'interaction avec l'IA pour le jeu Akinator."""
    
    def __init__(self, api_key: str, model: str = AI_MODEL):
        self.api_key = api_key
        self.model = model
        self.conversation_history = []
        self.movies_database = []
        
    def initialize_game(self, movies: List[dict]):
        """Initialise le jeu avec la liste des films disponibles."""
        self.movies_database = movies
        self.conversation_history = []
        
        # Créer un résumé compact de la base de données pour l'IA
        movie_summary = self._create_movie_summary(movies[:500])  # Limiter pour ne pas surcharger
        
        # Message système pour initialiser l'IA
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

        self.conversation_history.append({
            "role": "user",
            "content": system_prompt
        })
        
    def _create_movie_summary(self, movies: List[dict], max_movies: int = 100) -> str:
        """Crée un résumé compact des films pour l'IA."""
        summary_parts = []
        for i, movie in enumerate(movies[:max_movies]):
            title = movie.get("title", "Unknown")
            year = movie.get("release_date", "")[:4] if movie.get("release_date") else "N/A"
            genres = [GENRE_MAP.get(gid, str(gid)) for gid in movie.get("genre_ids", [])]
            genre_str = ", ".join(genres[:3]) if genres else "N/A"
            
            summary_parts.append(f"{title} ({year}) - {genre_str}")
            
        return "\n".join(summary_parts)
    
    def _call_anthropic_api(self, user_message: str) -> str:
        """Appelle l'API Anthropic Claude."""
        if not self.api_key:
            raise ValueError("Clé API Anthropic non configurée. Définissez ANTHROPIC_API_KEY.")
        
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
        
        try:
            response = requests.post(ANTHROPIC_API_URL, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            assistant_message = result["content"][0]["text"]
            
            self.conversation_history.append({
                "role": "assistant",
                "content": assistant_message
            })
            
            return assistant_message
            
        except requests.exceptions.RequestException as e:
            print(f"Erreur API: {e}")
            return "ERREUR: Impossible de contacter l'IA"
    
    def get_next_question(self, previous_answer: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """
        Obtient la prochaine question de l'IA ou une proposition de film.
        
        Returns:
            Tuple (type, content) où type est "question" ou "guess"
        """
        if previous_answer is not None:
            # Envoyer la réponse précédente
            response = self._call_anthropic_api(f"Réponse: {previous_answer}")
        else:
            # Première question
            response = self._call_anthropic_api("Commence le jeu !")
        
        # Parser la réponse
        if "GUESS:" in response:
            # L'IA propose un film
            guess = response.split("GUESS:")[1].strip().split("\n")[0].strip()
            return ("guess", guess)
        elif "QUESTION:" in response:
            # L'IA pose une question
            question = response.split("QUESTION:")[1].strip().split("\n")[0].strip()
            return ("question", question)
        else:
            # Format non reconnu, extraire le texte
            lines = response.strip().split("\n")
            for line in lines:
                if line.strip() and not line.startswith("#"):
                    if "?" in line:
                        return ("question", line.strip())
            return ("question", response.strip())
    
    def confirm_guess(self, is_correct: bool, correct_movie: Optional[str] = None):
        """Confirme si la proposition était correcte."""
        if is_correct:
            self._call_anthropic_api("Bravo ! Tu as trouvé !")
        else:
            if correct_movie:
                self._call_anthropic_api(f"Non, ce n'était pas ça. Le bon film était: {correct_movie}. Continue à poser des questions.")
            else:
                self._call_anthropic_api("Non, ce n'était pas ça. Continue à poser des questions.")


# =========================
# MOTEUR DE JEU AVEC IA
# =========================

def play_with_ai(db_path: str = DEFAULT_DB_PATH):
    """Lance une partie d'Akinator avec l'IA."""
    
    # Vérifier la clé API
    if not ANTHROPIC_API_KEY:
        print("❌ ERREUR: Clé API Anthropic non configurée.")
        print("Définissez la variable d'environnement ANTHROPIC_API_KEY")
        print("Exemple: export ANTHROPIC_API_KEY='votre_clé_api'")
        return 1
    
    print("🎬 AKINATOR FILM - VERSION IA 🤖")
    print("=" * 50)
    print("L'IA va vous poser des questions pour deviner votre film !")
    print("Répondez par: y (oui), n (non), ? (je ne sais pas)")
    print("=" * 50)
    print()
    
    # Charger la base de données
    conn = get_connection(db_path)
    load_genres(conn)
    movies = discover_movies(conn, pages=None)
    
    print(f"📊 Base de données chargée: {len(movies)} films")
    print()
    
    # Initialiser l'IA
    ai = AkinatorAI(ANTHROPIC_API_KEY)
    ai.initialize_game(movies)
    
    print("🚀 Démarrage du jeu...\n")
    
    question_count = 0
    previous_answer = None
    
    try:
        while True:
            # Obtenir la prochaine question ou proposition
            action_type, content = ai.get_next_question(previous_answer)
            
            if action_type == "guess":
                # L'IA propose un film
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
                # L'IA pose une question
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
# FONCTION API POUR LE BACKEND
# =========================

class AkinatorSession:
    """Classe pour gérer une session Akinator via API."""
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.ai: Optional[AkinatorAI] = None
        self.question_count = 0
        self.is_initialized = False
        
    def start(self) -> dict:
        """Démarre une nouvelle session et retourne la première question."""
        conn = get_connection(self.db_path)
        load_genres(conn)
        movies = discover_movies(conn, pages=None)
        
        self.ai = AkinatorAI(ANTHROPIC_API_KEY)
        self.ai.initialize_game(movies)
        self.is_initialized = True
        self.question_count = 0
        
        # Obtenir la première question
        action_type, content = self.ai.get_next_question()
        
        return {
            "status": "ok",
            "action": action_type,
            "content": content,
            "question_number": self.question_count + 1,
            "total_movies": len(movies)
        }
    
    def answer(self, response: str) -> dict:
        """Envoie une réponse et obtient la prochaine question ou proposition."""
        if not self.is_initialized or self.ai is None:
            return {"status": "error", "message": "Session non initialisée"}
        
        # Normaliser la réponse
        response = response.lower().strip()
        if response in ["y", "yes", "oui"]:
            answer = "oui"
        elif response in ["n", "no", "non"]:
            answer = "non"
        else:
            answer = "je ne sais pas"
        
        # Obtenir la prochaine action
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
            # Continuer le jeu
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
        description="Akinator de films avec IA (Claude)"
    )
    parser.add_argument(
        "--db",
        type=str,
        default=DEFAULT_DB_PATH,
        help="Chemin vers la base de données SQLite",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=ANTHROPIC_API_KEY,
        help="Clé API Anthropic",
    )
    
    args = parser.parse_args()
    
    # Configurer la clé API si fournie
    global ANTHROPIC_API_KEY
    if args.api_key:
        ANTHROPIC_API_KEY = args.api_key
    
    return play_with_ai(args.db)


if __name__ == "__main__":
    raise SystemExit(main())
