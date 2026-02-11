# 🆓 GUIDE GEMINI - Version GRATUITE

## 🎯 Pourquoi Gemini ?

**Gemini 2.0 Flash** de Google est **100% GRATUIT** avec une limite généreuse:
- ✅ **1500 requêtes par jour** gratuites
- ✅ **1 million de tokens par minute**
- ✅ **Pas de carte bancaire requise**
- ✅ Performances excellentes pour Akinator

**Comparaison des IA:**

| IA | Coût | Gratuit ? | Vitesse | Qualité |
|----|------|-----------|---------|---------|
| **Gemini 2.0 Flash** | 0€ | ✅ Oui | ⚡ Très rapide | ⭐⭐⭐⭐ |
| Claude Sonnet 4 | ~0.001€/partie | ❌ Non | ⚡ Rapide | ⭐⭐⭐⭐⭐ |
| GPT-4o Mini | ~0.0005€/partie | ❌ Non | ⚡ Rapide | ⭐⭐⭐⭐ |

## 🚀 Installation avec Gemini (2 minutes)

### 1. Obtenir une clé API Google (GRATUIT)

1. Allez sur: **https://aistudio.google.com/app/apikey**
2. Connectez-vous avec votre compte Google
3. Cliquez sur **"Create API key"**
4. Copiez la clé (commence par `AIza...`)

### 2. Configuration

```bash
# Copiez le fichier de config
cp env.example .env

# Éditez le fichier
nano .env
```

Dans le fichier `.env`, configurez:
```bash
# Choisir Gemini
AI_PROVIDER=gemini

# Coller votre clé Google
GOOGLE_API_KEY=AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

# Chemin vers votre base de données
MOVIES_DB_PATH=./movies.db
```

### 3. Installation des dépendances

```bash
pip install requests --break-system-packages
pip install fastapi uvicorn pydantic --break-system-packages
```

### 4. Lancement

```bash
# Mode console (test rapide)
python engine_akinator_multi_ai.py --provider gemini

# Mode serveur API (pour votre app)
python api_server.py
```

## 🎮 Utilisation

### Mode Console

```bash
export GOOGLE_API_KEY="AIzaSy..."
python engine_akinator_multi_ai.py --provider gemini

# Exemple de partie:
# ❓ Question #1: Est-ce un film d'action ?
# Réponse (y/n/?) : y
# ❓ Question #2: Le film est-il sorti après 2010 ?
# ...
```

### Mode API

```bash
# Démarrer le serveur
./start.sh

# Tester
curl http://localhost:8000/health

# Devrait afficher:
{
  "status": "ok",
  "current_provider": "gemini",
  "api_keys_configured": {
    "claude": false,
    "gemini": true,
    "openai": false
  }
}
```

## 🔄 Changer d'IA facilement

Vous pouvez changer d'IA en **1 ligne** dans `.env`:

```bash
# Pour utiliser Gemini (gratuit)
AI_PROVIDER=gemini
GOOGLE_API_KEY=AIzaSy...

# Pour utiliser Claude (meilleure qualité)
AI_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant...

# Pour utiliser OpenAI
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

Redémarrez simplement le serveur !

## 💰 Limites gratuites Gemini

| Limite | Valeur |
|--------|--------|
| Requêtes/jour | 1500 |
| Requêtes/minute | 15 |
| Tokens/minute | 1 million |

**Pour 1500 requêtes/jour:**
- Si 1 partie = ~10 requêtes
- Vous pouvez faire **~150 parties par jour GRATUITEMENT**

C'est largement suffisant pour un usage normal !

## 🆚 Gemini vs Claude vs OpenAI

### Pour Akinator, voici notre recommandation:

**🥇 Gemini 2.0 Flash** (Recommandé pour commencer)
- ✅ Gratuit
- ✅ Rapide
- ✅ Très bonne qualité
- ✅ Limite généreuse
- ⚠️ Questions parfois moins naturelles

**🥈 Claude Sonnet 4** (Pour la meilleure expérience)
- ✅ Meilleure compréhension
- ✅ Questions très naturelles
- ✅ Précision maximale
- ❌ Payant (~$0.001/partie)

**🥉 GPT-4o Mini** (Alternative payante)
- ✅ Bonne qualité
- ✅ Moins cher que Claude
- ❌ Payant (~$0.0005/partie)

## 📊 Exemples de questions générées

### Gemini
```
Question 1: Est-ce un film d'action ?
Question 2: Le film est-il sorti après 2010 ?
Question 3: Y a-t-il des super-héros dans le film ?
Question 4: Le film se passe-t-il dans l'espace ?
```

### Claude (comparaison)
```
Question 1: S'agit-il d'un film d'action ?
Question 2: Ce film a-t-il été réalisé au cours des 15 dernières années ?
Question 3: L'histoire tourne-t-elle autour de personnages aux pouvoirs surhumains ?
Question 4: L'intrigue se déroule-t-elle principalement hors de la Terre ?
```

Les deux fonctionnent très bien ! Gemini est juste légèrement plus direct.

## 🔧 Résolution de problèmes

### Erreur: "GOOGLE_API_KEY non configurée"

```bash
# Vérifier
echo $GOOGLE_API_KEY

