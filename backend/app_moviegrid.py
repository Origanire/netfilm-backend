from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import os
import random
import time

app = Flask(__name__)

CORS(app, resources={
    r"/*": {
        "origins": ["https://origanire.github.io"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"],
    }
})

TMDB_API_KEY = os.getenv('TMDB_API_KEY', 'a46949b0732719a510a26fd7c0a1a3ae')

# --- CONFIGURATION POUR LA GÉNÉRATION ---
# On définit des pools de critères "sûrs" pour augmenter les chances de succès
COMMON_GENRES = [
    {'id': '28', 'name': 'Action'}, {'id': '35', 'name': 'Comédie'}, 
    {'id': '18', 'name': 'Drame'}, {'id': '27', 'name': 'Horreur'},
    {'id': '878', 'name': 'Science-Fiction'}, {'id': '10749', 'name': 'Romance'}
]

YEAR_RANGES = [
    {'label': 'Années 90', 'value': '1990-1999'},
    {'label': 'Années 2000', 'value': '2000-2009'},
    {'label': 'Années 2010', 'value': '2010-2019'},
    {'label': 'Films récents', 'value': '2020-2025'}
]

# Liste simplifiée d'acteurs très prolifiques (ID TMDB)
POPULAR_ACTORS = [
    {'id': '287', 'name': 'Brad Pitt'}, {'id': '31', 'name': 'Tom Hanks'},
    {'id': '1892', 'name': 'Matt Damon'}, {'id': '113', 'name': 'Christopher Walken'},
    {'id': '8891', 'name': 'Samuel L. Jackson'}, {'id': '204', 'name': 'Kate Huinslet'}
]

# --- FONCTIONS EXISTANTES MODIFIÉES OU CONSERVÉES ---

@app.route("/", methods=["GET"])
def home():
    return "API MovieGrid Opérationnelle - Mode Génération Activé"

def check_intersection_exists(row_crit, col_crit):
    """Vérifie si au moins un film existe pour cette combinaison"""
    url = "https://api.themoviedb.org/3/discover/movie"
    params = {
        'api_key': TMDB_API_KEY,
        'language': 'fr-FR',
        'page': 1
    }
    params = apply_criterion_to_params(params, row_crit)
    params = apply_criterion_to_params(params, col_crit)
    
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            return response.json().get('total_results', 0) > 0
    except:
        return False
    return False

@app.route('/generate-grid', methods=['GET'])
def generate_grid():
    """Génère une grille 3x3 valide (chaque case a une solution)"""
    size = 3
    max_attempts = 10
    
    for attempt in range(max_attempts):
        # On mélange et on prend des critères au hasard
        shuffled_genres = random.sample(COMMON_GENRES, 3)
        shuffled_years = random.sample(YEAR_RANGES, 3)
        
        rows = [{'type': 'genre', 'value': g['id'], 'label': g['name']} for g in shuffled_genres]
        cols = [{'type': 'year', 'value': y['value'], 'label': y['label']} for y in shuffled_years]
        
        valid_grid = True
        
        # Vérification de chaque intersection (9 appels API)
        for r_crit in rows:
            for c_crit in cols:
                if not check_intersection_exists(r_crit, c_crit):
                    valid_grid = False
                    break
            if not valid_grid: break
            
        if valid_grid:
            return jsonify({
                'rows': rows,
                'cols': cols,
                'status': 'success',
                'attempt': attempt + 1
            })
            
    return jsonify({'error': 'Impossible de générer une grille 100% valide'}), 500

@app.route('/verify-movie', methods=['POST'])
def verify_movie():
    try:
        data = request.json
        movie_id = data.get('movieId')
        row_criterion = data.get('rowCriterion')
        col_criterion = data.get('colCriterion')

        if not movie_id: return jsonify({'isValid': False}), 400

        url = f"https://api.themoviedb.org/3/movie/{movie_id}"
        params = {'api_key': TMDB_API_KEY, 'append_to_response': 'credits', 'language': 'fr-FR'}
        
        response = requests.get(url, params=params)
        if response.status_code != 200: return jsonify({'isValid': False})

        movie = response.json()
        matches_row = check_criterion(movie, row_criterion)
        matches_col = check_criterion(movie, col_criterion)

        return jsonify({'isValid': matches_row and matches_col})
    except Exception as e:
        return jsonify({'isValid': False})

def check_criterion(movie, criterion):
    if not criterion: return True # Si pas de critère, c'est valide
    c_type = criterion.get('type')
    c_val = criterion.get('value')

    if c_type == 'genre':
        return any(str(g['id']) == str(c_val) for g in movie.get('genres', []))
    elif c_type == 'year':
        release_date = movie.get('release_date', '')
        if not release_date: return False
        year = int(release_date[:4])
        start, end = map(int, c_val.split('-'))
        return start <= year <= end
    # ... autres critères (acteurs, etc) identiques à ta version ...
    return False

def apply_criterion_to_params(params, criterion):
    if not criterion: return params
    c_type = criterion.get('type')
    c_val = criterion.get('value')

    if c_type == 'genre': params['with_genres'] = c_val
    elif c_type == 'actor': params['with_cast'] = c_val
    elif c_type == 'director': params['with_crew'] = c_val
    elif c_type == 'year':
        start, end = c_val.split('-')
        params['primary_release_date.gte'] = f"{start}-01-01"
        params['primary_release_date.lte'] = f"{end}-12-31"
    return params

@app.route('/get-solutions', methods=['POST'])
def get_solutions():
    # Identique à ton code original mais utilisé ici pour débugger ou aider le joueur
    data = request.json
    params = {'api_key': TMDB_API_KEY, 'language': 'fr-FR', 'sort_by': 'popularity.desc'}
    params = apply_criterion_to_params(params, data.get('rowCriterion'))
    params = apply_criterion_to_params(params, data.get('colCriterion'))

    response = requests.get("https://api.themoviedb.org/3/discover/movie", params=params)
    if response.status_code == 200:
        movies = response.json().get('results', [])[:5]
        return jsonify({'movies': [{'id': m['id'], 'title': m['title']} for m in movies]})
    return jsonify({'movies': []})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003, debug=True)
