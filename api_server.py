#!/usr/bin/env python3
"""
Serveur FastAPI pour Akinator IA
Compatible avec le frontend existant
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Optional
import uuid
from datetime import datetime, timedelta
import os

# Import du moteur Akinator IA Multi-Provider
try:
    from engine_akinator_multi_ai import AkinatorSession, AI_PROVIDER, ANTHROPIC_API_KEY, GOOGLE_API_KEY, OPENAI_API_KEY
except ImportError:
    # Fallback sur la version Claude-only
    from engine_akinator_ai import AkinatorSession
    AI_PROVIDER = "claude"
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    GOOGLE_API_KEY = ""
    OPENAI_API_KEY = ""

# Configuration
app = FastAPI(
    title="Akinator Film API",
    description="API pour jouer à Akinator avec des films, propulsée par l'IA Claude",
    version="2.0.0"
)

# CORS pour permettre les requêtes depuis le frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En production, spécifier les domaines autorisés
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Stockage en mémoire des sessions
# En production, utiliser Redis ou une base de données
sessions: Dict[str, Dict] = {}

# Configuration
DB_PATH = os.getenv("MOVIES_DB_PATH", "movies.db")
SESSION_TIMEOUT = timedelta(hours=1)


# ===========================
# MODÈLES PYDANTIC
# ===========================

class StartGameResponse(BaseModel):
    session_id: str
    status: str
    action: str
    content: str
    question_number: int
    total_movies: int


class AnswerRequest(BaseModel):
    session_id: str
    answer: str  # "y", "n", ou "?"


class AnswerResponse(BaseModel):
    status: str
    action: str
    content: str
    question_number: int


class ConfirmRequest(BaseModel):
    session_id: str
    is_correct: bool


class ConfirmResponse(BaseModel):
    status: str
    result: str
    questions_asked: Optional[int] = None
    action: Optional[str] = None
    content: Optional[str] = None
    question_number: Optional[int] = None


class SessionInfo(BaseModel):
    session_id: str
    question_count: int
    started_at: str
    is_active: bool


# ===========================
# HELPERS
# ===========================

def clean_expired_sessions():
    """Nettoie les sessions expirées."""
    now = datetime.now()
    expired = [
        sid for sid, data in sessions.items()
        if now - data["created_at"] > SESSION_TIMEOUT
    ]
    for sid in expired:
        del sessions[sid]


def get_session(session_id: str) -> Dict:
    """Récupère une session ou lève une erreur."""
    clean_expired_sessions()
    
    if session_id not in sessions:
        raise HTTPException(
            status_code=404,
            detail="Session non trouvée ou expirée"
        )
    
    return sessions[session_id]


# ===========================
# ROUTES API
# ===========================

@app.get("/")
async def root():
    """Page d'accueil de l'API."""
    return {
        "name": "Akinator Film API",
        "version": "2.0.0",
        "description": "Devinez des films avec l'IA Claude",
        "endpoints": {
            "start": "/api/akinator/start",
            "answer": "/api/akinator/answer",
            "confirm": "/api/akinator/confirm",
            "sessions": "/api/akinator/sessions"
        },
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Vérifie que l'API est opérationnelle."""
    # Vérifier quelle clé API est configurée
    api_keys_configured = {
        "claude": bool(ANTHROPIC_API_KEY),
        "gemini": bool(GOOGLE_API_KEY),
        "openai": bool(OPENAI_API_KEY)
    }
    
    current_provider_configured = api_keys_configured.get(AI_PROVIDER, False)
    
    if not current_provider_configured:
        return {
            "status": "warning",
            "message": f"API opérationnelle mais clé {AI_PROVIDER.upper()} non configurée",
            "current_provider": AI_PROVIDER,
            "api_keys_configured": api_keys_configured
        }
    
    return {
        "status": "ok",
        "message": "API opérationnelle",
        "active_sessions": len(sessions),
        "current_provider": AI_PROVIDER,
        "api_keys_configured": api_keys_configured
    }


@app.post("/api/akinator/start", response_model=StartGameResponse)
async def start_game():
    """
    Démarre une nouvelle partie d'Akinator.
    
    Returns:
        - session_id: Identifiant unique de la session
        - action: Type d'action ("question")
        - content: Texte de la première question
        - question_number: Numéro de la question (1)
        - total_movies: Nombre de films dans la base
    """
    # Vérifier que la clé API du provider actif est configurée
    if AI_PROVIDER == "claude" and not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="Clé API Anthropic non configurée.")
    elif AI_PROVIDER == "gemini" and not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="Clé API Google non configurée.")
    elif AI_PROVIDER == "openai" and not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Clé API OpenAI non configurée.")
    
    # Créer une nouvelle session
    session_id = str(uuid.uuid4())
    
    try:
        # Initialiser le moteur Akinator avec le provider
        akinator = AkinatorSession(db_path=DB_PATH, provider=AI_PROVIDER)
        result = akinator.start()
        
        # Stocker la session
        sessions[session_id] = {
            "akinator": akinator,
            "created_at": datetime.now(),
            "last_activity": datetime.now(),
            "question_count": result["question_number"]
        }
        
        return StartGameResponse(
            session_id=session_id,
            status=result["status"],
            action=result["action"],
            content=result["content"],
            question_number=result["question_number"],
            total_movies=result["total_movies"]
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors du démarrage du jeu: {str(e)}"
        )


