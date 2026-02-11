# Akinator IA - Documentation

## 📋 Vue d'ensemble

Cette version modifiée du moteur Akinator utilise l'API Claude d'Anthropic pour gérer intelligemment les questions et les réponses, au lieu d'utiliser un système de probabilités local. L'IA analyse la base de données de films et pose des questions stratégiques pour deviner le film pensé par l'utilisateur.

## 🔑 Caractéristiques principales

### ✅ Avantages par rapport à la version originale

1. **Intelligence contextuelle**: L'IA comprend le contexte et adapte ses questions
2. **Questions naturelles**: Formulation plus humaine et conversationnelle
3. **Pas de maintenance de règles**: L'IA s'adapte automatiquement sans coder de nouvelles règles
4. **Apprentissage continu**: L'IA améliore sa stratégie au fil de la conversation
5. **Compatibilité frontend**: L'interface reste identique pour le frontend

### 🎯 Comment ça fonctionne

```
Utilisateur pense à un film
        ↓
IA reçoit la base de données de films
        ↓
IA pose des questions stratégiques (genre, époque, acteurs, etc.)
        ↓
Utilisateur répond: oui / non / je ne sais pas
        ↓
IA affine ses hypothèses
        ↓
Quand confiance > 90% → Proposition du film
        ↓
Confirmation ou continuation
```

## 🚀 Installation

### 1. Prérequis

```bash
pip install requests --break-system-packages
```

### 2. Configuration de la clé API

Vous devez obtenir une clé API Anthropic sur: https://console.anthropic.com/

Puis la configurer:

```bash
export ANTHROPIC_API_KEY="votre_clé_api_ici"
```

Ou dans votre fichier `.env`:

```
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxx
```

### 3. Utilisation en ligne de commande

```bash
python engine_akinator_ai.py --db path/to/movies.db
```

## 🔌 Intégration avec votre Backend

### Option 1: Remplacement complet

Remplacez simplement `engine_akinator.py` par `engine_akinator_ai.py`:

```bash
cp engine_akinator_ai.py backend/engines/engine_akinator.py
```

### Option 2: Utilisation en parallèle

Gardez les deux versions et utilisez l'IA via une route API dédiée.

### Exemple d'intégration FastAPI/Flask

```python
from engine_akinator_ai import AkinatorSession

# Stockage des sessions (en production, utilisez Redis ou similaire)
sessions = {}

@app.post("/api/akinator/start")
async def start_akinator():
    """Démarre une nouvelle session Akinator."""
    session_id = generate_session_id()
    session = AkinatorSession(db_path="path/to/movies.db")
    
    result = session.start()
    sessions[session_id] = session
    
    return {
        "session_id": session_id,
        **result
    }

@app.post("/api/akinator/answer")
async def answer_question(session_id: str, answer: str):
    """Envoie une réponse et obtient la prochaine question."""
    session = sessions.get(session_id)
    if not session:
        return {"error": "Session invalide"}
    
    result = session.answer(answer)
    return result

@app.post("/api/akinator/confirm")
async def confirm_guess(session_id: str, is_correct: bool):
    """Confirme si la proposition était correcte."""
    session = sessions.get(session_id)
    if not session:
        return {"error": "Session invalide"}
    
    result = session.confirm(is_correct)
    
    # Si trouvé, supprimer la session
    if result.get("result") == "found":
        del sessions[session_id]
    
    return result
```

## 📡 Format des réponses API

### 1. Démarrage de session (`/start`)

```json
{
  "status": "ok",
  "action": "question",
  "content": "Est-ce un film d'action ?",
  "question_number": 1,
  "total_movies": 15432
}
```

### 2. Réponse à une question (`/answer`)

**Question suivante:**
```json
{
  "status": "ok",
  "action": "question",
  "content": "Le film est-il sorti après 2010 ?",
  "question_number": 2
}
```

**Proposition de film:**
```json
{
  "status": "ok",
  "action": "guess",
  "content": "Inception",
  "question_number": 5
}
```

### 3. Confirmation (`/confirm`)

**Film trouvé:**
```json
{
  "status": "ok",
  "result": "found",
  "questions_asked": 7
}
```

**Continuer:**
```json
{
  "status": "ok",
  "result": "continue",
  "action": "question",
  "content": "Y a-t-il Leonardo DiCaprio dans ce film ?",
  "question_number": 8
}
```

## 🎮 Compatibilité Frontend

Le frontend n'a **aucune modification** à faire ! L'API reste compatible:

### Flux de communication

```javascript
// 1. Démarrer le jeu
const response = await fetch('/api/akinator/start', { method: 'POST' });
const data = await response.json();
// data.content contient la question

// 2. Répondre à une question
const answer = await fetch('/api/akinator/answer', {
  method: 'POST',
  body: JSON.stringify({
    session_id: sessionId,
    answer: 'y' // ou 'n' ou '?'
  })
});

// 3. Si action === "guess", confirmer
if (data.action === 'guess') {
  const confirm = await fetch('/api/akinator/confirm', {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      is_correct: true
    })
  });
}
```

## ⚙️ Configuration avancée

### Personnalisation du modèle IA

Dans `engine_akinator_ai.py`, vous pouvez changer:

```python
# Utiliser un modèle différent
AI_MODEL = "claude-sonnet-4-20250514"  # Rapide et intelligent
# ou
AI_MODEL = "claude-opus-4-5-20251101"   # Plus puissant mais plus lent
```

