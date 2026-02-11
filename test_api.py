#!/usr/bin/env python3
"""
Script de test pour l'API Akinator IA
Valide le bon fonctionnement de toutes les routes
"""

import requests
import json
import time
from typing import Dict, Any


class AkinatorAPITester:
    """Classe pour tester l'API Akinator."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session_id = None
        
    def test_health(self) -> bool:
        """Test de l'endpoint health."""
        print("🔍 Test: Health Check")
        try:
            response = requests.get(f"{self.base_url}/health")
            data = response.json()
            
            print(f"   Status: {data.get('status')}")
            print(f"   API Key configurée: {data.get('api_key_configured')}")
            
            if data.get('status') == 'ok':
                print("   ✅ Health check OK\n")
                return True
            else:
                print(f"   ⚠️ Warning: {data.get('message')}\n")
                return False
                
        except Exception as e:
            print(f"   ❌ Erreur: {e}\n")
            return False
    
    def test_start_game(self) -> bool:
        """Test du démarrage d'une partie."""
        print("🔍 Test: Démarrage du jeu")
        try:
            response = requests.post(f"{self.base_url}/api/akinator/start")
            
            if response.status_code != 200:
                print(f"   ❌ Erreur HTTP {response.status_code}")
                print(f"   {response.text}\n")
                return False
            
            data = response.json()
            self.session_id = data.get('session_id')
            
            print(f"   Session ID: {self.session_id[:8]}...")
            print(f"   Total films: {data.get('total_movies')}")
            print(f"   Action: {data.get('action')}")
            print(f"   Question: {data.get('content')}")
            print("   ✅ Démarrage OK\n")
            return True
            
        except Exception as e:
            print(f"   ❌ Erreur: {e}\n")
            return False
    
    def test_answer_question(self, answer: str = "y") -> Dict[str, Any]:
        """Test de réponse à une question."""
        print(f"🔍 Test: Réponse à la question (answer='{answer}')")
        
        if not self.session_id:
            print("   ❌ Pas de session active\n")
            return {}
        
        try:
            response = requests.post(
                f"{self.base_url}/api/akinator/answer",
                json={
                    "session_id": self.session_id,
                    "answer": answer
                }
            )
            
            if response.status_code != 200:
                print(f"   ❌ Erreur HTTP {response.status_code}\n")
                return {}
            
            data = response.json()
            
            print(f"   Action: {data.get('action')}")
            print(f"   Question #{data.get('question_number')}: {data.get('content')}")
            print("   ✅ Réponse OK\n")
            return data
            
        except Exception as e:
            print(f"   ❌ Erreur: {e}\n")
            return {}
    
    def test_confirm_guess(self, is_correct: bool = False) -> Dict[str, Any]:
        """Test de confirmation d'une proposition."""
        print(f"🔍 Test: Confirmation (is_correct={is_correct})")
        
        if not self.session_id:
            print("   ❌ Pas de session active\n")
            return {}
        
        try:
            response = requests.post(
                f"{self.base_url}/api/akinator/confirm",
                json={
                    "session_id": self.session_id,
                    "is_correct": is_correct
                }
            )
            
            if response.status_code != 200:
                print(f"   ❌ Erreur HTTP {response.status_code}\n")
                return {}
            
            data = response.json()
            
            print(f"   Résultat: {data.get('result')}")
            if data.get('result') == 'found':
                print(f"   Questions posées: {data.get('questions_asked')}")
            else:
                print(f"   Prochaine question: {data.get('content')}")
            print("   ✅ Confirmation OK\n")
            return data
            
        except Exception as e:
            print(f"   ❌ Erreur: {e}\n")
            return {}
    
    def test_list_sessions(self) -> bool:
        """Test de listage des sessions."""
        print("🔍 Test: Liste des sessions")
        try:
            response = requests.get(f"{self.base_url}/api/akinator/sessions")
            data = response.json()
            
            print(f"   Total sessions: {data.get('total_sessions')}")
            print("   ✅ Liste OK\n")
            return True
            
        except Exception as e:
            print(f"   ❌ Erreur: {e}\n")
            return False
    
    def test_delete_session(self) -> bool:
        """Test de suppression d'une session."""
        print("🔍 Test: Suppression de session")
        
        if not self.session_id:
            print("   ⚠️ Pas de session à supprimer\n")
            return True
        
        try:
            response = requests.delete(
                f"{self.base_url}/api/akinator/sessions/{self.session_id}"
            )
            
            if response.status_code != 200:
                print(f"   ❌ Erreur HTTP {response.status_code}\n")
                return False
            
            print(f"   ✅ Session supprimée\n")
            self.session_id = None
            return True
            
        except Exception as e:
            print(f"   ❌ Erreur: {e}\n")
            return False
    
    def run_full_test_suite(self):
        """Lance tous les tests."""
        print("=" * 60)
        print("🧪 SUITE DE TESTS AKINATOR API")
        print("=" * 60)
        print()
        
        results = []
        
        # 1. Health check
        results.append(("Health Check", self.test_health()))
        time.sleep(0.5)
        
        # 2. Démarrage
        results.append(("Start Game", self.test_start_game()))
        time.sleep(0.5)
        
        # 3. Plusieurs réponses
        for i, answer in enumerate(['y', 'n', '?'], 1):
            data = self.test_answer_question(answer)
            results.append((f"Answer {i} ({answer})", bool(data)))
            time.sleep(0.5)
            
            # Si proposition, tester la confirmation
            if data.get('action') == 'guess':
                confirm_data = self.test_confirm_guess(is_correct=False)
                results.append(("Confirm Guess", bool(confirm_data)))
                time.sleep(0.5)
                break
        
        # 4. Liste des sessions
        results.append(("List Sessions", self.test_list_sessions()))
        time.sleep(0.5)
        
        # 5. Suppression
        results.append(("Delete Session", self.test_delete_session()))
        
        # Résumé
        print()
        print("=" * 60)
        print("📊 RÉSUMÉ DES TESTS")
        print("=" * 60)
        
        for test_name, success in results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"{status} - {test_name}")
        
        total = len(results)
        passed = sum(1 for _, s in results if s)
        
        print()
        print(f"Total: {passed}/{total} tests réussis")
        print("=" * 60)
        
        return passed == total


