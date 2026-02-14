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
    OPTIMISATION: 1 seule requête pour tous les genres au lieu de N requêtes.
    """
    cursor = conn.cursor()

    # OPTIMISATION MAJEURE: Charger tous les genres en UNE requête
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
        # Utiliser le dictionnaire (instantané) au lieu de faire une requête SQL
        movie["genre_ids"] = movie_genres_map.get(movie_id, [])
        movies.append(movie)

    return movies

def get_details(conn: sqlite3.Connection, movie_id: int) -> dict:
    """
    Récupère les détails complets d'un film depuis la base de données.
    Cache agressif pour éviter des allers-retours SQLite.
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

    # Production countries (si présent)
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
# Utils
# =========================

def safe_year(release_date: Optional[str]) -> Optional[int]:
    if not release_date:
        return None
    try:
        return int(str(release_date)[:4])
    except ValueError:
        return None

def normalize_title(title: str) -> str:
    """
    Normalisation agressive (articles + ponctuation + casing).
    Exemple: "Marvel's The Avengers" -> "MARVELSTHEAVENGERS" puis article retiré -> "MARVELSTHEAVENGERS"
    et pour les tests de "starts_with", on retire les articles au début avant suppression.
    """
    t = str(title).strip()
    t = re.sub(r"^(the|a|an|le|la|les|l'|un|une|des)\s+", "", t, flags=re.IGNORECASE)
    t = re.sub(r"[^A-Za-z0-9]", "", t)
    return t.upper()

def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x

def movie_id(m: dict) -> Optional[int]:
    mid = m.get("id")
    if mid is None:
        return None
    try:
        return int(mid)
    except Exception:
        return None


# =========================
# Question model + quality scoring
# =========================

def entropy_split(yes: int, no: int) -> float:
    n = yes + no
    if n == 0:
        return 0.0

    def h(x: int) -> float:
        if x == 0:
            return 0.0
        p = x / n
        return -p * math.log2(p)

    return h(yes) + h(no)

def split_counts(candidates: List[dict], predicate: Callable[[dict], Optional[bool]]) -> Tuple[int, int, int]:
    yes = no = unk = 0
    for m in candidates:
        r = predicate(m)
        if r is True:
            yes += 1
        elif r is False:
            no += 1
        else:
            unk += 1
    return yes, no, unk

@dataclass(frozen=True)
class Question:
    key: str
    text: str
    predicate: Callable[[dict], Optional[bool]]
    # NOUVEAU: dépendances logiques
    requires: Optional[Set[str]] = None  # questions qui doivent avoir été posées
    excludes: Optional[Set[str]] = None  # questions qui excluent celle-ci

    def score(self, candidates: List[dict]) -> float:
        """
        Calcule le score de discrimination de cette question.
        OPTIMISATION: Échantillonne si trop de candidats pour gagner du temps.
        """
        # OPTIMISATION: Sur grande liste, échantillonner pour calculer plus vite
        sample = candidates
        if len(candidates) > 500:
            sample = candidates[:500]
        
        yes, no, unk = split_counts(sample, self.predicate)

        if (yes == 0 and unk == 0) or (no == 0 and unk == 0):
            return -1.0

        base = entropy_split(yes, no)

        n = len(sample)
        unk_ratio = (unk / n) if n else 1.0
        # AMÉLIORATION: pénalité plus forte sur unk (données manquantes = moins fiable)
        score = base - 0.5 * unk_ratio

        # HIÉRARCHIE des boosters - du plus fort au plus faible
        # PRIORITÉ 0: Questions de langue (posées EN PREMIER, toujours)
        if self.key.startswith("language_"):
            score *= 120.0  # MEGA BOOST absolu
        # PRIORITÉ 1: Questions de VALIDATION du TOP candidat (ultra prioritaires)
        elif self.key.startswith("validate_"):
            # AMÉLIORATION: boost adaptatif selon la taille du pool
            if n <= 20:
                score *= 80.0   # Très peu de candidats = validation critique
            elif n <= 50:
                score *= 60.0
            else:
                score *= 40.0
        # PRIORITÉ 2: Réalisateurs (très discriminants)
        elif self.key.startswith(("director_", "dyn_director_")):
            score *= 2.0
        # PRIORITÉ 3: Franchises (exclusives)
        elif self.key.startswith("franchise_"):
            score *= 1.8
        # PRIORITÉ 4: Personnages
        elif self.key.startswith("char_"):
            score *= 1.5
        # PRIORITÉ 5: Acteurs
        elif self.key.startswith(("actor_", "dyn_actor_")):
            if 0 < yes < n:
                score *= 1.4
        # PRIORITÉ 6: Mots-clés dynamiques (très utiles sur petit pool)
        elif self.key.startswith("dyn_keyword_"):
            if n <= 30:
                score *= 1.3
        # PRIORITÉ 7: Localisation/Événement/Objet
        elif self.key.startswith(("location_", "event_", "object_")):
            score *= 1.25
        # JOKER titre: seulement utile sur petit pool
        elif self.key.startswith("joker_title_") and n <= 10:
            score *= 1.2

        return score


def get_question_type(q: Question) -> str:
    """Détecte le type d'une question pour tracking de diversité."""
    if q.key.startswith("validate_"):
        return "validation"  # NOUVEAU: Questions de validation du TOP
    elif q.key.startswith("language_"):
        return "language"
    elif q.key.startswith(("actor_", "dyn_actor_")):
        return "actor"
    elif q.key.startswith(("director_", "dyn_director_")):
        return "director"
    elif q.key.startswith("genre_"):
        return "genre"
    elif q.key.startswith(("franchise_", "char_")):
        return "franchise"
    elif q.key.startswith(("year_", "decade_", "after_", "before_")):
        return "date"
    elif q.key.startswith("dyn_keyword_"):
        return "keyword"
    elif q.key.startswith("runtime_"):
        return "runtime"
    elif q.key.startswith("joker_title_"):
        return "title"
    elif q.key.startswith(("big_budget", "small_budget", "box_office", "is_indie")):
        return "finance"
    elif q.key.startswith(("popular", "very_popular")):
        return "popularity"
    elif q.key.startswith(("is_saga", "is_standalone", "is_adaptation", "based_on_", "superhero")):
        return "meta"  # Méta-info sur le film
    elif q.key.startswith(("is_american", "is_french", "is_european", "is_asian")):
        return "origin"
    elif q.key.startswith(("is_animation", "is_live_action", "is_short", "is_feature")):
        return "format"
    elif q.key.startswith("theme_"):
        return "theme"  # Séparer theme de keyword
    else:
        return "other"


def count_recent_type(state: 'EngineState', q_type: str, window: int = 5) -> int:
    """Compte combien de questions du même type dans les N dernières."""
    if not state.recent_question_types:
        return 0
    
    recent = state.recent_question_types[-window:]  # Dernières N questions
    return recent.count(q_type)


def should_diversify(state: 'EngineState', q: Question, max_consecutive: int = 2) -> bool:
    """
    Retourne True si on devrait éviter cette question pour diversifier.
    AMÉLIORATION: Max 2 consécutives (au lieu de 3) pour plus de variété.
    """
    q_type = get_question_type(q)
    
    # Exceptions: TOUJOURS autoriser ces types (prioritaires)
    if q_type in ["language", "validation"]:
        return False  # JAMAIS pénaliser langue et validation
    
    # Compter les questions récentes du même type
    consecutive_count = count_recent_type(state, q_type, window=max_consecutive)
    
    # Si on a déjà posé max_consecutive questions de ce type → diversifier
    if consecutive_count >= max_consecutive:
        return True
    
    # NOUVEAU: Aussi vérifier la diversité globale des 5 dernières questions
    if len(state.recent_question_types) >= 5:
        last_5 = state.recent_question_types[-5:]
        unique_types = len(set(last_5))
        
        # Si moins de 3 types différents dans les 5 dernières → encourager diversité
        if unique_types < 3 and last_5.count(q_type) >= 2:
            return True
    
    return False


def choose_best_question(candidates: List[dict], questions: List[Question], asked: Set[str], 
                         is_first_question: bool = False, state: Optional['EngineState'] = None) -> Optional[Question]:
    """
    Choisit la meilleure question de manière déterministe et RAPIDE.
    OPTIMISATION: Échantillonne si trop de questions pour éviter de tout scorer.
    AMÉLIORATION: Aléatoire sur la première question + pénalité de diversité allégée.
    """
    contradictions = {
        "big_budget": "small_budget",
        "small_budget": "big_budget",
        "runtime_lt_90": "runtime_ge_150",
        "runtime_ge_150": "runtime_lt_90",
        "is_animation": "is_live_action",
        "is_live_action": "is_animation",
        "is_saga": "is_standalone",
        "is_standalone": "is_saga",
        "after_1980": "before_1970",
        "after_2000": "before_1990",
        "after_2020": "before_2010",
    }

    jokers_used = sum(1 for q in asked if q.startswith("joker_title_"))

    # Filtrer les questions valides
    valid_questions = []
    for q in questions:
        if q.key in asked:
            continue
        if q.requires and not q.requires.issubset(asked):
            continue
        if q.excludes and q.excludes.intersection(asked):
            continue
        if q.key.startswith("joker_title_") and jokers_used >= 1:
            continue
        if q.key in contradictions and contradictions[q.key] in asked:
            continue
        valid_questions.append(q)
    
    if not valid_questions:
        return None
    
    # OPTIMISATION CRITIQUE: Si trop de questions, échantillonner pour scorer plus vite
    if len(valid_questions) > 200:
        # Priorité aux questions validate_ et language_ avant d'échantillonner
        priority_qs = [q for q in valid_questions if q.key.startswith(("validate_", "language_"))]
        rest = [q for q in valid_questions if not q.key.startswith(("validate_", "language_"))]
        valid_questions = priority_qs + rest[:200 - len(priority_qs)]

    scored: List[Tuple[Question, float]] = []
    for q in valid_questions:
        s = q.score(candidates)
        if s > 0:
            # AMÉLIORATION: Pénalité de diversité moins agressive (0.1 au lieu de 0.01)
            # pour ne pas bloquer des questions pertinentes
            if state and should_diversify(state, q, max_consecutive=3):
                s *= 0.1  # Pénalité modérée (90% de réduction)
            
            scored.append((q, s))

    if not scored:
        return None

    scored.sort(key=lambda x: x[1], reverse=True)
    
    # AMÉLIORATION: Aléatoire sur la première question (top 3 au lieu de top 5)
    if is_first_question and len(scored) >= 3:
        top_3 = scored[:3]
        return random.choice(top_3)[0]
    
    return scored[0][0]


# =========================
# Predicates - ANNÉE
# =========================

def pred_after_year(year: int) -> Callable[[dict], Optional[bool]]:
    def p(m: dict) -> Optional[bool]:
        y = safe_year(m.get("release_date"))
        if y is None:
            return None
        return y >= year
    return p

def pred_before_year(year: int) -> Callable[[dict], Optional[bool]]:
    def p(m: dict) -> Optional[bool]:
        y = safe_year(m.get("release_date"))
        if y is None:
            return None
        return y < year
    return p

def pred_exact_year(year: int) -> Callable[[dict], Optional[bool]]:
    """Vérifie si le film est sorti exactement cette année."""
    def p(m: dict) -> Optional[bool]:
        y = safe_year(m.get("release_date"))
        if y is None:
            return None
        return y == year
    return p

def pred_decade(start_year: int) -> Callable[[dict], Optional[bool]]:
    """Vérifie si le film est sorti dans une décennie (ex: 1980-1989)."""
    def p(m: dict) -> Optional[bool]:
        y = safe_year(m.get("release_date"))
        if y is None:
            return None
        return start_year <= y < (start_year + 10)
    return p

def pred_year_range(start: int, end: int) -> Callable[[dict], Optional[bool]]:
    """Vérifie si le film est sorti dans une plage d'années."""
    def p(m: dict) -> Optional[bool]:
        y = safe_year(m.get("release_date"))
        if y is None:
            return None
        return start <= y <= end
    return p


# =========================
# Predicates - ULTRA-DISCRIMINANTS
# =========================

def pred_has_director(conn: sqlite3.Connection, director_name: str) -> Callable[[dict], Optional[bool]]:
    """Vérifie si un réalisateur spécifique a fait le film."""
    dn = director_name.lower()

    def p(m: dict) -> Optional[bool]:
        mid = movie_id(m)
        if mid is None:
            return None
        d = get_details(conn, mid)
        crew = d.get("credits", {}).get("crew", [])
        if not crew:
            return None
        directors = [c.get("name", "").lower() for c in crew if isinstance(c, dict) and c.get("job") == "Director"]
        return dn in directors
    return p

def pred_franchise_name(conn: sqlite3.Connection, franchise: str) -> Callable[[dict], Optional[bool]]:
    fn = franchise.lower()

    def p(m: dict) -> Optional[bool]:
        mid = movie_id(m)
        if mid is None:
            return None
        
        # D'abord vérifier le titre (souvent plus fiable)
        title = m.get("title", "")
        if fn in str(title).lower():
            return True
            
        # Ensuite vérifier la collection
        d = get_details(conn, mid)
        collection = d.get("belongs_to_collection")
        if collection:
            collection_name = str(collection.get("name", "")).lower()
            if fn in collection_name:
                return True
        
        # Si on n'a rien trouvé, vérifier les keywords
        keywords = d.get("keywords", {}).get("keywords", [])
        if isinstance(keywords, list):
            for kw in keywords:
                if isinstance(kw, dict):
                    kw_name = kw.get("name", "").lower()
                    if fn in kw_name:
                        return True
        
        # Si toujours rien, retourner False seulement si on a des données
        # Retourner None si on n'a aucune donnée pertinente
        if collection or keywords:
            return False
        return None
    return p