@app.post("/api/akinator/answer", response_model=AnswerResponse)
async def answer_question(request: AnswerRequest):
    """
    Envoie une réponse à la question actuelle.
    
    Args:
        session_id: Identifiant de la session
        answer: Réponse ("y" pour oui, "n" pour non, "?" pour je ne sais pas)
    
    Returns:
        - action: "question" ou "guess"
        - content: Prochaine question ou proposition de film
        - question_number: Numéro de la question
    """
    session_data = get_session(request.session_id)
    akinator = session_data["akinator"]
    
    try:
        result = akinator.answer(request.answer)
        
        # Mettre à jour la session
        session_data["last_activity"] = datetime.now()
        session_data["question_count"] = result["question_number"]
        
        return AnswerResponse(
            status=result["status"],
            action=result["action"],
            content=result["content"],
            question_number=result["question_number"]
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors du traitement de la réponse: {str(e)}"
        )


@app.post("/api/akinator/confirm", response_model=ConfirmResponse)
async def confirm_guess(request: ConfirmRequest):
    """
    Confirme si la proposition de l'IA était correcte.
    
    Args:
        session_id: Identifiant de la session
        is_correct: True si la proposition était correcte, False sinon
    
    Returns:
        - result: "found" si trouvé, "continue" pour continuer
        - questions_asked: Nombre de questions posées (si trouvé)
        - action/content: Prochaine question (si continue)
    """
    session_data = get_session(request.session_id)
    akinator = session_data["akinator"]
    
    try:
        result = akinator.confirm(request.is_correct)
        
        # Si trouvé, supprimer la session
        if result.get("result") == "found":
            del sessions[request.session_id]
        else:
            session_data["last_activity"] = datetime.now()
        
        return ConfirmResponse(**result)
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la confirmation: {str(e)}"
        )


@app.get("/api/akinator/sessions")
async def list_sessions():
    """
    Liste toutes les sessions actives (pour debug/admin).
    """
    clean_expired_sessions()
    
    session_list = []
    for sid, data in sessions.items():
        session_list.append(SessionInfo(
            session_id=sid,
            question_count=data["question_count"],
            started_at=data["created_at"].isoformat(),
            is_active=True
        ))
    
    return {
        "total_sessions": len(session_list),
        "sessions": session_list
    }


@app.delete("/api/akinator/sessions/{session_id}")
async def delete_session(session_id: str):
    """
    Supprime une session spécifique.
    """
    if session_id not in sessions:
        raise HTTPException(
            status_code=404,
            detail="Session non trouvée"
        )
    
    del sessions[session_id]
    
    return {
        "status": "ok",
        "message": f"Session {session_id} supprimée"
    }


@app.get("/api/stats")
async def get_stats():
    """
    Statistiques globales du serveur.
    """
    clean_expired_sessions()
    
    total_questions = sum(s["question_count"] for s in sessions.values())
    avg_questions = total_questions / len(sessions) if sessions else 0
    
    return {
        "active_sessions": len(sessions),
        "total_questions_asked": total_questions,
        "average_questions_per_session": round(avg_questions, 2),
        "api_key_configured": bool(ANTHROPIC_API_KEY)
    }


# ===========================
# STARTUP/SHUTDOWN
# ===========================

@app.on_event("startup")
async def startup_event():
    """Événement au démarrage du serveur."""
    print("🚀 Démarrage du serveur Akinator IA Multi-Provider")
    print(f"📊 Base de données: {DB_PATH}")
    print(f"🤖 Provider actif: {AI_PROVIDER.upper()}")
    print(f"🔑 Clés configurées:")
    print(f"   - Claude: {bool(ANTHROPIC_API_KEY)}")
    print(f"   - Gemini: {bool(GOOGLE_API_KEY)}")
    print(f"   - OpenAI: {bool(OPENAI_API_KEY)}")
    
    if AI_PROVIDER == "claude" and not ANTHROPIC_API_KEY:
        print("⚠️  ATTENTION: Provider Claude sélectionné mais clé non configurée!")
    elif AI_PROVIDER == "gemini" and not GOOGLE_API_KEY:
        print("⚠️  ATTENTION: Provider Gemini sélectionné mais clé non configurée!")
    elif AI_PROVIDER == "openai" and not OPENAI_API_KEY:
        print("⚠️  ATTENTION: Provider OpenAI sélectionné mais clé non configurée!")


@app.on_event("shutdown")
async def shutdown_event():
    """Événement à l'arrêt du serveur."""
    print(f"👋 Arrêt du serveur - {len(sessions)} sessions actives supprimées")
    sessions.clear()


# ===========================
# POINT D'ENTRÉE
# ===========================

if __name__ == "__main__":
    import uvicorn
    
    # Configuration pour le développement
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
