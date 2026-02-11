# 🎬 Backend Netfilm - Version IA

## ✅ Modifications apportées

### Fichiers MODIFIÉS :
- **app_akinator.py** - Utilise maintenant l'IA au lieu des probabilités

### Fichiers AJOUTÉS :
- **engines/engine_akinator_multi_ai.py** - Moteur IA (Gemini/Claude/OpenAI)
- **.env** - Configuration des clés API

### Fichiers INCHANGÉS :
- ✅ app.py
- ✅ app_blindtest.py
- ✅ app_moviegrid.py
- ✅ run_all.py
- ✅ requirements.txt (déjà complet)
- ✅ engines/engine_akinator.py (ancien moteur conservé)
- ✅ movies.db

## 🚀 Utilisation

### 1. Configuration (Important !)

Éditez le fichier `.env` et configurez votre clé API :

```bash
# Pour utiliser Gemini (GRATUIT - recommandé)
AI_PROVIDER=gemini
GOOGLE_API_KEY=votre_clé_ici

# Ou pour utiliser Claude
AI_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-xxxxx

# Ou pour utiliser OpenAI
AI_PROVIDER=openai
OPENAI_API_KEY=sk-xxxxx
```

### 2. Obtenir une clé API gratuite Gemini

1. Allez sur : https://aistudio.google.com/app/apikey
2. Connectez-vous avec votre compte Google
3. Cliquez sur "Create API key"
4. Copiez la clé (commence par `AIza...`)
5. Collez-la dans `.env`

### 3. Lancer le backend

```bash
# Comme d'habitude !
python backend/run_all.py
```

Ça lancera :
- Port 5001 : Akinator avec IA 🤖
- Port 5002 : BlindTest
- Port 5003 : MovieGrid

## 🔍 Tester que ça marche

```bash
# Vérifier le statut
curl http://localhost:5001/

# Devrait afficher:
# {"status":"ok","service":"Akinator API (IA)","ai_provider":"gemini",...}
```

## 🎯 Différences avec l'ancien système

### Avant (probabilités) :
- Questions prédéfinies
- Logique basée sur des règles

### Maintenant (IA) :
- Questions générées dynamiquement par l'IA
- Compréhension contextuelle
- Questions plus naturelles

## 🔄 Revenir à l'ancien système

Si vous voulez revenir à l'ancien moteur :

```bash
# 1. Récupérez l'ancien app_akinator.py depuis votre backup
# 2. Remplacez le fichier actuel
# 3. Relancez run_all.py
```

L'ancien moteur (`engines/engine_akinator.py`) est toujours présent !

## 🐛 Dépannage

### Erreur : "Clé API non configurée"
→ Éditez `.env` et configurez la bonne clé API

### Erreur : "Module engine_akinator_multi_ai not found"
→ Vérifiez que le fichier est bien dans `backend/engines/`

### Erreur : "Provider inconnu"
→ Dans `.env`, AI_PROVIDER doit être : gemini, claude, ou openai

### Le serveur ne démarre pas
→ Vérifiez que toutes les dépendances sont installées :
```bash
pip install -r requirements.txt --break-system-packages
```

## 📊 Performances

Avec Gemini (gratuit) :
- ~2-3 secondes par question
- 1500 requêtes/jour gratuit
- Qualité excellente

## 💡 Support

En cas de problème, vérifiez :
1. `.env` est bien configuré
2. La clé API est valide
3. Les dépendances sont installées
4. movies.db est accessible

---

**Version** : 2.0 (IA)
**Compatibilité** : Frontend inchangé ✅
