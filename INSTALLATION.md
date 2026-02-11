# 🚀 Guide d'Installation Rapide - Akinator IA

## Installation en 5 minutes

### 1. Prérequis

- Python 3.8 ou supérieur
- Une clé API Anthropic (gratuite pour tester)

### 2. Installation

```bash
# Cloner ou télécharger les fichiers
cd votre-projet/backend/engines/

# Installer les dépendances
pip install -r requirements.txt --break-system-packages
```

### 3. Configuration

```bash
# Copier le fichier de configuration
cp .env.example .env

# Éditer .env et ajouter votre clé API
nano .env
```

Dans le fichier `.env`, remplacez:
```
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Par votre vraie clé API obtenue sur: https://console.anthropic.com/

### 4. Démarrage

```bash
# Méthode 1: Script automatique
./start.sh

# Méthode 2: Manuelle
export ANTHROPIC_API_KEY="votre_clé"
python api_server.py
```

Le serveur démarre sur: http://localhost:8000

### 5. Test

```bash
# Dans un autre terminal
python test_api.py

# Pour un test complet
python test_api.py --full
```

### 6. Utilisation

#### En ligne de commande

```bash
python engine_akinator_ai.py --db path/to/movies.db
```

#### Via API

```bash
# Démarrer une partie
curl -X POST http://localhost:8000/api/akinator/start

# Répondre à une question
curl -X POST http://localhost:8000/api/akinator/answer \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "answer": "y"}'
```

#### Frontend JavaScript

```javascript
import { AkinatorClient } from './akinator_client.js';

const client = new AkinatorClient('http://localhost:8000');

// Démarrer
const result = await client.startGame();
console.log(result.question);

// Répondre
const next = await client.answerQuestion('y');
```

## 📡 Endpoints API

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/health` | GET | Vérifier l'état du serveur |
| `/api/akinator/start` | POST | Démarrer une nouvelle partie |
| `/api/akinator/answer` | POST | Répondre à une question |
| `/api/akinator/confirm` | POST | Confirmer une proposition |
| `/api/akinator/sessions` | GET | Lister les sessions actives |
| `/api/akinator/sessions/{id}` | DELETE | Supprimer une session |
| `/docs` | GET | Documentation interactive |

## 🔧 Dépannage

### Erreur: "Clé API non configurée"

```bash
# Vérifier que la variable est définie
echo $ANTHROPIC_API_KEY

# Si vide, la définir
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Erreur: "Base de données non trouvée"

```bash
# Vérifier le chemin
ls -la movies.db

# Mettre à jour dans .env
MOVIES_DB_PATH=/chemin/correct/movies.db
```

### Erreur: "Module fastapi non trouvé"

```bash
# Réinstaller les dépendances
pip install -r requirements.txt --break-system-packages
```

### Le serveur ne démarre pas

```bash
# Vérifier que le port 8000 est libre
lsof -i :8000

# Changer le port dans .env
API_PORT=8001
```

## 🎮 Utilisation avec votre Frontend

### Remplacer l'ancien moteur

```bash
# Sauvegarder l'ancien
mv backend/engines/engine_akinator.py backend/engines/engine_akinator_old.py

# Installer le nouveau
cp engine_akinator_ai.py backend/engines/engine_akinator.py
cp api_server.py backend/
```

### Adapter les routes

Si votre frontend appelle `/api/game/start`, modifiez `api_server.py`:

```python
# Changer
@app.post("/api/akinator/start")

# En
@app.post("/api/game/start")
```

### Compatibilité

Le nouveau moteur est **100% compatible** avec votre frontend existant.
Les seules différences:
- Les questions sont générées par l'IA (plus naturelles)
- Les propositions sont plus intelligentes
- Pas besoin de maintenir les règles de probabilité

## 💰 Coûts

Pour référence avec Claude Sonnet 4:

| Usage | Questions | Coût estimé |
|-------|-----------|-------------|
| 1 partie | 5-10 | ~$0.001 |
| 100 parties | 500-1000 | ~$0.10 |
| 1000 parties | 5000-10000 | ~$1.00 |

**Astuce**: Utilisez le cache de réponses pour réduire les coûts en production.

## 📚 Documentation Complète

Voir `README_AI.md` pour:
- Détails d'architecture
- Guide d'optimisation
- Exemples avancés
- Monitoring et métriques

## 🆘 Support

- Issues: [GitHub Issues]
- Email: support@votre-domaine.com
- Docs Anthropic: https://docs.anthropic.com/

## ✅ Checklist de Mise en Production

- [ ] Clé API configurée
- [ ] Base de données accessible
- [ ] CORS configuré correctement
- [ ] Rate limiting activé
- [ ] Monitoring en place
- [ ] Logs configurés
- [ ] Variables d'environnement sécurisées
- [ ] Tests passants
- [ ] Documentation à jour
- [ ] Backup de la base de données

---

**Temps d'installation total**: ~5 minutes  
**Niveau de difficulté**: ⭐⭐☆☆☆ (Facile)  
**Compatibilité**: Frontend existant sans modification