def pred_main_character_name(conn: sqlite3.Connection, char_keyword: str) -> Callable[[dict], Optional[bool]]:
    ck = char_keyword.lower()

    def p(m: dict) -> Optional[bool]:
        mid = movie_id(m)
        if mid is None:
            return None
        d = get_details(conn, mid)

        keywords = d.get("keywords", {}).get("keywords", [])
        if isinstance(keywords, list):
            names = [k.get("name", "").lower() for k in keywords if isinstance(k, dict)]
            if any(ck in kw for kw in names):
                return True

        cast = d.get("credits", {}).get("cast", [])
        if isinstance(cast, list):
            chars = [c.get("character", "").lower() for c in cast if isinstance(c, dict)]
            if any(ck in ch for ch in chars):
                return True

        return None
    return p


def pred_is_harry_potter(conn: sqlite3.Connection) -> Callable[[dict], Optional[bool]]:
    """Détection spécifique et robuste pour Harry Potter."""
    def p(m: dict) -> Optional[bool]:
        # Vérifier le titre en priorité
        title = str(m.get("title", "")).lower()
        if "harry potter" in title:
            return True
        
        mid = movie_id(m)
        if mid is None:
            return None
        
        d = get_details(conn, mid)
        
        # Vérifier la collection
        collection = d.get("belongs_to_collection")
        if collection:
            col_name = str(collection.get("name", "")).lower()
            if "harry potter" in col_name or "wizarding world" in col_name:
                return True
        
        # Vérifier les keywords
        keywords = d.get("keywords", {}).get("keywords", [])
        if isinstance(keywords, list):
            for kw in keywords:
                if isinstance(kw, dict):
                    kw_name = kw.get("name", "").lower()
                    if "harry potter" in kw_name or "hogwarts" in kw_name:
                        return True
        
        # Vérifier le cast pour les acteurs principaux
        cast = d.get("credits", {}).get("cast", [])
        if isinstance(cast, list):
            top_actors = [c.get("name", "").lower() for c in cast[:5] if isinstance(c, dict)]
            hp_actors = {"daniel radcliffe", "emma watson", "rupert grint"}
            # Si au moins 2 des 3 acteurs principaux sont présents
            matches = sum(1 for actor in hp_actors if any(actor in ta for ta in top_actors))
            if matches >= 2:
                return True
        
        return False
    return p


# =========================
# Predicates - TITRE (JOKERS)
# =========================

def pred_title_starts_with(letter: str) -> Callable[[dict], Optional[bool]]:
    l = str(letter).upper()

    def p(m: dict) -> Optional[bool]:
        title = m.get("title")
        if not title:
            return None
        nt = normalize_title(title)
        if not nt:
            return None
        return nt.startswith(l)
    return p

def pred_title_contains_word(word: str) -> Callable[[dict], Optional[bool]]:
    w = re.sub(r"\s+", " ", str(word)).strip().lower()

    def p(m: dict) -> Optional[bool]:
        title = m.get("title")
        if not title:
            return None
        return w in str(title).lower()
    return p


# =========================
# Predicates - GENRE
# =========================

def pred_has_genre(conn: sqlite3.Connection, name: str) -> Callable[[dict], Optional[bool]]:
    def p(m: dict) -> Optional[bool]:
        gids = m.get("genre_ids")
        if isinstance(gids, list) and gids:
            names = [GENRE_MAP.get(int(gid)) for gid in gids if gid is not None]
            names = [n for n in names if n]
            if names:
                return name in names

        mid = movie_id(m)
        if mid is None:
            return None
        d = get_details(conn, mid)
        genres = d.get("genres", [])
        if not isinstance(genres, list):
            return None
        names = [g.get("name") for g in genres if isinstance(g, dict)]
        if not names:
            return None
        return name in names
    return p

def pred_is_animation(conn: sqlite3.Connection) -> Callable[[dict], Optional[bool]]:
    return pred_has_genre(conn, "Animation")

def pred_not_animation(conn: sqlite3.Connection) -> Callable[[dict], Optional[bool]]:
    base = pred_is_animation(conn)
    def p(m: dict) -> Optional[bool]:
        r = base(m)
        if r is None:
            return None
        return not r
    return p


# =========================
# Predicates - DURÉE
# =========================

def pred_runtime_lt(conn: sqlite3.Connection, minutes: int) -> Callable[[dict], Optional[bool]]:
    def p(m: dict) -> Optional[bool]:
        runtime = m.get("runtime")
        if runtime is None:
            mid = movie_id(m)
            if mid is not None:
                runtime = get_details(conn, mid).get("runtime")
        if runtime is None:
            return None
        return int(runtime) < minutes
    return p

def pred_runtime_ge(conn: sqlite3.Connection, minutes: int) -> Callable[[dict], Optional[bool]]:
    def p(m: dict) -> Optional[bool]:
        runtime = m.get("runtime")
        if runtime is None:
            mid = movie_id(m)
            if mid is not None:
                runtime = get_details(conn, mid).get("runtime")
        if runtime is None:
            return None
        return int(runtime) >= minutes
    return p

def pred_is_short(conn: sqlite3.Connection) -> Callable[[dict], Optional[bool]]:
    return pred_runtime_lt(conn, 45)

def pred_is_feature(conn: sqlite3.Connection) -> Callable[[dict], Optional[bool]]:
    return pred_runtime_ge(conn, 60)


# =========================
# Predicates - ORIGINE / LANGUE
# =========================

def pred_is_american(conn: sqlite3.Connection) -> Callable[[dict], Optional[bool]]:
    def p(m: dict) -> Optional[bool]:
        mid = movie_id(m)
        if mid is None:
            return None
        countries = get_details(conn, mid).get("production_countries", [])
        if not isinstance(countries, list):
            return None
        return any(c.get("iso_3166_1") == "US" for c in countries if isinstance(c, dict))
    return p

def pred_is_french(conn: sqlite3.Connection) -> Callable[[dict], Optional[bool]]:
    def p(m: dict) -> Optional[bool]:
        mid = movie_id(m)
        if mid is None:
            return None
        countries = get_details(conn, mid).get("production_countries", [])
        if not isinstance(countries, list):
            return None
        return any(c.get("iso_3166_1") == "FR" for c in countries if isinstance(c, dict))
    return p

def pred_is_european(conn: sqlite3.Connection) -> Callable[[dict], Optional[bool]]:
    EUROPEAN_CODES = {"GB", "FR", "DE", "IT", "ES", "NL", "BE", "CH", "AT", "SE", "NO", "DK", "FI", "PL", "CZ", "IE", "PT", "GR"}
    def p(m: dict) -> Optional[bool]:
        mid = movie_id(m)
        if mid is None:
            return None
        countries = get_details(conn, mid).get("production_countries", [])
        if not isinstance(countries, list):
            return None
        return any(c.get("iso_3166_1") in EUROPEAN_CODES for c in countries if isinstance(c, dict))
    return p

def pred_is_asian(conn: sqlite3.Connection) -> Callable[[dict], Optional[bool]]:
    ASIAN_CODES = {"JP", "KR", "CN", "TW", "HK", "TH", "IN", "ID", "MY", "SG", "PH"}
    def p(m: dict) -> Optional[bool]:
        mid = movie_id(m)
        if mid is None:
            return None
        countries = get_details(conn, mid).get("production_countries", [])
        if not isinstance(countries, list):
            return None
        return any(c.get("iso_3166_1") in ASIAN_CODES for c in countries if isinstance(c, dict))
    return p

def pred_language(lang_code: str) -> Callable[[dict], Optional[bool]]:
    def p(m: dict) -> Optional[bool]:
        lang = m.get("original_language")
        if not lang:
            return None
        return str(lang) == lang_code
    return p


# =========================
# Predicates - POPULARITÉ / NOTES
# =========================

def pred_vote_average_ge(th: float) -> Callable[[dict], Optional[bool]]:
    def p(m: dict) -> Optional[bool]:
        v = m.get("vote_average")
        if v is None:
            return None
        try:
            return float(v) >= th
        except Exception:
            return None
    return p

def pred_popularity_ge(th: float) -> Callable[[dict], Optional[bool]]:
    def p(m: dict) -> Optional[bool]:
        v = m.get("popularity")
        if v is None:
            return None
        try:
            return float(v) >= th
        except Exception:
            return None
    return p

def pred_vote_count_ge(th: int) -> Callable[[dict], Optional[bool]]:
    def p(m: dict) -> Optional[bool]:
        v = m.get("vote_count")
        if v is None:
            return None
        try:
            return int(v) >= th
        except Exception:
            return None
    return p


# =========================
# Predicates - BUDGET / REVENUS
# =========================

def pred_budget_ge(conn: sqlite3.Connection, th: int) -> Callable[[dict], Optional[bool]]:
    def p(m: dict) -> Optional[bool]:
        budget = m.get("budget")
        if budget is None:
            mid = movie_id(m)
            if mid is not None:
                budget = get_details(conn, mid).get("budget")
        if budget in (None, 0):
            return None
        return int(budget) >= th
    return p

def pred_budget_lt(conn: sqlite3.Connection, th: int) -> Callable[[dict], Optional[bool]]:
    def p(m: dict) -> Optional[bool]:
        budget = m.get("budget")
        if budget is None:
            mid = movie_id(m)
            if mid is not None:
                budget = get_details(conn, mid).get("budget")
        if budget in (None, 0):
            return None
        return int(budget) < th
    return p

def pred_revenue_ge(conn: sqlite3.Connection, th: int) -> Callable[[dict], Optional[bool]]:
    def p(m: dict) -> Optional[bool]:
        revenue = m.get("revenue")
        if revenue is None:
            mid = movie_id(m)
            if mid is not None:
                revenue = get_details(conn, mid).get("revenue")
        if revenue in (None, 0):
            return None
        return int(revenue) >= th
    return p

def pred_is_indie(conn: sqlite3.Connection) -> Callable[[dict], Optional[bool]]:
    def p(m: dict) -> Optional[bool]:
        budget = m.get("budget")
        if budget is None:
            mid = movie_id(m)
            if mid is not None:
                budget = get_details(conn, mid).get("budget")
        if budget in (None, 0):
            return None
        return int(budget) < 5_000_000
    return p


# =========================
# Predicates - SAGA / COLLECTION
# =========================

def pred_is_saga(conn: sqlite3.Connection) -> Callable[[dict], Optional[bool]]:
    def p(m: dict) -> Optional[bool]:
        mid = movie_id(m)
        if mid is None:
            return None
        d = get_details(conn, mid)
        return d.get("belongs_to_collection") is not None
    return p

def pred_not_saga(conn: sqlite3.Connection) -> Callable[[dict], Optional[bool]]:
    base = pred_is_saga(conn)
    def p(m: dict) -> Optional[bool]:
        r = base(m)
        if r is None:
            return None
        return not r
    return p


# =========================
# Predicates - KEYWORDS
# =========================

def pred_keyword(conn: sqlite3.Connection, keyword: str) -> Callable[[dict], Optional[bool]]:
    k = keyword.lower().strip()
    def p(m: dict) -> Optional[bool]:
        mid = movie_id(m)
        if mid is None:
            return None
        keywords = get_details(conn, mid).get("keywords", {}).get("keywords", [])
        if not isinstance(keywords, list):
            return None
        names = [kw.get("name", "").lower().strip() for kw in keywords if isinstance(kw, dict)]
        if not names:
            return None
        # AMÉLIORATION: correspondance exacte d'abord, puis partielle
        if k in names:
            return True
        # Correspondance partielle uniquement si keyword assez long (évite faux positifs)
        if len(k) >= 4:
            return any(k in name or name in k for name in names)
        return False
    return p

def pred_is_adaptation(conn: sqlite3.Connection) -> Callable[[dict], Optional[bool]]:
    p1 = pred_keyword(conn, "based on novel")
    p2 = pred_keyword(conn, "based on comic")
    p3 = pred_keyword(conn, "based on true story")
    def p(m: dict) -> Optional[bool]:
        r1, r2, r3 = p1(m), p2(m), p3(m)
        if r1 is True or r2 is True or r3 is True:
            return True
        if r1 is None and r2 is None and r3 is None:
            return None
        return False
    return p


# =========================
# Predicates - CLASSIFICATION
# =========================

def pred_is_adult() -> Callable[[dict], Optional[bool]]:
    def p(m: dict) -> Optional[bool]:
        adult = m.get("adult")
        if adult is None:
            return None
        return adult is True
    return p

def pred_actor_in_cast(conn: sqlite3.Connection, actor_name: str) -> Callable[[dict], Optional[bool]]:
    an = actor_name.lower()

    def p(m: dict) -> Optional[bool]:
        mid = movie_id(m)
        if mid is None:
            return None
        d = get_details(conn, mid)
        cast = d.get("credits", {}).get("cast", [])
        if not cast:
            return None
        actors = [c.get("name", "").lower() for c in cast if isinstance(c, dict)]
        return an in actors
    return p


# =========================
# Default questions (statiques) - VERSION AMÉLIORÉE
# =========================