### Limitation du nombre de films

Pour des réponses plus rapides et moins coûteuses:

```python
def initialize_game(self, movies: List[dict]):
    # Limiter à 1000 films populaires au lieu de tous
    self.movies_database = movies[:1000]
```

## 💰 Coût estimé

Avec l'API Claude:
- **Claude Sonnet 4**: ~$3 / million de tokens input, ~$15 / million de tokens output
- **Partie moyenne**: ~5-10 questions = ~2000 tokens total
- **Coût par partie**: ~$0.001 - $0.003 (0.1 à 0.3 centimes)

Pour 1000 parties/jour: ~$1-3/jour

## 🔒 Sécurité

### Variables d'environnement

**Ne JAMAIS** commiter votre clé API dans le code !

Utilisez:
```bash
# .env
ANTHROPIC_API_KEY=sk-ant-xxxxx

# Ou variables d'environnement système
export ANTHROPIC_API_KEY="sk-ant-xxxxx"
```

### Limitation de taux

L'API Anthropic a des limites:
- Requêtes/minute: Varie selon votre plan
- Implémentez un rate limiting côté serveur

```python
from functools import lru_cache
from time import time

@lru_cache(maxsize=100)
def rate_limit(session_id: str, timestamp: int) -> bool:
    # Limiter à 1 requête par seconde
    return True
```

## 🐛 Debugging

### Mode verbose

Ajoutez des logs pour debug:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Dans la classe AkinatorAI
def _call_anthropic_api(self, user_message: str) -> str:
    logging.debug(f"Envoi à l'IA: {user_message}")
    response = ...
    logging.debug(f"Réponse de l'IA: {response}")
    return response
```

### Test sans API

Pour tester sans consommer de crédits API:

```python
class MockAkinatorAI(AkinatorAI):
    def _call_anthropic_api(self, user_message: str) -> str:
        # Retourner des réponses mockées
        return "QUESTION: Est-ce un film d'action ?"
```

## 📊 Monitoring

### Métriques à surveiller

1. **Temps de réponse API**: Doit être < 3 secondes
2. **Taux de réussite**: % de films trouvés
3. **Nombre moyen de questions**: Objectif < 15
4. **Coût par partie**: Pour optimisation budget

### Exemple de logging

```python
import time

class AkinatorSession:
    def __init__(self):
        self.start_time = time.time()
        self.api_calls = 0
    
    def answer(self, response: str):
        self.api_calls += 1
        result = ...
        
        # Log metrics
        duration = time.time() - self.start_time
        print(f"Session: {self.api_calls} calls, {duration:.2f}s")
        
        return result
```

## 🚨 Gestion d'erreurs

### Timeout API

```python
try:
    response = requests.post(
        ANTHROPIC_API_URL, 
        headers=headers, 
        json=payload, 
        timeout=10  # 10 secondes max
    )
except requests.exceptions.Timeout:
    return {
        "status": "error",
        "message": "L'IA met trop de temps à répondre, réessayez"
    }
```

### Limite de tokens dépassée

```python
try:
    result = response.json()
except Exception as e:
    if "max_tokens" in str(e):
        # Augmenter max_tokens ou réduire l'historique
        pass
```

## 📝 Exemples de questions générées par l'IA

L'IA adapte ses questions selon le contexte:

**Début de partie (questions larges):**
- "Est-ce un film d'action ?"
- "Le film est-il sorti après 2010 ?"
- "S'agit-il d'un film américain ?"

**Milieu de partie (questions ciblées):**
- "Y a-t-il des super-héros dans ce film ?"
- "Le film se passe-t-il dans l'espace ?"
- "Est-ce un film de Christopher Nolan ?"

**Fin de partie (questions très spécifiques):**
- "Leonardo DiCaprio joue-t-il dans ce film ?"
- "Le film parle-t-il de rêves ?"
- "Le film s'appelle-t-il Inception ?"

## 🎓 Conseils d'optimisation

### 1. Cache des résultats fréquents

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_movie_info(movie_id: int) -> dict:
    # Cache les infos de films fréquemment demandés
    return get_details(conn, movie_id)
```

### 2. Pré-calcul des métadonnées

```python
# Au démarrage, calculer les stats
movie_stats = {
    "by_genre": count_by_genre(movies),
    "by_decade": count_by_decade(movies),
    "by_language": count_by_language(movies)
}
```

### 3. Compression de l'historique

```python
# Garder seulement les N derniers messages
MAX_HISTORY = 20

if len(self.conversation_history) > MAX_HISTORY:
    self.conversation_history = self.conversation_history[-MAX_HISTORY:]
```

## 🔮 Améliorations futures possibles

1. **Mode hybride**: Combiner IA + probabilités pour plus de précision
2. **Apprentissage des préférences**: L'IA apprend du comportement utilisateur
3. **Multi-langues**: Questions en français, anglais, espagnol, etc.
4. **Suggestions intelligentes**: "Peut-être avez-vous pensé à..."
5. **Mode compétition**: Comparer IA vs Système probabiliste

## 📞 Support

Pour toute question ou problème:
- GitHub Issues: [votre-repo]/issues
- Email: support@votre-domaine.com
- Documentation Anthropic: https://docs.anthropic.com/

---

**Version**: 1.0.0  
**Dernière mise à jour**: 2024  
**Licence**: MIT