def test_complete_game_flow():
    """Test d'un flux de jeu complet."""
    print()
    print("=" * 60)
    print("🎮 TEST D'UN JEU COMPLET")
    print("=" * 60)
    print()
    
    base_url = "http://localhost:8000"
    
    try:
        # Démarrer
        print("1️⃣ Démarrage du jeu...")
        response = requests.post(f"{base_url}/api/akinator/start")
        data = response.json()
        session_id = data['session_id']
        print(f"   ✅ Session: {session_id[:8]}...")
        print(f"   Question: {data['content']}\n")
        
        # Jouer plusieurs tours
        max_questions = 10
        for i in range(max_questions):
            # Réponse aléatoire
            import random
            answer = random.choice(['y', 'n', '?'])
            
            print(f"2️⃣ Réponse #{i+1}: {answer}")
            response = requests.post(
                f"{base_url}/api/akinator/answer",
                json={"session_id": session_id, "answer": answer}
            )
            data = response.json()
            
            if data['action'] == 'guess':
                print(f"   💡 Proposition: {data['content']}")
                
                # Confirmer (incorrecte pour continuer)
                print("3️⃣ Confirmation: Non")
                response = requests.post(
                    f"{base_url}/api/akinator/confirm",
                    json={"session_id": session_id, "is_correct": False}
                )
                data = response.json()
                
                if data['result'] == 'continue':
                    print(f"   ❓ Nouvelle question: {data['content']}\n")
                else:
                    print("   ✅ Jeu terminé\n")
                    break
            else:
                print(f"   ❓ Question: {data['content']}\n")
            
            time.sleep(0.5)
        
        # Nettoyer
        print("4️⃣ Nettoyage...")
        requests.delete(f"{base_url}/api/akinator/sessions/{session_id}")
        print("   ✅ Session supprimée")
        
        print()
        print("=" * 60)
        print("✅ TEST COMPLET RÉUSSI")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Point d'entrée principal."""
    import sys
    
    # Vérifier que le serveur est accessible
    try:
        response = requests.get("http://localhost:8000/health", timeout=2)
        if response.status_code != 200:
            print("❌ Le serveur n'est pas accessible sur http://localhost:8000")
            print("   Assurez-vous que le serveur est démarré avec:")
            print("   python api_server.py")
            return 1
    except requests.exceptions.RequestException:
        print("❌ Le serveur n'est pas accessible sur http://localhost:8000")
        print("   Assurez-vous que le serveur est démarré avec:")
        print("   python api_server.py")
        return 1
    
    # Lancer les tests
    tester = AkinatorAPITester()
    success = tester.run_full_test_suite()
    
    if len(sys.argv) > 1 and sys.argv[1] == "--full":
        test_complete_game_flow()
    
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
