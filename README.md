# 🎬 AKINATOR IA - Multi-Provider

## 🎯 Choisissez votre IA

Ce package supporte **3 IA différentes** :

| IA | Prix | Qualité | Vitesse | Recommandé pour |
|----|------|---------|---------|-----------------|
| 🟢 **Gemini** | GRATUIT | ⭐⭐⭐⭐ | ⚡⚡⚡ | Débuter, tester, développer |
| 🔵 **Claude** | Payant | ⭐⭐⭐⭐⭐ | ⚡⚡ | Production, meilleure qualité |
| 🟠 **OpenAI** | Payant | ⭐⭐⭐⭐ | ⚡⚡⚡ | Alternative à Claude |

## 🆓 RECOMMANDATION : Commencez avec Gemini

**Gemini 2.0 Flash** est parfait pour débuter :
- ✅ **100% gratuit** (1500 requêtes/jour)
- ✅ Pas de carte bancaire
- ✅ Excellente qualité
- ✅ Setup en 2 minutes

👉 **Lisez GUIDE_GEMINI.md pour commencer avec Gemini !**

## 📦 Installation rapide

### Avec Gemini (GRATUIT - Recommandé)

```bash
# 1. Obtenir une clé gratuite
# Allez sur: https://aistudio.google.com/app/apikey

# 2. Configuration
cp env.example .env
nano .env
# Configurez: AI_PROVIDER=gemini et GOOGLE_API_KEY=...

# 3. Lancement
pip install -r requirements.txt --break-system-packages
python engine_akinator_multi_ai.py --provider gemini
```

### Avec Claude (Payant)

```bash
# 1. Obtenir une clé
# https://console.anthropic.com/

# 2. Configuration
AI_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-xxxxx

# 3. Lancement
python engine_akinator_multi_ai.py --provider claude
```

### Avec OpenAI (Payant)

```bash
# 1. Obtenir une clé
# https://platform.openai.com/api-keys

# 2. Configuration
AI_PROVIDER=openai
OPENAI_API_KEY=sk-xxxxx

# 3. Lancement
python engine_akinator_multi_ai.py --provider openai
```

## 📁 Fichiers du package

### Fichiers principaux
- **engine_akinator_multi_ai.py** - Moteur avec support multi-IA ⭐ NOUVEAU
- **engine_akinator_ai.py** - Version Claude-only (ancienne)
- **api_server.py** - Serveur API REST (mis à jour pour multi-IA)

### Utilitaires
- **akinator_client.js** - Client JavaScript
- **test_api.py** - Suite de tests
- **start.sh** - Script de démarrage

### Configuration
- **env.example** - Fichier de configuration type
- **requirements.txt** - Dépendances Python

### Documentation
- **GUIDE_GEMINI.md** - Guide complet Gemini (gratuit) ⭐ NOUVEAU
- **INSTALLATION.md** - Installation rapide
- **README_AI.md** - Documentation technique détaillée
- **SOMMAIRE.md** - Vue d'ensemble

## 🔄 Changer d'IA en 1 ligne

Dans le fichier `.env` :

```bash
# Utiliser Gemini (gratuit)
AI_PROVIDER=gemini

# Utiliser Claude (meilleure qualité)
AI_PROVIDER=claude

# Utiliser OpenAI
AI_PROVIDER=openai
```

Pas de changement de code nécessaire !

## 💰 Comparaison des coûts

Pour **1000 parties** :

| IA | Coût total | Coût/partie |
|----|-----------|-------------|
| Gemini | **0€** | 0€ |
| Claude | ~1€ | ~0.001€ |
| OpenAI | ~0.50€ | ~0.0005€ |

## 🚀 Démarrage en 30 secondes

```bash
# Décompresser
unzip akinator_multi_ia.zip
cd akinator_multi_ia/

# Configuration Gemini (gratuit)
cp env.example .env
echo "AI_PROVIDER=gemini" >> .env
echo "GOOGLE_API_KEY=VOTRE_CLE_ICI" >> .env

# Installation
pip install requests --break-system-packages

# Test
python engine_akinator_multi_ai.py --provider gemini
```

## 📚 Documentation

1. **Débuter avec Gemini (gratuit)** → GUIDE_GEMINI.md
2. **Installation complète** → INSTALLATION.md
3. **Documentation technique** → README_AI.md
4. **Vue d'ensemble** → SOMMAIRE.md

## 🎮 Exemples d'utilisation

### Console (test rapide)

```bash
# Avec Gemini
python engine_akinator_multi_ai.py --provider gemini

# Avec Claude
python engine_akinator_multi_ai.py --provider claude

# Avec OpenAI
python engine_akinator_multi_ai.py --provider openai
```

### Serveur API (production)

```bash
# Démarrer le serveur
./start.sh

# L'IA utilisée est celle configurée dans .env
# L'API fonctionne de la même manière quelle que soit l'IA !
```

### Frontend JavaScript

```javascript
// Le client ne change pas, quelle que soit l'IA backend !
const client = new AkinatorClient('http://localhost:8000');
const result = await client.startGame();
```

## ✅ Compatibilité Frontend

**Aucun changement nécessaire dans votre frontend !**

L'API expose les mêmes endpoints, peu importe l'IA utilisée :
- `POST /api/akinator/start`
- `POST /api/akinator/answer`
- `POST /api/akinator/confirm`

Vous pouvez changer d'IA côté backend sans toucher au frontend.

## 🔧 Résolution de problèmes

### "Provider 'X' non supporté"
→ Vérifiez `AI_PROVIDER` dans .env (doit être: gemini, claude, ou openai)

### "Clé API non configurée"
→ Vérifiez que vous avez bien configuré la clé pour le provider choisi

### "Module X not found"
→ `pip install -r requirements.txt --break-system-packages`

## 📞 Support

- **Gemini** : https://aistudio.google.com/
- **Claude** : https://console.anthropic.com/
- **OpenAI** : https://platform.openai.com/

---

## 🎯 Notre recommandation

**Pour débuter :**
1. Utilisez **Gemini** (gratuit, excellent)
2. Lisez **GUIDE_GEMINI.md**
3. Testez avec `python engine_akinator_multi_ai.py --provider gemini`

**Pour la production :**
1. Testez d'abord avec Gemini
2. Si vous voulez la meilleure qualité, passez à **Claude**
3. Changez juste `AI_PROVIDER=claude` dans .env

---

**Version** : 2.0.0 (Multi-Provider)  
**Date** : Février 2025  
**Support IA** : Gemini ✅ | Claude ✅ | OpenAI ✅

🎬 **Bon jeu avec l'IA de votre choix !**
