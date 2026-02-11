#!/bin/bash

# Script de démarrage pour Akinator IA Multi-Provider

echo "🎬 AKINATOR IA - Démarrage Multi-Provider"
echo "=========================================="
echo ""

# Vérifier Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 n'est pas installé"
    exit 1
fi

# Vérifier le fichier .env
if [ ! -f .env ]; then
    echo "⚠️  Fichier .env non trouvé"
    echo "   Création depuis env.example..."
    
    if [ -f env.example ]; then
        cp env.example .env
        echo "   ✅ Fichier .env créé"
    else
        echo "   ❌ Fichier env.example non trouvé"
        echo "   Créez un fichier .env manuellement"
        exit 1
    fi
    
    echo ""
    echo "   ⚠️  IMPORTANT: Éditez .env et configurez votre clé API"
    echo "   - Pour Gemini (gratuit): https://aistudio.google.com/app/apikey"
    echo "   - Pour Claude: https://console.anthropic.com/"
    echo "   - Pour OpenAI: https://platform.openai.com/api-keys"
    echo ""
    read -p "Appuyez sur Entrée quand vous avez configuré votre clé API..."
fi

# Charger les variables d'environnement
export $(cat .env | grep -v '^#' | grep -v '^$' | xargs)

# Déterminer quel provider est utilisé
AI_PROVIDER=${AI_PROVIDER:-gemini}

echo "🤖 Provider sélectionné: $AI_PROVIDER"
echo ""

# Vérifier la clé API appropriée
if [ "$AI_PROVIDER" = "gemini" ]; then
    if [ -z "$GOOGLE_API_KEY" ] || [ "$GOOGLE_API_KEY" = "votre_cle_google_ici" ]; then
        echo "❌ Clé API Google non configurée dans .env"
        echo "   1. Obtenez une clé gratuite sur: https://aistudio.google.com/app/apikey"
        echo "   2. Éditez le fichier .env"
        echo "   3. Configurez: GOOGLE_API_KEY=AIzaSy..."
        exit 1
    fi
    echo "✅ Clé API Google configurée"
    
elif [ "$AI_PROVIDER" = "claude" ]; then
    if [ -z "$ANTHROPIC_API_KEY" ] || [ "$ANTHROPIC_API_KEY" = "sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" ]; then
        echo "❌ Clé API Anthropic non configurée dans .env"
        echo "   1. Obtenez une clé sur: https://console.anthropic.com/"
        echo "   2. Éditez le fichier .env"
        echo "   3. Configurez: ANTHROPIC_API_KEY=sk-ant-..."
        exit 1
    fi
    echo "✅ Clé API Anthropic configurée"
    
elif [ "$AI_PROVIDER" = "openai" ]; then
    if [ -z "$OPENAI_API_KEY" ] || [ "$OPENAI_API_KEY" = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" ]; then
        echo "❌ Clé API OpenAI non configurée dans .env"
        echo "   1. Obtenez une clé sur: https://platform.openai.com/api-keys"
        echo "   2. Éditez le fichier .env"
        echo "   3. Configurez: OPENAI_API_KEY=sk-..."
        exit 1
    fi
    echo "✅ Clé API OpenAI configurée"
    
else
    echo "❌ Provider inconnu: $AI_PROVIDER"
    echo "   Options valides: gemini, claude, openai"
    exit 1
fi

# Vérifier la base de données
MOVIES_DB_PATH=${MOVIES_DB_PATH:-./movies.db}
if [ ! -f "$MOVIES_DB_PATH" ]; then
    echo "⚠️  Base de données non trouvée: $MOVIES_DB_PATH"
    echo "   Assurez-vous que le fichier movies.db existe"
    echo ""
    read -p "Continuer quand même ? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Installer les dépendances
echo ""
echo "📦 Vérification des dépendances..."
pip install -q -r requirements.txt --break-system-packages 2>/dev/null || pip install -q -r requirements.txt 2>/dev/null

# Configuration du serveur
API_HOST=${API_HOST:-0.0.0.0}
API_PORT=${API_PORT:-8000}

# Démarrer le serveur
echo ""
echo "🚀 Démarrage du serveur sur http://$API_HOST:$API_PORT"
echo ""
echo "   🤖 Provider IA: $AI_PROVIDER"
echo "   📊 Base de données: $MOVIES_DB_PATH"
echo "   📖 API Documentation: http://localhost:$API_PORT/docs"
echo "   💚 Health Check: http://localhost:$API_PORT/health"
echo ""
echo "Appuyez sur Ctrl+C pour arrêter le serveur"
echo "=========================================="
echo ""

# Lancer uvicorn
python3 -m uvicorn api_server:app --host $API_HOST --port $API_PORT --reload