def default_questions(conn: sqlite3.Connection) -> List[Question]:
    return [

        # ─────────────────────────────────────────────
        # TYPE / FORMAT
        # ─────────────────────────────────────────────
        Question("is_animation",  "Est-ce que c'est un film d'animation ?",      pred_is_animation(conn)),
        Question("is_live_action","Est-ce que c'est un film en prises de vues réelles (live-action) ?", pred_not_animation(conn)),
        Question("is_feature",    "Est-ce que c'est un long-métrage (≥ 60 min) ?", pred_is_feature(conn)),
        Question("runtime_lt_90", "Est-ce que le film dure moins d'1h30 ?",      pred_runtime_lt(conn, 90)),
        Question("runtime_90_120","Est-ce que le film dure entre 1h30 et 2h ?",
                 lambda m: (lambda r, l: True if (r is not None and l is not None and not r and not l) else None)(
                     pred_runtime_lt(conn, 90)(m), pred_runtime_ge(conn, 120)(m))),
        Question("runtime_ge_150","Est-ce que le film dure plus de 2h30 ?",      pred_runtime_ge(conn, 150)),

        # ─────────────────────────────────────────────
        # DÉCENNIES — couverture complète des années 1920 à 2020
        # ─────────────────────────────────────────────
        Question("decade_1920s", "Le film est-il sorti dans les années 1920 ?",  pred_decade(1920)),
        Question("decade_1930s", "Le film est-il sorti dans les années 1930 ?",  pred_decade(1930)),
        Question("decade_1940s", "Le film est-il sorti dans les années 1940 ?",  pred_decade(1940)),
        Question("decade_1950s", "Le film est-il sorti dans les années 1950 ?",  pred_decade(1950)),
        Question("decade_1960s", "Le film est-il sorti dans les années 1960 ?",  pred_decade(1960)),
        Question("decade_1970s", "Le film est-il sorti dans les années 1970 (1970–1979) ?", pred_decade(1970)),
        Question("decade_1980s", "Le film est-il sorti dans les années 1980 (1980–1989) ?", pred_decade(1980)),
        Question("decade_1990s", "Le film est-il sorti dans les années 1990 (1990–1999) ?", pred_decade(1990)),
        Question("decade_2000s", "Le film est-il sorti dans les années 2000 (2000–2009) ?", pred_decade(2000)),
        Question("decade_2010s", "Le film est-il sorti dans les années 2010 (2010–2019) ?", pred_decade(2010)),
        Question("decade_2020s", "Le film est-il sorti depuis 2020 ?",           pred_decade(2020)),

        # Pivots larges pour couper vite au début
        Question("before_1990",  "Le film est-il sorti avant 1990 ?",            pred_before_year(1990)),
        Question("before_2000",  "Le film est-il sorti avant 2000 ?",
                 pred_before_year(2000),  requires=None, excludes=frozenset({"before_1990"})),
        Question("after_2010",   "Le film est-il sorti en 2010 ou après ?",      pred_after_year(2010)),
        Question("after_2020",   "Le film est-il sorti en 2020 ou après ?",
                 pred_after_year(2020),   requires=None, excludes=frozenset({"before_2000","before_1990"})),

        # ─────────────────────────────────────────────
        # GENRES
        # ─────────────────────────────────────────────
        Question("genre_action",     "Est-ce un film d'action ?",                         pred_has_genre(conn, "Action")),
        Question("genre_adventure",  "Y a-t-il des aventures, quêtes ou explorations ?",  pred_has_genre(conn, "Adventure")),
        Question("genre_comedy",     "Est-ce une comédie (film drôle) ?",                 pred_has_genre(conn, "Comedy")),
        Question("genre_drama",      "Est-ce principalement un drame (film sérieux/émouvant) ?", pred_has_genre(conn, "Drama")),
        Question("genre_fantasy",    "Y a-t-il de la magie ou du fantastique ?",          pred_has_genre(conn, "Fantasy")),
        Question("genre_horror",     "Est-ce un film d'horreur ?",                        pred_has_genre(conn, "Horror")),
        Question("genre_mystery",    "Y a-t-il une enquête ou un mystère à résoudre ?",   pred_has_genre(conn, "Mystery")),
        Question("genre_romance",    "Est-ce une histoire d'amour / romance ?",           pred_has_genre(conn, "Romance")),
        Question("genre_scifi",      "Y a-t-il de la science-fiction (espace, robots, futur) ?", pred_has_genre(conn, "Science Fiction")),
        Question("genre_thriller",   "Est-ce un thriller (suspense, tension) ?",          pred_has_genre(conn, "Thriller")),
        Question("genre_crime",      "Est-ce un film policier ou criminel ?",             pred_has_genre(conn, "Crime")),
        Question("genre_family",     "Est-ce un film tout public / familial ?",           pred_has_genre(conn, "Family")),
        Question("genre_war",        "Est-ce un film de guerre ?",                        pred_has_genre(conn, "War")),
        Question("genre_history",    "Est-ce un film historique (époque passée) ?",       pred_has_genre(conn, "History")),
        Question("genre_music",      "La musique est-elle centrale dans l'histoire ?",    pred_has_genre(conn, "Music")),
        Question("genre_documentary","Est-ce un documentaire ?",                          pred_has_genre(conn, "Documentary")),
        Question("genre_western",    "Est-ce un western ?",                               pred_has_genre(conn, "Western")),
        Question("genre_sport",      "Le sport est-il le thème principal ?",              pred_has_genre(conn, "Sport")),

        # ─────────────────────────────────────────────
        # LIEU / CADRE DE L'HISTOIRE
        # ─────────────────────────────────────────────
        Question("setting_space",     "L'histoire se déroule-t-elle dans l'espace ?",         pred_keyword(conn, "space")),
        Question("setting_sea",       "L'histoire se déroule-t-elle en mer / sur l'océan ?",  pred_keyword(conn, "ocean")),
        Question("setting_city",      "L'histoire se déroule-t-elle principalement en ville ?",pred_keyword(conn, "new york")),
        Question("setting_jungle",    "L'histoire se déroule-t-elle dans la jungle ?",        pred_keyword(conn, "jungle")),
        Question("setting_desert",    "L'histoire se déroule-t-elle dans un désert ?",        pred_keyword(conn, "desert")),
        Question("setting_school",    "L'histoire se passe-t-elle dans une école ?",          pred_keyword(conn, "school")),
        Question("setting_prison",    "L'histoire se passe-t-elle en prison ?",               pred_keyword(conn, "prison")),
        Question("setting_post_apo",  "Le monde est-il post-apocalyptique / en ruine ?",      pred_keyword(conn, "post-apocalyptic")),
        Question("setting_future",    "L'histoire se déroule-t-elle dans le futur ?",         pred_keyword(conn, "future")),
        Question("setting_medieval",  "Le cadre est-il médiéval (chevaliers, royaumes) ?",    pred_keyword(conn, "middle ages")),
        Question("setting_ww2",       "L'histoire se déroule-t-elle pendant la Seconde Guerre mondiale ?", pred_keyword(conn, "world war ii")),
        Question("setting_ww1",       "L'histoire se déroule-t-elle pendant la Première Guerre mondiale ?", pred_keyword(conn, "world war i")),

        # ─────────────────────────────────────────────
        # TON / AMBIANCE
        # ─────────────────────────────────────────────
        Question("tone_dark",        "Le film a-t-il une ambiance sombre et pesante ?",       pred_keyword(conn, "dark")),
        Question("tone_funny",       "Le film est-il principalement comique / humoristique ?", pred_keyword(conn, "comedy")),
        Question("tone_scary",       "Le film est-il effrayant / fait-il peur ?",              pred_keyword(conn, "fear")),
        Question("tone_feel_good",   "Est-ce un film feel-good / optimiste ?",                pred_keyword(conn, "feel-good")),
        Question("tone_violent",     "Y a-t-il beaucoup de violence ?",                       pred_keyword(conn, "violence")),
        Question("tone_suspense",    "Y a-t-il beaucoup de suspense / rebondissements ?",     pred_keyword(conn, "suspense")),
        Question("tone_romantic",    "Est-ce que le film est romantique / sentimental ?",     pred_keyword(conn, "romance")),
        Question("tone_sad",         "Le film est-il triste / émouvant (fait pleurer) ?",     pred_keyword(conn, "sadness")),

        # ─────────────────────────────────────────────
        # NARRATION / STRUCTURE
        # ─────────────────────────────────────────────
        Question("narr_twist",       "Y a-t-il un retournement de situation / twist final ?", pred_keyword(conn, "twist ending")),
        Question("narr_time_travel", "Y a-t-il des voyages dans le temps ?",                  pred_keyword(conn, "time travel")),
        Question("narr_flashback",   "Le film utilise-t-il des flashbacks importants ?",      pred_keyword(conn, "flashback")),
        Question("narr_heist",       "Est-ce un film de braquage / casse ?",                  pred_keyword(conn, "heist")),
        Question("narr_road_movie",  "Est-ce un road movie (voyage sur la route) ?",          pred_keyword(conn, "road trip")),
        Question("narr_survival",    "Le personnage principal lutte-t-il pour survivre ?",    pred_keyword(conn, "survival")),
        Question("narr_revenge",     "La vengeance est-elle un moteur de l'histoire ?",       pred_keyword(conn, "revenge")),
        Question("narr_love_story",  "Y a-t-il une grande histoire d'amour ?",                pred_keyword(conn, "love story")),
        Question("narr_redemption",  "Y a-t-il une quête de rédemption / rachat ?",           pred_keyword(conn, "redemption")),
        Question("narr_based_book",  "Est-ce adapté d'un livre / roman ?",                    pred_keyword(conn, "based on novel")),
        Question("narr_based_comic", "Est-ce adapté d'une bande dessinée / comic ?",          pred_keyword(conn, "based on comic")),
        Question("narr_true_story",  "Est-ce basé sur une histoire vraie ?",                  pred_keyword(conn, "based on true story")),
        Question("narr_coming_age",  "Est-ce une histoire de passage à l'âge adulte ?",       pred_keyword(conn, "coming of age")),

        # ─────────────────────────────────────────────
        # PUBLIC CIBLE
        # ─────────────────────────────────────────────
        Question("audience_children","Est-ce fait pour les enfants (film jeunesse) ?",        pred_keyword(conn, "children")),
        Question("audience_teen",    "Est-ce destiné aux adolescents ?",                      pred_keyword(conn, "teenager")),
        Question("is_adult",         "Est-ce un film strictement réservé aux adultes (contenu explicite) ?", pred_is_adult()),

        # ─────────────────────────────────────────────
        # PROTAGONISTE
        # ─────────────────────────────────────────────
        Question("hero_female",      "Le/la protagoniste principal(e) est-il/elle une femme ?", pred_keyword(conn, "female protagonist")),
        Question("hero_child",       "Le personnage principal est-il un enfant ?",              pred_keyword(conn, "child hero")),
        Question("hero_villain",     "Suit-on principalement un anti-héros ou un méchant ?",   pred_keyword(conn, "anti-hero")),
        Question("hero_group",       "Y a-t-il un groupe / équipe de héros (pas un seul) ?",   pred_keyword(conn, "ensemble cast")),
        Question("hero_animal",      "Un animal est-il le personnage principal ?",              pred_keyword(conn, "animal")),
        Question("hero_robot_ai",    "Le protagoniste est-il un robot ou une IA ?",             pred_keyword(conn, "robot")),

        # ─────────────────────────────────────────────
        # THÈMES UNIVERSELS
        # ─────────────────────────────────────────────
        Question("theme_family",     "La famille est-elle au cœur du film ?",                  pred_keyword(conn, "family")),
        Question("theme_friendship", "L'amitié est-elle un thème central ?",                   pred_keyword(conn, "friendship")),
        Question("theme_power",      "Le film parle-t-il de pouvoir / domination ?",           pred_keyword(conn, "power")),
        Question("theme_identity",   "Le film explore-t-il la question de l'identité ?",       pred_keyword(conn, "identity")),
        Question("theme_good_evil",  "C'est un affrontement entre le bien et le mal ?",        pred_keyword(conn, "good versus evil")),
        Question("theme_money",      "L'argent / la richesse sont-ils au centre de l'histoire ?", pred_keyword(conn, "money")),
        Question("theme_politics",   "Y a-t-il une dimension politique importante ?",          pred_keyword(conn, "politics")),
        Question("theme_religion",   "La religion / la foi joue-t-elle un rôle clé ?",         pred_keyword(conn, "religion")),
        Question("theme_nature",     "La nature / l'environnement est-il un enjeu majeur ?",   pred_keyword(conn, "nature")),
        Question("theme_war_cost",   "Le film montre-t-il les conséquences humaines de la guerre ?", pred_keyword(conn, "war")),
        Question("theme_sacrifice",  "Un personnage fait-il un grand sacrifice ?",             pred_keyword(conn, "sacrifice")),
        Question("theme_dream",      "Les rêves ou l'inconscient sont-ils importants ?",       pred_keyword(conn, "dream")),
        Question("theme_tech",       "La technologie / l'informatique est-elle centrale ?",    pred_keyword(conn, "technology")),
        Question("theme_superhero",  "Est-ce un film de super-héros ?",                        pred_keyword(conn, "superhero")),
        Question("theme_magic",      "Y a-t-il de la magie ou des pouvoirs surnaturels ?",    pred_keyword(conn, "magic")),
        Question("theme_chosen_one", "Le héros est-il un élu / le seul à pouvoir sauver le monde ?", pred_keyword(conn, "chosen one")),

        # ─────────────────────────────────────────────
        # ORIGINE / LANGUE
        # ─────────────────────────────────────────────
        Question("is_american",  "Est-ce une production américaine ?",    pred_is_american(conn)),
        Question("is_french",    "Est-ce une production française ?",     pred_is_french(conn)),
        Question("is_european",  "Est-ce une production européenne ?",    pred_is_european(conn)),
        Question("is_asian",     "Est-ce une production asiatique ?",     pred_is_asian(conn)),

        Question("language_en",  "Le film est-il en anglais ?",           pred_language("en")),
        Question("language_fr",  "Le film est-il en français ?",          pred_language("fr")),
        Question("language_ja",  "Le film est-il en japonais ?",          pred_language("ja")),
        Question("language_es",  "Le film est-il en espagnol ?",          pred_language("es")),
        Question("language_de",  "Le film est-il en allemand ?",          pred_language("de")),
        Question("language_it",  "Le film est-il en italien ?",           pred_language("it")),
        Question("language_ko",  "Le film est-il en coréen ?",            pred_language("ko")),
        Question("language_zh",  "Le film est-il en chinois (mandarin/cantonais) ?", pred_language("zh")),
        Question("language_pt",  "Le film est-il en portugais ?",         pred_language("pt")),
        Question("language_ru",  "Le film est-il en russe ?",             pred_language("ru")),

        # ─────────────────────────────────────────────
        # SUCCÈS / BUDGET / POPULARITÉ
        # ─────────────────────────────────────────────
        Question("very_popular",    "Est-ce un film très connu / culte du grand public ?",     pred_popularity_ge(80)),
        Question("popular",         "Est-ce un film populaire (mais pas forcément culte) ?",   pred_popularity_ge(50)),
        Question("big_budget",      "Est-ce un film à gros budget (blockbuster, > 50M$) ?",    pred_budget_ge(conn, 50_000_000)),
        Question("small_budget",    "Est-ce un film à petit budget (< 10M$) ?",
                 pred_budget_lt(conn, 10_000_000), excludes=frozenset({"big_budget"})),
        Question("box_office_hit",  "A-t-il cartonné au box-office (> 100M$ de recettes) ?",  pred_revenue_ge(conn, 100_000_000)),
        Question("is_indie",        "Est-ce un film indépendant / art et essai ?",
                 pred_is_indie(conn), excludes=frozenset({"big_budget"})),

        # ─────────────────────────────────────────────
        # FRANCHISE / UNIVERS
        # ─────────────────────────────────────────────
        Question("is_saga",      "Le film fait-il partie d'une saga / série (avec suite ou préquel) ?", pred_is_saga(conn)),
        Question("is_standalone","Est-ce un film unique (pas de suite) ?",                    pred_not_saga(conn)),

        Question("franchise_marvel",    "Est-ce un film du MCU (Marvel Studios) ?",            pred_franchise_name(conn, "Marvel")),
        Question("franchise_dc",        "Est-ce un film DC Comics ?",                          pred_franchise_name(conn, "DC")),
        Question("franchise_star_wars", "Est-ce un film Star Wars ?",                          pred_franchise_name(conn, "Star Wars")),
        Question("franchise_harry_potter","Est-ce un film Harry Potter ?",                     pred_is_harry_potter(conn)),
        Question("franchise_lotr",      "Est-ce Le Seigneur des Anneaux ou Le Hobbit ?",
                 lambda m: (lambda a, b: True if a is True or b is True else (False if a is False and b is False else None))(
                     pred_franchise_name(conn, "Lord of the Rings")(m), pred_franchise_name(conn, "Hobbit")(m))),
        Question("franchise_bond",      "Est-ce un film James Bond ?",                         pred_franchise_name(conn, "James Bond")),
        Question("franchise_jurassic",  "Est-ce un film Jurassic Park / World ?",              pred_franchise_name(conn, "Jurassic")),
        Question("franchise_fast",      "Est-ce un film Fast & Furious ?",                     pred_franchise_name(conn, "Fast")),
        Question("franchise_pirates",   "Est-ce un film Pirates des Caraïbes ?",               pred_franchise_name(conn, "Pirates of the Caribbean")),
        Question("franchise_xmen",      "Est-ce un film X-Men ?",                              pred_franchise_name(conn, "X-Men")),
        Question("franchise_mission_impossible","Est-ce un film Mission: Impossible ?",        pred_franchise_name(conn, "Mission: Impossible")),
        Question("franchise_indiana_jones","Est-ce un film Indiana Jones ?",                   pred_franchise_name(conn, "Indiana Jones")),
        Question("franchise_terminator","Est-ce un film Terminator ?",                         pred_franchise_name(conn, "Terminator")),
        Question("franchise_alien",     "Est-ce un film Alien ?",                              pred_franchise_name(conn, "Alien")),
        Question("franchise_matrix",    "Est-ce un film Matrix ?",                             pred_franchise_name(conn, "Matrix")),
        Question("franchise_rocky",     "Est-ce un film Rocky ou Creed ?",
                 lambda m: (lambda a, b: True if a is True or b is True else (False if a is False and b is False else None))(
                     pred_franchise_name(conn, "Rocky")(m), pred_franchise_name(conn, "Creed")(m))),
        Question("franchise_transformers","Est-ce un film Transformers ?",                     pred_franchise_name(conn, "Transformers")),
        Question("franchise_planet_apes","Est-ce un film La Planète des Singes ?",             pred_franchise_name(conn, "Planet of the Apes")),
        Question("franchise_lethal_weapon","Est-ce un film L'Arme Fatale ?",                   pred_franchise_name(conn, "Lethal Weapon")),
        Question("franchise_back_future","Est-ce un film Retour vers le Futur ?",              pred_franchise_name(conn, "Back to the Future")),
        Question("franchise_godfather", "Est-ce un film Le Parrain ?",                        pred_franchise_name(conn, "Godfather")),
        Question("franchise_die_hard",  "Est-ce un film Die Hard ?",                           pred_franchise_name(conn, "Die Hard")),
        Question("franchise_john_wick", "Est-ce un film John Wick ?",                          pred_franchise_name(conn, "John Wick")),
        Question("franchise_bourne",    "Est-ce un film Jason Bourne ?",                       pred_franchise_name(conn, "Bourne")),
        Question("franchise_toy_story", "Est-ce un film Toy Story ?",                          pred_franchise_name(conn, "Toy Story")),
        Question("franchise_ice_age",   "Est-ce un film L'Âge de Glace ?",                     pred_franchise_name(conn, "Ice Age")),
        Question("franchise_shrek",     "Est-ce un film Shrek ?",                              pred_franchise_name(conn, "Shrek")),
        Question("franchise_despicable","Est-ce un film Moi, Moche et Méchant / Minions ?",   pred_franchise_name(conn, "Despicable Me")),
        Question("franchise_hunger_games","Est-ce un film Hunger Games ?",                    pred_franchise_name(conn, "Hunger Games")),
        Question("franchise_twilight",  "Est-ce un film Twilight ?",                           pred_franchise_name(conn, "Twilight")),

        # ─────────────────────────────────────────────
        # PERSONNAGES ICONIQUES
        # ─────────────────────────────────────────────
        Question("char_batman",    "Le personnage principal est-il Batman ?",                  pred_main_character_name(conn, "Batman")),
        Question("char_superman",  "Le personnage principal est-il Superman ?",                pred_main_character_name(conn, "Superman")),
        Question("char_spiderman", "Le personnage principal est-il Spider-Man ?",             pred_main_character_name(conn, "Spider")),
        Question("char_ironman",   "Le personnage principal est-il Iron Man ?",               pred_main_character_name(conn, "Iron Man")),
        Question("char_joker",     "Le personnage principal est-il le Joker ?",               pred_main_character_name(conn, "Joker")),
        Question("char_terminator","Le personnage principal est-il le Terminator ?",          pred_main_character_name(conn, "Terminator")),
        Question("char_harry_p",   "Le personnage principal est-il Harry Potter ?",           pred_main_character_name(conn, "Harry Potter")),
        Question("char_frodo",     "Le personnage principal est-il Frodon ?",                 pred_main_character_name(conn, "Frodo")),
        Question("char_jack_sparrow","Le personnage principal est-il Jack Sparrow ?",         pred_main_character_name(conn, "Jack Sparrow")),
        Question("char_james_bond","Le personnage principal est-il James Bond ?",             pred_main_character_name(conn, "James Bond")),
        Question("char_indiana_j", "Le personnage principal est-il Indiana Jones ?",          pred_main_character_name(conn, "Indiana Jones")),
        Question("char_wolverine", "Le personnage principal est-il Wolverine ?",              pred_main_character_name(conn, "Wolverine")),

        # ─────────────────────────────────────────────
        # RÉALISATEURS
        # ─────────────────────────────────────────────
        Question("director_nolan",      "Réalisé par Christopher Nolan ?",    pred_has_director(conn, "Christopher Nolan")),
        Question("director_spielberg",  "Réalisé par Steven Spielberg ?",     pred_has_director(conn, "Steven Spielberg")),
        Question("director_tarantino",  "Réalisé par Quentin Tarantino ?",    pred_has_director(conn, "Quentin Tarantino")),
        Question("director_scorsese",   "Réalisé par Martin Scorsese ?",      pred_has_director(conn, "Martin Scorsese")),
        Question("director_fincher",    "Réalisé par David Fincher ?",        pred_has_director(conn, "David Fincher")),
        Question("director_cameron",    "Réalisé par James Cameron ?",        pred_has_director(conn, "James Cameron")),
        Question("director_jackson",    "Réalisé par Peter Jackson ?",        pred_has_director(conn, "Peter Jackson")),
        Question("director_ridley",     "Réalisé par Ridley Scott ?",         pred_has_director(conn, "Ridley Scott")),
        Question("director_kubrick",    "Réalisé par Stanley Kubrick ?",      pred_has_director(conn, "Stanley Kubrick")),
        Question("director_hitchcock",  "Réalisé par Alfred Hitchcock ?",     pred_has_director(conn, "Alfred Hitchcock")),
        Question("director_lynch",      "Réalisé par David Lynch ?",          pred_has_director(conn, "David Lynch")),
        Question("director_wachowski",  "Réalisé par les Wachowski ?",
                 lambda m: (lambda a, b: True if a is True or b is True else (None if a is None or b is None else False))(
                     pred_has_director(conn, "Lana Wachowski")(m), pred_has_director(conn, "Lilly Wachowski")(m))),
        Question("director_russo",      "Réalisé par les frères Russo ?",
                 lambda m: (lambda a, b: True if a is True or b is True else (None if a is None or b is None else False))(
                     pred_has_director(conn, "Anthony Russo")(m), pred_has_director(conn, "Joe Russo")(m))),
        Question("director_zemeckis",   "Réalisé par Robert Zemeckis ?",      pred_has_director(conn, "Robert Zemeckis")),
        Question("director_lucas",      "Réalisé par George Lucas ?",         pred_has_director(conn, "George Lucas")),
        Question("director_coppola",    "Réalisé par Francis Ford Coppola ?", pred_has_director(conn, "Francis Ford Coppola")),
        Question("director_burton",     "Réalisé par Tim Burton ?",           pred_has_director(conn, "Tim Burton")),
        Question("director_verhoven",   "Réalisé par Paul Verhoeven ?",       pred_has_director(conn, "Paul Verhoeven")),
        Question("director_anderson_wes","Réalisé par Wes Anderson ?",        pred_has_director(conn, "Wes Anderson")),
        Question("director_villeneuve", "Réalisé par Denis Villeneuve ?",     pred_has_director(conn, "Denis Villeneuve")),
        Question("director_favreau",    "Réalisé par Jon Favreau ?",          pred_has_director(conn, "Jon Favreau")),
        Question("director_snyder",     "Réalisé par Zack Snyder ?",          pred_has_director(conn, "Zack Snyder")),
        Question("director_bay",        "Réalisé par Michael Bay ?",          pred_has_director(conn, "Michael Bay")),
        Question("director_lee_ang",    "Réalisé par Ang Lee ?",              pred_has_director(conn, "Ang Lee")),
        Question("director_miyazaki",   "Réalisé par Hayao Miyazaki ?",       pred_has_director(conn, "Hayao Miyazaki")),
        Question("director_luc_besson", "Réalisé par Luc Besson ?",           pred_has_director(conn, "Luc Besson")),
        Question("director_gondry",     "Réalisé par Michel Gondry ?",        pred_has_director(conn, "Michel Gondry")),
        Question("director_dolan",      "Réalisé par Xavier Dolan ?",         pred_has_director(conn, "Xavier Dolan")),
        Question("director_cuaron",     "Réalisé par Alfonso Cuarón ?",       pred_has_director(conn, "Alfonso Cuarón")),
        Question("director_bong",       "Réalisé par Bong Joon-ho ?",         pred_has_director(conn, "Bong Joon-ho")),
        Question("director_park_chan",  "Réalisé par Park Chan-wook ?",       pred_has_director(conn, "Park Chan-wook")),

        # ─────────────────────────────────────────────
        # JOKERS TITRE (dernier recours)
        # ─────────────────────────────────────────────
        Question("joker_title_a_d", "Le titre commence-t-il par A, B, C ou D ?",
                 lambda m: (lambda a,b,c,d: True if any(x is True for x in [a,b,c,d]) else (None if all(x is None for x in [a,b,c,d]) else False))(
                     pred_title_starts_with("A")(m), pred_title_starts_with("B")(m),
                     pred_title_starts_with("C")(m), pred_title_starts_with("D")(m))),
        Question("joker_title_e_h", "Le titre commence-t-il par E, F, G ou H ?",
                 lambda m: (lambda a,b,c,d: True if any(x is True for x in [a,b,c,d]) else (None if all(x is None for x in [a,b,c,d]) else False))(
                     pred_title_starts_with("E")(m), pred_title_starts_with("F")(m),
                     pred_title_starts_with("G")(m), pred_title_starts_with("H")(m))),
        Question("joker_title_i_l", "Le titre commence-t-il par I, J, K ou L ?",
                 lambda m: (lambda a,b,c,d: True if any(x is True for x in [a,b,c,d]) else (None if all(x is None for x in [a,b,c,d]) else False))(
                     pred_title_starts_with("I")(m), pred_title_starts_with("J")(m),
                     pred_title_starts_with("K")(m), pred_title_starts_with("L")(m))),
        Question("joker_title_m_p", "Le titre commence-t-il par M, N, O ou P ?",
                 lambda m: (lambda a,b,c,d: True if any(x is True for x in [a,b,c,d]) else (None if all(x is None for x in [a,b,c,d]) else False))(
                     pred_title_starts_with("M")(m), pred_title_starts_with("N")(m),
                     pred_title_starts_with("O")(m), pred_title_starts_with("P")(m))),
        Question("joker_title_q_t", "Le titre commence-t-il par Q, R, S ou T ?",
                 lambda m: (lambda a,b,c,d: True if any(x is True for x in [a,b,c,d]) else (None if all(x is None for x in [a,b,c,d]) else False))(
                     pred_title_starts_with("Q")(m), pred_title_starts_with("R")(m),
                     pred_title_starts_with("S")(m), pred_title_starts_with("T")(m))),
        Question("joker_title_u_z", "Le titre commence-t-il par U, V, W, X, Y ou Z ?",
                 lambda m: (lambda a,b,c,d,e,f: True if any(x is True for x in [a,b,c,d,e,f]) else (None if all(x is None for x in [a,b,c,d,e,f]) else False))(
                     pred_title_starts_with("U")(m), pred_title_starts_with("V")(m), pred_title_starts_with("W")(m),
                     pred_title_starts_with("X")(m), pred_title_starts_with("Y")(m), pred_title_starts_with("Z")(m))),
    ]