# Si vide, configurer
export GOOGLE_API_KEY="AIzaSy..."

# Ou éditer .env
nano .env
```

### Erreur: "API quota exceeded"

Vous avez atteint la limite journalière (1500 requêtes).
Solutions:
1. Attendre demain (reset à minuit UTC)
2. Créer un autre compte Google (limite par compte)
3. Passer à Claude ou OpenAI (payant mais illimité)

### Erreur: "Invalid API key"

Votre clé est incorrecte ou expirée:
1. Retournez sur https://aistudio.google.com/app/apikey
2. Créez une nouvelle clé
3. Mettez à jour `.env`

## 🎓 Conseils d'optimisation

### Réduire les coûts (même gratuit)

```bash
# Limiter le nombre de films pour des réponses plus rapides
# Dans engine_akinator_multi_ai.py, ligne ~250:

def initialize_game(self, movies: List[dict]):
    # Au lieu de tous les films
    self.movies_database = movies[:1000]  # Top 1000 seulement
```

### Cache pour éviter les appels répétés

```python
# Ajouter un cache simple pour les questions fréquentes
from functools import lru_cache

@lru_cache(maxsize=100)
def get_cached_response(question: str) -> str:
    # Cache les 100 dernières questions
    pass
```

## 📈 Monitoring de votre quota

Gemini n'a pas de dashboard de quota, mais vous pouvez tracer:

```python
import json
from datetime import datetime

# Logger chaque appel
with open('api_calls.log', 'a') as f:
    f.write(f"{datetime.now()}: Gemini call\n")

# Compter les appels du jour
calls_today = len([
    line for line in open('api_calls.log')
    if datetime.now().date().isoformat() in line
])

print(f"Appels aujourd'hui: {calls_today}/1500")
```

## 🔄 Migration vers Claude (si besoin)

Si vous voulez passer à Claude plus tard:

```bash
# 1. Obtenir une clé Claude
# https://console.anthropic.com/

# 2. Modifier .env
AI_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-xxxxx

# 3. Redémarrer
./start.sh

# C'est tout ! Le code reste identique.
```

## ✅ Checklist Gemini

- [ ] Clé API créée sur https://aistudio.google.com/app/apikey
- [ ] `.env` configuré avec `AI_PROVIDER=gemini`
- [ ] `GOOGLE_API_KEY` renseignée
- [ ] Test en console: `python engine_akinator_multi_ai.py --provider gemini`
- [ ] Test API: `curl http://localhost:8000/health`
- [ ] Quota restant > 0

## 🎉 Conclusion

**Gemini 2.0 Flash est parfait pour:**
- ✅ Débuter sans frais
- ✅ Prototypes et développement
- ✅ Applications avec trafic modéré (<150 parties/jour)
- ✅ Tester l'IA sans engagement

**Passez à Claude si:**
- Vous voulez la meilleure qualité possible
- Vous dépassez 1500 requêtes/jour
- Vous monétisez votre application

---

**Support Gemini:**
- Documentation: https://ai.google.dev/docs
- API Explorer: https://aistudio.google.com/
- Community: https://discuss.ai.google.dev/

**🚀 Bon jeu avec Gemini !**