# =========================
# Build dynamic questions
# =========================

def build_top_validation_questions(
    conn: sqlite3.Connection,
    candidates: List[dict],
    asked: Set[str],
) -> List[Question]:
    """
    Génère des questions SPÉCIFIQUES au film #1 pour le valider/éliminer rapidement.
    
    Stratégie: Au lieu d'éliminer 149 autres films, on pose des questions sur le #1:
    - Si réponse OUI → Le #1 se confirme
    - Si réponse NON → Le #1 est ÉLIMINÉ immédiatement !
    
    AMÉLIORÉ: Active dès 10 candidats (au lieu de 50) pour converger plus vite.
    """
    # AMÉLIORATION: Plage élargie - actif dès 10 candidats jusqu'à 500
    if len(candidates) < 10 or len(candidates) > 500:
        return []
    
    top = candidates[0]
    mid = movie_id(top)
    if mid is None:
        return []
    
    questions: List[Question] = []
    details = get_details(conn, mid)
    
    # 1. RÉALISATEUR du film #1 (en premier - très discriminant)
    crew = details.get("credits", {}).get("crew", [])
    if isinstance(crew, list):
        for person in crew:
            if isinstance(person, dict) and person.get("job") == "Director":
                name = person.get("name", "").strip()
                if name:
                    key = f"validate_director_{name.replace(' ', '_').lower()}"
                    if key not in asked:
                        text = f"Est-ce réalisé par {name} ?"
                        questions.append(Question(key, text, pred_has_director(conn, name)))
                break
    
    # 2. ACTEURS PRINCIPAUX du film #1 (top 3 seulement = plus précis)
    cast = details.get("credits", {}).get("cast", [])
    if isinstance(cast, list):
        for actor in cast[:3]:  # Top 3 acteurs seulement
            if isinstance(actor, dict):
                name = actor.get("name", "").strip()
                if name:
                    if name.lower() not in ACTOR_NATIONALITY:
                        continue
                    key = f"validate_actor_{name.replace(' ', '_').lower()}"
                    if key not in asked:
                        text = f"Est-ce que {name} joue dedans ?"
                        questions.append(Question(key, text, pred_actor_in_cast(conn, name)))
    
    # 3. ANNÉE EXACTE du film #1
    year = safe_year(top.get("release_date"))
    if year:
        key = f"validate_year_{year}"
        if key not in asked:
            text = f"Est-ce sorti en {year} ?"
            questions.append(Question(key, text, pred_exact_year(year)))
    
    # 4. KEYWORDS DISTINCTIFS du film #1 (top 5 les plus rares dans le pool)
    keywords = details.get("keywords", {}).get("keywords", [])
    if isinstance(keywords, list) and len(candidates) <= 100:
        # Calculer la rareté de chaque keyword dans le pool
        from collections import Counter
        pool_kw_counter: Counter = Counter()
        for cand in candidates[:50]:  # Limiter pour perf
            cand_mid = movie_id(cand)
            if cand_mid and cand_mid != mid:
                cand_kws = get_details(conn, cand_mid).get("keywords", {}).get("keywords", [])
                if isinstance(cand_kws, list):
                    for kw in cand_kws:
                        if isinstance(kw, dict):
                            pool_kw_counter[kw.get("name", "").lower().strip()] += 1
        
        # Choisir les keywords du top film les plus RARES dans le pool (= plus discriminants)
        rare_keywords = []
        for kw in keywords[:15]:
            if isinstance(kw, dict):
                name = kw.get("name", "").lower().strip()
                if name and len(name) >= 4:
                    freq = pool_kw_counter.get(name, 0)
                    rare_keywords.append((name, freq))
        
        # Trier par fréquence croissante (les plus rares en premier)
        rare_keywords.sort(key=lambda x: x[1])
        
        for kw_name, freq in rare_keywords[:5]:
            key = f"validate_keyword_{kw_name.replace(' ', '_')}"
            if key not in asked:
                text = f"Le film est-il lié à '{kw_name}' ?"
                questions.append(Question(key, text, pred_keyword(conn, kw_name)))
    
    # 5. COLLECTION / FRANCHISE du film #1
    collection = details.get("belongs_to_collection")
    if collection:
        col_name = str(collection.get("name", "")).strip()
        if col_name:
            # Extraire le nom court de la franchise
            short_name = col_name.replace(" Collection", "").replace(" Franchise", "").strip()
            if short_name:
                key = f"validate_franchise_{short_name.replace(' ', '_').lower()}"
                if key not in asked:
                    text = f"Le film fait-il partie de la franchise '{short_name}' ?"
                    questions.append(Question(key, text, pred_franchise_name(conn, short_name.lower())))
    
    return questions[:20]  # Max 20 questions de validation


def build_dynamic_keyword_questions(
    conn: sqlite3.Connection,
    candidates: List[dict],
    asked: Set[str],
    top_k: int = 80,
) -> List[Question]:
    """
    Questions dynamiques basées sur les keywords les plus fréquents dans le pool.
    AMÉLIORÉ: Filtre les keywords trop génériques, génère plus sur petit pool.
    """
    from collections import Counter
    
    if len(candidates) > 300:
        return []

    # Keywords trop génériques à ignorer (ne discriminent pas bien)
    GENERIC_KEYWORDS = {
        "based on novel", "based on book", "based on short story",
        "independent film", "cult film", "blockbuster",
        "sequel", "prequel", "reboot",
        "female protagonist", "male protagonist",
        "based on true story",  # gardé dans les questions statiques
    }

    keyword_counter: Counter = Counter()
    for m in candidates:
        mid = movie_id(m)
        if mid is None:
            continue
        kws = get_details(conn, mid).get("keywords", {}).get("keywords", [])
        if isinstance(kws, list):
            for kw in kws:
                if isinstance(kw, dict):
                    name = kw.get("name", "").strip().lower()
                    if name and name not in GENERIC_KEYWORDS and len(name) >= 3:
                        keyword_counter[name] += 1

    questions: List[Question] = []
    n = len(candidates)
    
    # AMÉLIORÉ: top_k adaptatif selon la taille du pool
    actual_top_k = top_k
    if n <= 5:
        actual_top_k = 300   # Quasi illimité sur très petit pool
    elif n <= 10:
        actual_top_k = 200
    elif n <= 30:
        actual_top_k = 150
    elif n <= 50:
        actual_top_k = 120
    elif n <= 100:
        actual_top_k = 100
    
    for kw, count in keyword_counter.most_common(actual_top_k):
        if count < 1:
            continue
        
        # AMÉLIORATION: Sur un grand pool, n'inclure que les keywords qui discriminent bien
        # (ni trop rares = 1 film, ni trop communs = >80% des films)
        if n >= 50:
            ratio = count / n
            if count < 2:  # Trop rare sur grand pool
                continue
            if ratio > 0.85:  # Trop commun = ne discrimine pas
                continue
        
        key = f"dyn_keyword_{kw.replace(' ', '_')}"
        if key in asked:
            continue
        text = f"Le film est-il lié au thème '{kw}' ?"
        questions.append(Question(key, text, pred_keyword(conn, kw)))

    return questions


def detect_dominant_language(candidates: List[dict]) -> Optional[str]:
    """
    Détecte la langue originale dominante parmi les candidats.
    Retourne le code langue (en, fr, ja, es, etc.) ou None si mixte.
    """
    from collections import Counter
    
    if not candidates:
        return None
    
    lang_counter: Counter = Counter()
    for m in candidates:
        lang = m.get("original_language", "")
        if lang:
            lang_counter[lang] += 1
    
    if not lang_counter:
        return None
    
    # Si une langue représente 70%+ des candidats, c'est la langue dominante
    total = len(candidates)
    most_common_lang, count = lang_counter.most_common(1)[0]
    
    if count / total >= 0.70:
        return most_common_lang
    
    return None  # Trop mixte


# =========================
# ACTEURS CÉLÈBRES (par décennie + par pays) — utilisé pour questions dynamiques
# =========================

ACTORS_BY_DECADE_EN = {
    1960: [
        "Sean Connery", "Paul Newman", "Steve McQueen", "Clint Eastwood", "Marlon Brando",
        "Sidney Poitier", "Audrey Hepburn", "Elizabeth Taylor", "Julie Andrews", "Cary Grant",
        "Peter O'Toole", "Henry Fonda"
    ],
    1970: [
        "Al Pacino", "Robert De Niro", "Jack Nicholson", "Dustin Hoffman", "Gene Hackman",
        "Donald Sutherland", "Harrison Ford", "Sylvester Stallone", "Diane Keaton", "Jane Fonda",
        "Faye Dunaway", "Goldie Hawn", "John Cazale", "Burt Reynolds", "Christopher Walken"
    ],
    1980: [
        "Tom Cruise", "Arnold Schwarzenegger", "Sylvester Stallone", "Harrison Ford", "Eddie Murphy",
        "Michael J. Fox", "Bruce Willis", "Mel Gibson", "Meryl Streep", "Sigourney Weaver",
        "Michelle Pfeiffer", "Whoopi Goldberg", "Bill Murray", "Kevin Costner", "Sean Penn"
    ],
    1990: [
        "Leonardo DiCaprio", "Brad Pitt", "Tom Hanks", "Johnny Depp", "Will Smith",
        "Morgan Freeman", "Keanu Reeves", "Denzel Washington", "Julia Roberts", "Sandra Bullock",
        "Nicole Kidman", "Jodie Foster", "Matt Damon", "Jim Carrey", "Samuel L. Jackson"
    ],
    2000: [
        "Tom Cruise", "Leonardo DiCaprio", "Brad Pitt", "Johnny Depp", "Christian Bale",
        "George Clooney", "Russell Crowe", "Matt Damon", "Angelina Jolie", "Natalie Portman",
        "Cate Blanchett", "Keira Knightley", "Hugh Jackman", "Daniel Craig", "Sean Penn"
    ],
    2010: [
        "Robert Downey Jr.", "Leonardo DiCaprio", "Chris Hemsworth", "Chris Evans", "Ryan Gosling",
        "Brad Pitt", "Dwayne Johnson", "Joaquin Phoenix", "Scarlett Johansson", "Jennifer Lawrence",
        "Emma Stone", "Margot Robbie", "Amy Adams", "Christian Bale", "Benedict Cumberbatch"
    ],
    2020: [
        "Timothée Chalamet", "Zendaya", "Florence Pugh", "Anya Taylor-Joy", "Austin Butler",
        "Cillian Murphy", "Margot Robbie", "Robert Pattinson", "Pedro Pascal", "Ryan Gosling",
        "Jenna Ortega", "Paul Mescal", "Barry Keoghan", "Sydney Sweeney", "Jason Momoa"
    ],
}

ACTORS_FR = [
    "Jean Gabin", "Alain Delon", "Jean-Paul Belmondo", "Gérard Depardieu", "Louis de Funès",
    "Jean Reno", "Omar Sy", "Vincent Cassel", "Marion Cotillard", "Catherine Deneuve",
    "Isabelle Adjani", "Brigitte Bardot", "Juliette Binoche", "Michel Piccoli", "Patrick Dewaere",
    "Daniel Auteuil", "Yves Montand", "Jean Dujardin", "François Cluzet", "Bourvil",
    "Sophie Marceau", "Michel Serrault", "Jean-Pierre Léaud", "Romain Duris", "Gaspard Ulliel"
]

ACTORS_ES = [
    "Antonio Banderas", "Penélope Cruz", "Javier Bardem", "Fernando Rey", "Carmen Maura",
    "Victoria Abril", "Eduard Fernández", "Jordi Mollà", "Paz Vega", "Álex González",
    "Luis Tosar", "Maribel Verdú", "Sergi López", "Antonio de la Torre",
    "Raúl Arévalo", "Inma Cuesta", "Karra Elejalde", "Emma Suárez", "Najwa Nimri",
    "Mario Casas", "Blanca Portillo", "José Sacristán", "Imanol Arias", "Ana Torrent"
]

ACTORS_DE = [
    "Bruno Ganz", "Christoph Waltz", "Diane Kruger", "Til Schweiger",
    "Moritz Bleibtreu", "Nina Hoss", "Daniel Brühl", "Jürgen Prochnow", "August Diehl",
    "Hannah Herzsprung", "Sebastian Koch", "Heiner Lauterbach", "Lars Eidinger", "Maria Schrader",
    "Ulrich Mühe", "Sibel Kekilli", "Volker Bruch", "Barbara Sukowa",
    "Klaus Kinski", "Romy Schneider", "Brigitte Helm", "Tom Schilling", "Matthias Schweighöfer"
]

ACTORS_JA = [
    "Toshiro Mifune", "Takashi Shimura", "Ken Watanabe", "Issey Ogata", "Hiroyuki Sanada",
    "Rinko Kikuchi", "Tadanobu Asano", "Koji Yakusho", "Takeshi Kitano", "Yû Aoi",
    "Shin'ichi Tsutsumi", "Satomi Ishihara", "Masami Nagasawa", "Kankurō Nakamura",
    "Kazuki Kitamura", "Ayase Haruka", "Sho Sakurai", "Masahiro Motoki", "Yôsuke Eguchi",
    "Ryō Yoshizawa", "Kento Yamazaki", "Suzu Hirose", "Fumiyo Kohinata", "Shota Sometani"
]

ACTORS_IT = [
    "Marcello Mastroianni", "Sophia Loren", "Vittorio Gassman", "Alberto Sordi", "Gina Lollobrigida",
    "Monica Bellucci", "Claudia Cardinale", "Totò", "Roberto Benigni", "Pierfrancesco Favino",
    "Isabella Rossellini", "Raoul Bova", "Sergio Castellitto", "Asia Argento", "Stefania Sandrelli",
    "Valeria Golino", "Franco Nero", "Bud Spencer", "Terence Hill", "Giancarlo Giannini",
    "Elio Germano", "Toni Servillo", "Silvana Mangano", "Luigi Lo Cascio", "Riccardo Scamarcio"
]


def get_decade_from_year(year: Optional[int]) -> Optional[int]:
    if year is None:
        return None
    return (year // 10) * 10


def detect_dominant_decade(candidates: List[dict]) -> Optional[int]:
    """Décennie dominante si elle représente >= 70% des candidats."""
    from collections import Counter

    if not candidates:
        return None

    decade_counter: Counter = Counter()
    for m in candidates:
        year = safe_year(m.get("release_date"))
        decade = get_decade_from_year(year)
        if decade is not None:
            decade_counter[decade] += 1

    if not decade_counter:
        return None

    total = len(candidates)
    most_common_decade, count = decade_counter.most_common(1)[0]
    if count / total >= 0.70:
        return most_common_decade
    return None


def get_relevant_actors(dominant_language: Optional[str], dominant_decade: Optional[int]) -> List[str]:
    """Réduit le bruit: pour 'en' filtre par décennie, pour autres langues liste pays."""
    if dominant_language is None:
        all_actors = []
        for actors in ACTORS_BY_DECADE_EN.values():
            all_actors.extend(actors)
        all_actors.extend(ACTORS_FR)
        all_actors.extend(ACTORS_ES)
        all_actors.extend(ACTORS_DE)
        all_actors.extend(ACTORS_JA)
        all_actors.extend(ACTORS_IT)
        return list(set(all_actors))

    if dominant_language == "en":
        if dominant_decade is None or dominant_decade < 1960:
            all_en = []
            for actors in ACTORS_BY_DECADE_EN.values():
                all_en.extend(actors)
            return list(set(all_en))
        if dominant_decade in ACTORS_BY_DECADE_EN:
            return ACTORS_BY_DECADE_EN[dominant_decade]
        available = sorted(ACTORS_BY_DECADE_EN.keys())
        closest = min(available, key=lambda x: abs(x - dominant_decade))
        return ACTORS_BY_DECADE_EN[closest]

    if dominant_language == "fr":
        return ACTORS_FR
    if dominant_language == "es":
        return ACTORS_ES
    if dominant_language == "de":
        return ACTORS_DE
    if dominant_language == "ja":
        return ACTORS_JA
    if dominant_language == "it":
        return ACTORS_IT

    return []


# Mapping acteurs célèbres → nationalité (code langue)
# Cette liste sera enrichie au fur et à mesure
ACTOR_NATIONALITY = {
    # Acteurs américains/anglais (en)
    "leonardo dicaprio": "en",
    "brad pitt": "en",
    "tom hanks": "en",
    "robert downey jr.": "en",
    "scarlett johansson": "en",
    "jennifer lawrence": "en",
    "tom cruise": "en",
    "will smith": "en",
    "denzel washington": "en",
    "morgan freeman": "en",
    "samuel l. jackson": "en",
    "christian bale": "en",
    "matt damon": "en",
    "mark wahlberg": "en",
    "johnny depp": "en",
    "angelina jolie": "en",
    "sandra bullock": "en",
    "julia roberts": "en",
    "meryl streep": "en",
    "kate winslet": "en",
    "cate blanchett": "en",
    "hugh jackman": "en",
    "chris hemsworth": "en",
    "chris evans": "en",
    "chris pratt": "en",
    "robert pattinson": "en",
    "emma watson": "en",
    "daniel radcliffe": "en",
    "rupert grint": "en",
    "harrison ford": "en",
    "mark hamill": "en",
    "carrie fisher": "en",
    "natalie portman": "en",
    "ewan mcgregor": "en",
    "ian mckellen": "en",
    "patrick stewart": "en",
    "ben affleck": "en",
    "ryan gosling": "en",
    "ryan reynolds": "en",
    "keanu reeves": "en",
    "charlize theron": "en",
    "michael fassbender": "en",
    "james mcavoy": "en",
    "benedict cumberbatch": "en",
    "tom hiddleston": "en",
    "eddie redmayne": "en",
    
    # Acteurs français (fr)
    "marion cotillard": "fr",
    "omar sy": "fr",
    "jean reno": "fr",
    "gérard depardieu": "fr",
    "vincent cassel": "fr",
    "jean dujardin": "fr",
    "audrey tautou": "fr",
    "léa seydoux": "fr",
    "sophie marceau": "fr",
    "isabelle huppert": "fr",
    "juliette binoche": "fr",
    "lambert wilson": "fr",
    "mathieu amalric": "fr",
    "romain duris": "fr",
    "gad elmaleh": "fr",
    "dany boon": "fr",
    "françois cluzet": "fr",
    "benoît magimel": "fr",
    "audrey dana": "fr",
    
    # Acteurs espagnols (es)
    "penélope cruz": "es",
    "javier bardem": "es",
    "antonio banderas": "es",
    "ricardo darín": "es",
    "adrián suar": "es",
    "guillermo campra": "es",
    "dani martín": "es",
    
    # Acteurs japonais (ja)
    "ken watanabe": "ja",
    "rinko kikuchi": "ja",
    "toshiro mifune": "ja",
    "mari natsuki": "ja",
    
    # Acteurs allemands (de)
    "diane kruger": "de",
    "til schweiger": "de",
    "daniel brühl": "de",
    "christoph waltz": "de",
    
    # Acteurs italiens (it)
    "sophia loren": "it",
    "marcello mastroianni": "it",
    "roberto benigni": "it",
    "monica bellucci": "it",
    "damiano russo": "it",
}


def should_include_actor(actor_name: str, dominant_language: Optional[str], relevant_actor_set: Optional[Set[str]] = None) -> bool:
    """
    Détermine si on doit poser une question sur cet acteur.

    Règles:
    - Si relevant_actor_set est fourni (mode "réduction de bruit"), on garde uniquement les acteurs dans ce set.
    - Sinon, on filtre par langue dominante via ACTOR_NATIONALITY (si connu).
    - Si la langue est mixte ou inconnue, on accepte.
    """
    if relevant_actor_set is not None:
        return actor_name in relevant_actor_set

    if dominant_language is None:
        return True

    actor_lower = actor_name.lower().strip()
    actor_lang = ACTOR_NATIONALITY.get(actor_lower)

    if actor_lang is None:
        return True  # Acteur inconnu, on garde par défaut

    return actor_lang == dominant_language


def build_dynamic_questions(
    conn: sqlite3.Connection,
    candidates: List[dict],
    asked: Set[str],
    top_k: int = 60,
) -> List[Question]:
    """
    Questions dynamiques basées sur acteurs/réalisateurs fréquents dans le pool.
    AMÉLIORÉ: Filtre intelligent + plus de candidats acceptés.
    """
    from collections import Counter
    
    if len(candidates) > 300:
        return []

    # Détecter la langue dominante
    dominant_language = detect_dominant_language(candidates)
    dominant_decade = detect_dominant_decade(candidates)
    relevant_actor_set = set(get_relevant_actors(dominant_language, dominant_decade))
    
    actor_counter: Counter = Counter()
    director_counter: Counter = Counter()
    n = len(candidates)

    for m in candidates:
        mid = movie_id(m)
        if mid is None:
            continue
        d = get_details(conn, mid)
        cast = d.get("credits", {}).get("cast", [])
        crew = d.get("credits", {}).get("crew", [])

        if isinstance(cast, list):
            # AMÉLIORÉ: top 10 acteurs sur petit pool, top 7 sur grand
            max_actors = 10 if n <= 30 else 7
            for c in cast[:max_actors]:
                if isinstance(c, dict):
                    name = c.get("name", "").strip()
                    if name:
                        actor_counter[name] += 1

        if isinstance(crew, list):
            for c in crew:
                if isinstance(c, dict) and c.get("job") == "Director":
                    name = c.get("name", "").strip()
                    if name:
                        director_counter[name] += 1

    questions: List[Question] = []
    
    # top_k adaptatif selon la taille du pool
    actual_top_k = top_k
    if n <= 5:
        actual_top_k = 300
    elif n <= 10:
        actual_top_k = 150
    elif n <= 30:
        actual_top_k = 120
    elif n <= 50:
        actual_top_k = 100
    elif n <= 100:
        actual_top_k = 80

    # Filtrer les acteurs selon la langue dominante
    for actor, count in actor_counter.most_common(actual_top_k):
        if count < 1:
            continue
        
        # Sur grand pool, exiger au moins 2 films (pour éviter les questions inutiles)
        if n >= 50 and count < 2:
            continue
        
        if actor.lower() not in ACTOR_NATIONALITY:
            continue
        
        # Filtre de langue
        if not should_include_actor(actor, dominant_language, relevant_actor_set):
            continue
        
        key = f"dyn_actor_{actor.replace(' ', '_').lower()}"
        if key in asked:
            continue
        text = f"Est-ce que {actor} joue dedans ?"
        questions.append(Question(key, text, pred_actor_in_cast(conn, actor)))

    # Réalisateurs: toujours inclure (très discriminants)
    for director, count in director_counter.most_common(actual_top_k):
        if count < 1:
            continue
        
        key = f"dyn_director_{director.replace(' ', '_').lower()}"
        if key in asked:
            continue
        text = f"Est-ce réalisé par {director} ?"
        questions.append(Question(key, text, pred_has_director(conn, director)))

    return questions


def build_dynamic_year_questions(
    candidates: List[dict],
    asked: Set[str],
) -> List[Question]:
    """
    Génère des questions de date par DICHOTOMIE au lieu d'années individuelles.
    
    Principe : trouver la coupure temporelle qui divise le pool en deux moitiés égales,
    puis proposer UN SEUL pivot (ex: "avant ou après 2005 ?").
    Pas de spam "sorti en 2003 ? 2004 ? 2005 ?".
    """
    if len(candidates) > 200 or len(candidates) < 2:
        return []

    # Collecter toutes les années disponibles, triées
    years = sorted(
        y for m in candidates
        if (y := safe_year(m.get("release_date"))) is not None
    )

    if len(years) < 2:
        return []

    min_year = years[0]
    max_year = years[-1]

    # Si toutes les années sont identiques, rien à faire
    if min_year == max_year:
        return []

    questions: List[Question] = []
    n = len(years)

    # --- PIVOT MÉDIAN : la coupure qui équilibre le mieux le pool ---
    median_year = years[n // 2]

    # On évite les clés déjà posées et les pivots redondants
    # (si min == median ou median == max il n'y a pas de vraie coupure)
    if min_year < median_year:
        key = f"before_year_{median_year}"
        if key not in asked:
            text = f"Le film est-il sorti avant {median_year} ?"
            questions.append(Question(key, text, pred_before_year(median_year)))

    # --- QUELQUES PIVOTS SUPPLÉMENTAIRES pour affiner (décennies entières) ---
    # On ajoute les décennies présentes dans le pool mais pas encore demandées
    decades_in_pool = sorted({(y // 10) * 10 for y in years})
    for decade in decades_in_pool:
        # Question "sorti dans les années XXXX ?" (ex: "dans les années 1990 ?")
        key = f"decade_{decade}s"
        if key not in asked:
            yes_count = sum(1 for y in years if decade <= y < decade + 10)
            # Seulement si cette décennie est minoritaire (discriminante)
            if 0 < yes_count < n:
                text = f"Le film est-il sorti dans les années {decade} ({decade}–{decade+9}) ?"
                questions.append(Question(key, text, pred_decade(decade)))

    # --- PIVOT PRÉCIS si pool très petit (≤ 10 films) ---
    # On propose l'année exacte UNIQUEMENT pour la médiane, pas pour chaque film
    if len(candidates) <= 10 and min_year < max_year:
        # Chercher l'année qui divise le mieux (la plus proche de la moitié)
        best_pivot = years[n // 2]
        key_exact = f"exact_year_pivot_{best_pivot}"
        if key_exact not in asked:
            before = sum(1 for y in years if y < best_pivot)
            after  = sum(1 for y in years if y >= best_pivot)
            if before > 0 and after > 0:
                text = f"Le film est-il sorti en {best_pivot} ou après ?"
                questions.append(Question(key_exact, text, pred_after_year(best_pivot)))

    return questions


def build_binary_disambiguation_questions(
    conn: sqlite3.Connection,
    candidates: List[dict],
    asked: Set[str],
) -> List[Question]:
    """
    NOUVEAU: Génère des questions ultra-précises pour désambiguïser un très petit pool.
    Activé quand il reste 2 à 15 films: crée des questions qui séparent exactement.
    
    Stratégie: pour chaque paire de films restants, trouver ce qui les différencie.
    """
    n = len(candidates)
    if n < 2 or n > 15:
        return []
    
    questions: List[Question] = []
    added_keys: set = set()
    
    # Pour chaque film dans le pool, générer des questions très spécifiques
    for m in candidates:
        mid = movie_id(m)
        if mid is None:
            continue
        
        details = get_details(conn, mid)
        title = str(m.get("title", "")).strip()
        year = safe_year(m.get("release_date"))
        
        # 1. Première lettre du titre (si pas déjà demandé et utile)
        if title:
            letter = title[0].upper() if not title[0].isdigit() else title[0]
            key = f"bin_title_letter_{letter}"
            if key not in asked and key not in added_keys:
                # Vérifier que cette lettre discrimine (pas tous les films ont la même)
                yes_count = sum(1 for cand in candidates 
                               if str(cand.get("title", "")).startswith(letter))
                if 0 < yes_count < n:
                    text = f"Le titre du film commence-t-il par la lettre '{letter}' ?"
                    questions.append(Question(key, text, pred_title_starts_with(letter)))
                    added_keys.add(key)
        
        # 2. Nombre de mots dans le titre
        if title:
            word_count = len(title.split())
            if word_count >= 1:
                key = f"bin_title_words_{word_count}"
                if key not in asked and key not in added_keys:
                    yes_count = sum(1 for cand in candidates 
                                   if len(str(cand.get("title", "")).split()) == word_count)
                    if 0 < yes_count < n:
                        text = f"Le titre du film contient-il exactement {word_count} mot(s) ?"
                        questions.append(Question(key, text, 
                            lambda m, wc=word_count: len(str(m.get("title", "")).split()) == wc))
                        added_keys.add(key)
        
        # 3. Pivot temporel (médiane des années du pool) — une seule question, pas par film
        # (géré globalement par build_dynamic_year_questions, on évite le doublon ici)
        
        # 4. Acteur principal unique
        cast = details.get("credits", {}).get("cast", [])
        if isinstance(cast, list):
            for actor_data in cast[:2]:  # Top 2 acteurs
                if isinstance(actor_data, dict):
                    actor_name = actor_data.get("name", "").strip()
                    if not actor_name:
                        continue
                    if actor_name.lower() not in ACTOR_NATIONALITY:
                        continue
                    key = f"bin_actor_{actor_name.replace(' ', '_').lower()}"
                    if key not in asked and key not in added_keys:
                        # Vérifier que cet acteur est dans au moins 1 film mais pas tous
                        actor_lower = actor_name.lower()
                        yes_count = 0
                        for cand in candidates:
                            cand_mid = movie_id(cand)
                            if cand_mid:
                                cand_cast = get_details(conn, cand_mid).get("credits", {}).get("cast", [])
                                if isinstance(cand_cast, list):
                                    if any(c.get("name", "").lower() == actor_lower for c in cand_cast if isinstance(c, dict)):
                                        yes_count += 1
                        if 0 < yes_count < n:
                            text = f"Est-ce que {actor_name} joue dans ce film ?"
                            questions.append(Question(key, text, pred_actor_in_cast(conn, actor_name)))
                            added_keys.add(key)
        
        # 5. Réalisateur
        crew = details.get("credits", {}).get("crew", [])
        if isinstance(crew, list):
            for person in crew:
                if isinstance(person, dict) and person.get("job") == "Director":
                    dir_name = person.get("name", "").strip()
                    if dir_name:
                        key = f"bin_director_{dir_name.replace(' ', '_').lower()}"
                        if key not in asked and key not in added_keys:
                            dir_lower = dir_name.lower()
                            yes_count = 0
                            for cand in candidates:
                                cand_mid = movie_id(cand)
                                if cand_mid:
                                    cand_crew = get_details(conn, cand_mid).get("credits", {}).get("crew", [])
                                    if isinstance(cand_crew, list):
                                        if any(c.get("name", "").lower() == dir_lower and c.get("job") == "Director"
                                               for c in cand_crew if isinstance(c, dict)):
                                            yes_count += 1
                            if 0 < yes_count < n:
                                text = f"Est-ce réalisé par {dir_name} ?"
                                questions.append(Question(key, text, pred_has_director(conn, dir_name)))
                                added_keys.add(key)
                    break
    
    return questions

Answer = str

@dataclass
class EngineState:
    candidates: List[dict]
    asked: Set[str]
    scores: Dict[int, float]
    strikes: Dict[int, int]
    question_count: int
    guess_cooldown: int
    top_streak_mid: Optional[int]
    top_streak_len: int
    consecutive_guesses: int  # NOUVEAU: compteur de guesses consécutifs
    recent_question_types: List[str]  # NOUVEAU: historique des types récents (max 5)


def init_state(movies: List[dict]) -> EngineState:
    scores = {}
    for m in movies:
        mid = movie_id(m)
        if mid is not None:
            scores[mid] = 0.0
    return EngineState(
        candidates=movies,
        asked=set(),
        scores=scores,
        strikes={},
        question_count=0,
        guess_cooldown=0,
        top_streak_mid=None,
        top_streak_len=0,
        consecutive_guesses=0,  # NOUVEAU
        recent_question_types=[],  # NOUVEAU
    )


def snapshot_state(state: EngineState) -> EngineState:
    return EngineState(
        candidates=list(state.candidates),
        asked=set(state.asked),
        scores=dict(state.scores),
        strikes=dict(state.strikes),
        question_count=state.question_count,
        guess_cooldown=state.guess_cooldown,
        top_streak_mid=state.top_streak_mid,
        top_streak_len=state.top_streak_len,
        consecutive_guesses=state.consecutive_guesses,  # NOUVEAU
        recent_question_types=list(state.recent_question_types),  # NOUVEAU
    )


def sort_candidates(state: EngineState) -> None:
    def key_func(m: dict) -> Tuple[float, float]:
        mid = movie_id(m)
        if mid is None:
            return (-1e9, 0.0)
        score = float(state.scores.get(mid, 0.0))
        pop = float(m.get("popularity", 0.0))
        return (-score, -pop)

    state.candidates.sort(key=key_func)


def update_state_with_answer(
    state: EngineState,
    q: Question,
    ans: Answer,
    max_strikes: int,
    debug_target_id: Optional[int] = None,
) -> None:
    """
    Ajuste les scores et retire les films qui accumulent trop de contradictions.
    AMÉLIORÉ: Gestion fine des données manquantes + scoring différencié par type de question.
    """
    # Identification des questions à élimination DURE
    hard_elimination_prefixes = [
        "franchise_",
        "language_",
        "director_",
        "joker_title_",
        "char_",
        "decade_",
        "year_",
        "validate_",      # AMÉLIORATION: les questions de validation sont aussi dures
    ]
    
    hard_elimination_keys = {
        "is_animation",
        "is_live_action",
        "is_short",
        "is_feature",
        "runtime_lt_90",
        "runtime_ge_150",
        "before_2000",
        "after_2010",
        "is_saga",
        "is_standalone",
        "big_budget",
        "small_budget",
        "is_american",
        "is_french",
        "is_european",
        "is_asian",
    }
    
    # Vérifier si c'est une question à élimination dure
    is_hard_elimination = (
        q.key in hard_elimination_keys or
        any(q.key.startswith(prefix) for prefix in hard_elimination_prefixes)
    )
    
    # AMÉLIORATION: Le boost "oui" varie selon le type de question
    # Les questions de validation/acteur/réalisateur sont très fortes
    def yes_boost(key: str) -> float:
        if key.startswith("validate_"):
            return 8.0   # Très fort: question ciblée sur le #1
        if key.startswith(("director_", "dyn_director_")):
            return 7.0   # Réalisateur = très discriminant
        if key.startswith(("franchise_", "char_")):
            return 6.0   # Franchise/Personnage = exclusif
        if key.startswith(("actor_", "dyn_actor_")):
            return 5.0   # Acteur
        if key.startswith(("language_", "decade_", "year_")):
            return 5.0   # Filtres temporels/linguistiques
        if key.startswith("genre_"):
            return 3.0   # Genre (moins exclusif)
        return 5.0        # Défaut

    def no_boost(key: str) -> float:
        if key.startswith("validate_"):
            return 4.0
        if key.startswith(("director_", "franchise_", "char_")):
            return 4.0
        if key.startswith(("actor_", "dyn_actor_", "dyn_director_")):
            return 3.0
        return 3.0

    if ans == "y":
        # ÉLIMINATION IMMÉDIATE: tous ceux qui répondent False sont éliminés
        to_keep = []
        for m in state.candidates:
            mid = movie_id(m)
            if mid is None:
                continue
            r = q.predicate(m)
            if r is True:
                state.scores[mid] = state.scores.get(mid, 0.0) + yes_boost(q.key)
                to_keep.append(m)
            elif r is None:
                # AMÉLIORATION: données manquantes → pénalité plus forte pour les questions dures
                penalty = -2.0 if is_hard_elimination else -0.5
                state.scores[mid] = state.scores.get(mid, 0.0) + penalty
                to_keep.append(m)
            # Si r is False → ÉLIMINER
        
        state.candidates = to_keep
        remaining_ids = {movie_id(m) for m in state.candidates if movie_id(m) is not None}
        state.scores = {mid: score for mid, score in state.scores.items() if mid in remaining_ids}
        state.strikes = {mid: strikes for mid, strikes in state.strikes.items() if mid in remaining_ids}

    elif ans == "n":
        # ÉLIMINATION IMMÉDIATE: tous ceux qui répondent True sont éliminés
        to_keep = []
        for m in state.candidates:
            mid = movie_id(m)
            if mid is None:
                continue
            r = q.predicate(m)
            if r is False:
                state.scores[mid] = state.scores.get(mid, 0.0) + no_boost(q.key)
                to_keep.append(m)
            elif r is None:
                # AMÉLIORATION: données manquantes → légère pénalité pour questions dures
                penalty = -1.0 if is_hard_elimination else 0.3
                state.scores[mid] = state.scores.get(mid, 0.0) + penalty
                to_keep.append(m)
            # Si r is True → ÉLIMINER
        
        state.candidates = to_keep
        remaining_ids = {movie_id(m) for m in state.candidates if movie_id(m) is not None}
        state.scores = {mid: score for mid, score in state.scores.items() if mid in remaining_ids}
        state.strikes = {mid: strikes for mid, strikes in state.strikes.items() if mid in remaining_ids}

    elif ans == "py":
        for m in state.candidates:
            mid = movie_id(m)
            if mid is None:
                continue
            r = q.predicate(m)
            if r is True:
                boost = 2.0 if is_hard_elimination else 1.0
                state.scores[mid] = state.scores.get(mid, 0.0) + boost
            elif r is False:
                penalty = -2.5 if is_hard_elimination else -1.0
                state.scores[mid] = state.scores.get(mid, 0.0) + penalty
                # AMÉLIORATION: accumuler des strikes sur les questions dures
                if is_hard_elimination:
                    state.strikes[mid] = state.strikes.get(mid, 0) + 1

    elif ans == "pn":
        for m in state.candidates:
            mid = movie_id(m)
            if mid is None:
                continue
            r = q.predicate(m)
            if r is False:
                boost = 2.0 if is_hard_elimination else 1.0
                state.scores[mid] = state.scores.get(mid, 0.0) + boost
            elif r is True:
                penalty = -2.5 if is_hard_elimination else -1.0
                state.scores[mid] = state.scores.get(mid, 0.0) + penalty
                if is_hard_elimination:
                    state.strikes[mid] = state.strikes.get(mid, 0) + 1

    elif ans == "?":
        for m in state.candidates:
            mid = movie_id(m)
            if mid is None:
                continue
            r = q.predicate(m)
            if r is None:
                state.scores[mid] = state.scores.get(mid, 0.0) + 0.2

    # Élimination par strikes (sauf si c'était une question à élimination dure, déjà géré)
    if not is_hard_elimination:
        to_remove = []
        for m in state.candidates:
            mid = movie_id(m)
            if mid is None:
                continue
            if state.strikes.get(mid, 0) >= max_strikes:
                to_remove.append(mid)

        if to_remove:
            state.candidates = [m for m in state.candidates if movie_id(m) not in to_remove]
            for mid in to_remove:
                state.scores.pop(mid, None)
                state.strikes.pop(mid, None)

    sort_candidates(state)

    if debug_target_id is not None and debug_target_id in state.scores:
        print(
            f"[DEBUG] Film cible {debug_target_id}: score={state.scores[debug_target_id]:.2f}, strikes={state.strikes.get(debug_target_id, 0)}"
        )


# =========================
# Display helpers
# =========================

def short_movie_str(m: dict) -> str:
    title = str(m.get("title") or "N/A")
    y = safe_year(m.get("release_date"))
    year = str(y) if y is not None else "N/A"
    return f"{title} ({year})"

def print_top(state: EngineState, limit: int = 10) -> None:
    for m in state.candidates[:limit]:
        mid = movie_id(m)
        sc = state.scores.get(mid, 0.0) if mid is not None else 0.0
        st = state.strikes.get(mid, 0) if mid is not None else 0
        print(f"- {short_movie_str(m)} | score={sc:.2f} | strikes={st}")
    if len(state.candidates) > limit:
        print(f"... +{len(state.candidates) - limit} autres")


# =========================
# Convergence: mode "guess" + prune
# =========================

def score_of(state: EngineState, m: dict) -> float:
    mid = movie_id(m)
    if mid is None:
        return -1e9
    return float(state.scores.get(mid, 0.0))

def should_enter_guess_mode(state: EngineState) -> bool:
    """
    RÈGLES STRICTES - Guess UNIQUEMENT dans 4 cas:
    1. Un seul candidat restant
    2. Score du #1 est 2x supérieur au #2 ET on a posé au moins 5 questions
    3. Le même film est #1 pendant 10 questions d'affilée
    4. NOUVEAU: Score du #1 très élevé (>= 15) ET #2 négatif ET >= 7 questions posées
    """
    # CAS 1: Un seul candidat
    if len(state.candidates) == 1:
        return True
    
    # Nécessite un minimum de questions pour éviter les faux positifs prématurés
    min_questions_for_ratio = 5
    
    # CAS 2: Score 2x supérieur au #2 (avec garde-fou)
    if len(state.candidates) >= 2 and state.question_count >= min_questions_for_ratio:
        s1 = score_of(state, state.candidates[0])
        s2 = score_of(state, state.candidates[1])
        
        # Le #1 doit avoir un score 2x supérieur au #2
        if s2 > 0 and (s1 / s2) >= 2.0:
            return True
        # Cas spécial: #2 négatif mais #1 très positif
        elif s2 <= 0 and s1 >= 10.0:
            return True
    
    # CAS 3: Streak de 10 questions minimum
    if state.top_streak_len >= 10:
        return True
    
    # CAS 4: NOUVEAU - Score très élevé avec pool réduit
    if len(state.candidates) <= 5 and state.question_count >= 7:
        s1 = score_of(state, state.candidates[0])
        if s1 >= 15.0:
            return True
    
    # Sinon: PAS DE GUESS, continuer les questions
    return False

def ask_yes_no(prompt: str) -> bool:
    ans = input(prompt).strip().lower()
    while ans not in ("y", "n"):
        ans = input(prompt).strip().lower()
    return ans == "y"

def eliminate_movie(state: EngineState, mid: int) -> None:
    # suppression dure: on retire du pool immédiatement
    state.candidates = [m for m in state.candidates if movie_id(m) != mid]
    state.scores.pop(mid, None)
    state.strikes.pop(mid, None)

def read_answer() -> Answer:
    """
    y  : oui
    n  : non
    ?  : je ne sais pas
    py : probablement oui
    pn : probablement non
    u  : undo (retour en arrière)
    """
    ans = input("Réponds (y/n/?/py/pn/u) : ").strip().lower()
    while ans not in ("y", "n", "?", "py", "pn", "u"):
        ans = input("Réponds (y/n/?/py/pn/u) : ").strip().lower()
    return ans


# NOUVEAU: Fonction pour poser des questions discriminantes ciblées
def get_discriminating_questions(
    conn: sqlite3.Connection,
    candidates: List[dict],
    asked: Set[str],
    count: int = 5,
) -> List[Question]:
    """
    Génère des questions discriminantes basées sur les candidats actuels.
    Utilisé quand on a trop de guesses consécutifs ratés.
    MODIFICATION: Sélection déterministe des meilleures questions (pas d'aléatoire).
    """
    all_questions = default_questions(conn)
    dyn_kw = build_dynamic_keyword_questions(conn, candidates, asked, top_k=50)
    dyn_people = build_dynamic_questions(conn, candidates, asked, top_k=40)
    
    available = [q for q in all_questions + dyn_kw + dyn_people if q.key not in asked]
    
    # Trier par score de discrimination
    scored = [(q, q.score(candidates)) for q in available]
    scored = [(q, s) for q, s in scored if s > 0.1]  # Garder seulement les questions utiles
    scored.sort(key=lambda x: x[1], reverse=True)
    
    # MODIFICATION: Prendre directement les N meilleures questions (pas d'aléatoire)
    return [q for q, _ in scored[:count]]


# =========================
# Main loop
# =========================

def main() -> int:
    parser = argparse.ArgumentParser(description="Akinator de films (SQLite) - version tolérante/score AMÉLIORÉE.")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="Chemin vers movies.db")
    parser.add_argument("--pages", type=int, default=0, help="Limiter le nombre de films (pages*20). 0=all")
    parser.add_argument("--max-strikes", type=int, default=3, help="Contradictions avant élimination d'un film")
    parser.add_argument("--top-streak-questions", type=int, default=3, help="Si le même film reste #1 pendant N questions, proposer un guess")
    parser.add_argument("--guess-cooldown", type=int, default=2, help="Après un guess raté, forcer au moins N questions avant de reguesser (évite les guesses en chaîne)")
    parser.add_argument("--max-consecutive-guesses", type=int, default=4, help="Maximum de guesses consécutifs avant de forcer des questions ciblées")
    parser.add_argument("--debug-target-id", type=int, default=0, help="ID du film à tracer (0=off)")
    args = parser.parse_args()

    db_path = args.db
    pages = args.pages if args.pages > 0 else None
    max_strikes = max(1, int(args.max_strikes))
    top_streak_questions = max(2, int(args.top_streak_questions))
    max_consecutive_guesses = max(2, int(args.max_consecutive_guesses))  # NOUVEAU
    debug_target_id = args.debug_target_id if args.debug_target_id > 0 else None

    print("╔════════════════════════════════════════════════════════╗")
    print("║         AKINATOR DE FILMS - ULTRA RAPIDE 🚀           ║")
    print("╚════════════════════════════════════════════════════════╝")
    print()
    print("Pense à un film populaire, et je vais essayer de le deviner.")
    print("Réponses: y/n/?/py/pn, et u pour annuler la dernière réponse.")
    print()

    conn = None
    try:
        print("⏳ Initialisation de la base de données...", end='', flush=True)
        conn = get_connection(db_path)
        
        # OPTIMISATION: Créer des index pour accélérer les requêtes
        cursor = conn.cursor()
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_movie_genres_movie ON movie_genres(movie_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_movie_cast_movie ON movie_cast(movie_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_movie_crew_movie ON movie_crew(movie_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_movie_keywords_movie ON movie_keywords(movie_id)")
        except:
            pass  # Index déjà existants
        
        load_genres(conn)
        print(" ✓")

        print("⏳ Chargement des films...", end='', flush=True)
        movies = discover_movies(conn, pages=pages)
        print(f" ✓ {len(movies)} films chargés")
        print()

        questions = default_questions(conn)

        state = init_state(movies)
        sort_candidates(state)
        state.top_streak_mid = movie_id(state.candidates[0]) if state.candidates else None
        state.top_streak_len = 0

        history: List[EngineState] = []

        while True:
            if not state.candidates:
                print("Aucun candidat restant (trop de contradictions).")
                print("Astuce: utilise '?' ou 'py/pn' quand tu es incertain.")
                return 0

            # affichage du top quand il reste peu
            if len(state.candidates) <= 7:
                print(f"\nIl ne reste que {len(state.candidates)} candidats:")
                print_top(state, limit=7)
                print()

            # condition de victoire (top très dominant ou 1 restant)
            if len(state.candidates) == 1:
                print()
                print("J'AI TROUVÉ :", short_movie_str(state.candidates[0]))
                print(f"Questions: {state.question_count}")
                return 0

            # NOUVEAU: Si trop de guesses consécutifs ratés, forcer des questions discriminantes
            if state.consecutive_guesses >= max_consecutive_guesses:
                print("\n[Mode questions ciblées activé - je cherche de nouvelles pistes...]")
                targeted_questions = get_discriminating_questions(conn, state.candidates, state.asked, count=3)
                
                for tq in targeted_questions:
                    if state.consecutive_guesses < max_consecutive_guesses:
                        break
                        
                    yes, no, unk = split_counts(state.candidates, tq.predicate)
                    print(f"\nQuestion #{state.question_count + 1}: {tq.text}")
                    ans = read_answer()

                    if ans == "u":
                        if not history:
                            print("Impossible: aucun historique.")
                            print()
                            continue
                        state = history.pop()
                        print("OK, retour en arrière effectué.")
                        print(f"Candidats: {len(state.candidates)}")
                        print()
                        continue

                    history.append(snapshot_state(state))
                    state.asked.add(tq.key)
                    state.question_count += 1
                    state.consecutive_guesses = 0  # Reset du compteur après une vraie question
                    
                    # CORRECTION: Décrémenter le cooldown aussi ici
                    if state.guess_cooldown > 0:
                        state.guess_cooldown -= 1

                    update_state_with_answer(state, tq, ans, max_strikes=max_strikes, debug_target_id=debug_target_id)
                    print(f"Restants: {len(state.candidates)}")
                    print()
            
            # STRICT MODE: Vérifier UNIQUEMENT les 3 règles strictes
            # Pas de guess prématuré basé sur le nombre de candidats
            
            # Si on entre en mode guess (selon les 3 règles strictes) ET pas de cooldown
            if should_enter_guess_mode(state) and state.guess_cooldown == 0:
                top = state.candidates[0]
                guess = short_movie_str(top)
                
                # Afficher la raison du guess
                if len(state.candidates) == 1:
                    print(f"\n✅ UN SEUL CANDIDAT RESTANT!")
                elif len(state.candidates) >= 2:
                    s1 = score_of(state, state.candidates[0])
                    s2 = score_of(state, state.candidates[1])
                    if s2 > 0:
                        ratio = s1 / s2
                        print(f"\n💯 DOMINATION 2X (Ratio: {ratio:.1f}x)")
                    else:
                        print(f"\n💯 DOMINATION ABSOLUE (Score #1: {s1:.1f})")
                elif state.top_streak_len >= 10:
                    print(f"\n🔥 STREAK DE {state.top_streak_len} QUESTIONS!")
                
                if ask_yes_no(f"Je pense que c'est: {guess}. C'est ça ? (y/n) : "):
                    print("\n✅ J'AI TROUVÉ :", guess)
                    print(f"Questions: {state.question_count}")
                    return 0
                else:
                    mid = movie_id(top)
                    if mid is not None:
                        eliminate_movie(state, mid)
                    sort_candidates(state)
                    state.guess_cooldown = args.guess_cooldown
                    state.top_streak_mid = movie_id(state.candidates[0]) if state.candidates else None
                    state.top_streak_len = 0
                    state.consecutive_guesses += 1
                    print("OK, je continue avec plus de questions.\n")
                    continue
            
            # Seulement maintenant on génère les questions (si on n'a pas guess)
            dyn_kw = build_dynamic_keyword_questions(conn, state.candidates, state.asked, top_k=80)
            dyn_people = build_dynamic_questions(conn, state.candidates, state.asked, top_k=60)
            dyn_years = build_dynamic_year_questions(state.candidates, state.asked)
            
            # Questions de VALIDATION du TOP candidat (priorité élevée)
            validation_questions = build_top_validation_questions(conn, state.candidates, state.asked)
            
            # NOUVEAU: Questions de DÉSAMBIGUÏSATION BINAIRE sur très petit pool
            binary_questions = build_binary_disambiguation_questions(conn, state.candidates, state.asked)
            
            # STRATÉGIE: Questions de validation + binaires EN PREMIER pour convergence rapide
            merged_questions = validation_questions + binary_questions + dyn_kw + dyn_people + dyn_years + questions

            # AMÉLIORATION: Ajouter de l'aléatoire sur la première question
            is_first = (state.question_count == 0)
            q = choose_best_question(state.candidates, merged_questions, state.asked, is_first_question=is_first, state=state)
            
            # STRICT MODE: Si plus de questions disponibles ET plusieurs candidats
            if q is None:
                if len(state.candidates) == 1:
                    # Un seul candidat: guess automatique
                    print("\n✅ UN SEUL CANDIDAT RESTANT!")
                    print("J'AI TROUVÉ :", short_movie_str(state.candidates[0]))
                    print(f"Questions: {state.question_count}")
                    return 0
                else:
                    # Plusieurs candidats mais plus de questions
                    print(f"\n⚠️ Plus de questions automatiques disponibles.")
                    print(f"Il reste {len(state.candidates)} candidats. Voici le top 5:")
                    print_top(state, limit=min(5, len(state.candidates)))
                    print()
                    
                    # Forcer l'utilisateur à éliminer manuellement
                    choice = input("Tape le numéro du film correct (1-5) ou 'e' pour éliminer le #1 et continuer : ").strip().lower()
                    
                    if choice in ['1', '2', '3', '4', '5']:
                        idx = int(choice) - 1
                        if idx < len(state.candidates):
                            print("\n✅ J'AI TROUVÉ :", short_movie_str(state.candidates[idx]))
                            print(f"Questions: {state.question_count}")
                            return 0
                    elif choice == 'e':
                        # Éliminer le #1 et continuer
                        top = state.candidates[0]
                        mid = movie_id(top)
                        if mid is not None:
                            eliminate_movie(state, mid)
                        sort_candidates(state)
                        print(f"OK, {short_movie_str(top)} éliminé. Il reste {len(state.candidates)} candidats.\n")
                        continue
                    else:
                        print("Choix invalide, je continue.\n")
                        continue

            yes, no, unk = split_counts(state.candidates, q.predicate)
            print(f"Question #{state.question_count + 1}: {q.text}")
            ans = read_answer()

            if ans == "u":
                if not history:
                    print("Impossible: aucun historique.")
                    print()
                    continue
                state = history.pop()
                print("OK, retour en arrière effectué.")
                print(f"Candidats: {len(state.candidates)}")
                print()
                continue

            history.append(snapshot_state(state))

            state.asked.add(q.key)
            
            # NOUVEAU: Tracker le type de question pour diversité
            q_type = get_question_type(q)
            state.recent_question_types.append(q_type)
            # Garder seulement les 10 dernières pour économiser mémoire
            if len(state.recent_question_types) > 10:
                state.recent_question_types = state.recent_question_types[-10:]
            
            # NOUVEAU: Si on répond "oui" à une question de langue, exclure TOUTES les autres
            if ans == "y" and q.key.startswith("language_"):
                all_languages = {"language_en", "language_fr", "language_ja", "language_es", 
                               "language_de", "language_it", "language_ko", "language_zh"}
                # Ajouter toutes les autres langues à "asked" pour les exclure
                for lang in all_languages:
                    if lang != q.key:  # Sauf celle qu'on vient de confirmer
                        state.asked.add(lang)
                print(f"   [Langue confirmée: {q.key.replace('language_', '')} - Autres langues exclues]")
            
            state.question_count += 1
            state.consecutive_guesses = 0

            if state.guess_cooldown > 0:
                state.guess_cooldown -= 1

            update_state_with_answer(
                state,
                q,
                ans,
                max_strikes=max_strikes,
                debug_target_id=debug_target_id,
            )

            print(f"Restants: {len(state.candidates)}")

            top = state.candidates[0]
            mid = movie_id(top)

            if mid is not None:
                if state.top_streak_mid == mid:
                    state.top_streak_len += 1
                else:
                    state.top_streak_mid = mid
                    state.top_streak_len = 1

                if state.top_streak_len >= 9 and state.guess_cooldown == 0:
                    guess = short_movie_str(top)
                    if ask_yes_no(f"Le même film est #1 depuis un moment. Je pense que c'est: {guess}. C'est ça ? (y/n) : "):
                        print("\nJ'AI TROUVÉ :", guess)
                        print(f"Questions: {state.question_count}")
                        return 0
                    else:
                        eliminate_movie(state, mid)
                        sort_candidates(state)
                        state.guess_cooldown = args.guess_cooldown
                        state.top_streak_mid = movie_id(state.candidates[0]) if state.candidates else None
                        state.top_streak_len = 0
                        state.consecutive_guesses += 1
                        print("OK, je continue.\n")
                        continue
            print()

    finally:
        close_connection()

if __name__ == "__main__":
    raise SystemExit(main())
