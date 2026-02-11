/**
 * Client JavaScript pour Akinator IA
 * Compatible avec le frontend existant
 */

class AkinatorClient {
  constructor(apiUrl = 'http://localhost:8000') {
    this.apiUrl = apiUrl;
    this.sessionId = null;
    this.questionNumber = 0;
  }

  /**
   * Démarre une nouvelle partie
   * @returns {Promise<Object>} Première question
   */
  async startGame() {
    try {
      const response = await fetch(`${this.apiUrl}/api/akinator/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      
      this.sessionId = data.session_id;
      this.questionNumber = data.question_number;

      return {
        question: data.content,
        questionNumber: data.question_number,
        totalMovies: data.total_movies
      };

    } catch (error) {
      console.error('Erreur lors du démarrage:', error);
      throw error;
    }
  }

  /**
   * Envoie une réponse à la question courante
   * @param {string} answer - "y", "n", ou "?"
   * @returns {Promise<Object>} Prochaine question ou proposition
   */
  async answerQuestion(answer) {
    if (!this.sessionId) {
      throw new Error('Aucune session active. Appelez startGame() d\'abord.');
    }

    try {
      const response = await fetch(`${this.apiUrl}/api/akinator/answer`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          session_id: this.sessionId,
          answer: answer
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      this.questionNumber = data.question_number;

      return {
        action: data.action,  // "question" ou "guess"
        content: data.content,
        questionNumber: data.question_number,
        isGuess: data.action === 'guess'
      };

    } catch (error) {
      console.error('Erreur lors de la réponse:', error);
      throw error;
    }
  }

  /**
   * Confirme si la proposition était correcte
   * @param {boolean} isCorrect - True si correct, False sinon
   * @returns {Promise<Object>} Résultat ou prochaine question
   */
  async confirmGuess(isCorrect) {
    if (!this.sessionId) {
      throw new Error('Aucune session active.');
    }

    try {
      const response = await fetch(`${this.apiUrl}/api/akinator/confirm`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          session_id: this.sessionId,
          is_correct: isCorrect
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();

      if (data.result === 'found') {
        // Partie terminée
        const result = {
          found: true,
          questionsAsked: data.questions_asked
        };
        
        // Réinitialiser la session
        this.sessionId = null;
        this.questionNumber = 0;
        
        return result;
      } else {
        // Continuer le jeu
        return {
          found: false,
          action: data.action,
          content: data.content,
          questionNumber: data.question_number
        };
      }

    } catch (error) {
      console.error('Erreur lors de la confirmation:', error);
      throw error;
    }
  }

  /**
   * Réinitialise le client (abandonne la partie en cours)
   */
  reset() {
    this.sessionId = null;
    this.questionNumber = 0;
  }
}


// ===========================
// EXEMPLE D'UTILISATION
// ===========================

async function playAkinator() {
  const client = new AkinatorClient('http://localhost:8000');

  try {
    // 1. Démarrer le jeu
    console.log('🎬 Démarrage d\'Akinator Film...\n');
    const start = await client.startGame();
    console.log(`📊 Base de données: ${start.totalMovies} films`);
    console.log(`❓ Question ${start.questionNumber}: ${start.question}\n`);

    // 2. Répondre aux questions (exemple)
    let response = await client.answerQuestion('y');  // Oui
    
    while (response.action === 'question') {
      console.log(`❓ Question ${response.questionNumber}: ${response.content}`);
      
      // Simuler une réponse (en vrai, demander à l'utilisateur)
      const answers = ['y', 'n', '?'];
      const randomAnswer = answers[Math.floor(Math.random() * answers.length)];
      
      console.log(`   Réponse: ${randomAnswer === 'y' ? 'Oui' : randomAnswer === 'n' ? 'Non' : 'Je ne sais pas'}\n`);
      
      response = await client.answerQuestion(randomAnswer);
    }

    // 3. L'IA propose un film
    if (response.isGuess) {
      console.log(`💡 JE PENSE QUE C'EST: ${response.content}`);
      console.log('   Est-ce correct ?\n');

      // Simuler la confirmation (en vrai, demander à l'utilisateur)
      const isCorrect = Math.random() > 0.5;
      const result = await client.confirmGuess(isCorrect);

      if (result.found) {
        console.log(`✅ Trouvé en ${result.questionsAsked} questions !`);
      } else {
        console.log('❌ Dommage, je continue...');
        console.log(`❓ Question ${result.questionNumber}: ${result.content}`);
      }
    }

  } catch (error) {
    console.error('❌ Erreur:', error.message);
  }
}


// ===========================
// INTÉGRATION REACT
// ===========================

/**
 * Hook React pour utiliser Akinator
 */
function useAkinator() {
  const [client] = React.useState(() => new AkinatorClient());
  const [currentQuestion, setCurrentQuestion] = React.useState(null);
  const [questionNumber, setQuestionNumber] = React.useState(0);
  const [isGuessing, setIsGuessing] = React.useState(false);
  const [isLoading, setIsLoading] = React.useState(false);
  const [error, setError] = React.useState(null);

  const startGame = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await client.startGame();
      setCurrentQuestion(result.question);
      setQuestionNumber(result.questionNumber);
      setIsGuessing(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const answer = async (response) => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await client.answerQuestion(response);
      setCurrentQuestion(result.content);
      setQuestionNumber(result.questionNumber);
      setIsGuessing(result.isGuess);
      return result;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  const confirm = async (isCorrect) => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await client.confirmGuess(isCorrect);
      if (!result.found) {
        setCurrentQuestion(result.content);
        setQuestionNumber(result.questionNumber);
        setIsGuessing(false);
      }
      return result;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  return {
    currentQuestion,
    questionNumber,
    isGuessing,
    isLoading,
    error,
    startGame,
    answer,
    confirm
  };
}


// ===========================
// COMPOSANT REACT EXEMPLE
// ===========================

function AkinatorGame() {
  const {
    currentQuestion,
    questionNumber,
    isGuessing,
    isLoading,
    error,
    startGame,
    answer,
    confirm
  } = useAkinator();

  const [gameState, setGameState] = React.useState('idle'); // idle, playing, won

  const handleStart = async () => {
    await startGame();
    setGameState('playing');
  };

  const handleAnswer = async (response) => {
    const result = await answer(response);
    // result contient la prochaine question ou proposition
  };

  const handleConfirm = async (isCorrect) => {
    const result = await confirm(isCorrect);
    if (result.found) {
      setGameState('won');
    }
  };

  if (error) {
    return (
      <div className="error">
        <h2>❌ Erreur</h2>
        <p>{error}</p>
        <button onClick={handleStart}>Réessayer</button>
      </div>
    );
  }

  if (gameState === 'idle') {
    return (
      <div className="start-screen">
        <h1>🎬 Akinator Film</h1>
        <p>Pensez à un film et je vais le deviner !</p>
        <button onClick={handleStart} disabled={isLoading}>
          {isLoading ? 'Chargement...' : 'Commencer'}
        </button>
      </div>
    );
  }

  if (gameState === 'won') {
    return (
      <div className="win-screen">
        <h2>🎉 J'ai trouvé !</h2>
        <p>Merci d'avoir joué !</p>
        <button onClick={() => { setGameState('idle'); handleStart(); }}>
          Rejouer
        </button>
      </div>
    );
  }

  return (
    <div className="game-screen">
      <div className="question-counter">
        Question #{questionNumber}
      </div>

      {!isGuessing ? (
        <div className="question">
          <h2>{currentQuestion}</h2>
          <div className="answers">
            <button 
              onClick={() => handleAnswer('y')} 
              disabled={isLoading}
              className="btn-yes"
            >
              ✅ Oui
            </button>
            <button 
              onClick={() => handleAnswer('n')} 
              disabled={isLoading}
              className="btn-no"
            >
              ❌ Non
            </button>
            <button 
              onClick={() => handleAnswer('?')} 
              disabled={isLoading}
              className="btn-unknown"
            >
              🤷 Je ne sais pas
            </button>
          </div>
        </div>
      ) : (
        <div className="guess">
          <h2>💡 Je pense que c'est :</h2>
          <h3>{currentQuestion}</h3>
          <div className="answers">
            <button 
              onClick={() => handleConfirm(true)} 
              disabled={isLoading}
              className="btn-correct"
            >
              ✅ Oui, c'est ça !
            </button>
            <button 
              onClick={() => handleConfirm(false)} 
              disabled={isLoading}
              className="btn-incorrect"
            >
              ❌ Non, continue
            </button>
          </div>
        </div>
      )}

      {isLoading && <div className="loader">⏳ Réflexion...</div>}
    </div>
  );
}


// ===========================
// INTÉGRATION VUE.JS
// ===========================

const AkinatorVue = {
  data() {
    return {
      client: new AkinatorClient(),
      currentQuestion: null,
      questionNumber: 0,
      isGuessing: false,
      isLoading: false,
      error: null,
      gameState: 'idle'
    };
  },
  methods: {
    async startGame() {
      this.isLoading = true;
      this.error = null;
      try {
        const result = await this.client.startGame();
        this.currentQuestion = result.question;
        this.questionNumber = result.questionNumber;
        this.gameState = 'playing';
      } catch (err) {
        this.error = err.message;
      } finally {
        this.isLoading = false;
      }
    },
    async answer(response) {
      this.isLoading = true;
      try {
        const result = await this.client.answerQuestion(response);
        this.currentQuestion = result.content;
        this.questionNumber = result.questionNumber;
        this.isGuessing = result.isGuess;
      } catch (err) {
        this.error = err.message;
      } finally {
        this.isLoading = false;
      }
    },
    async confirm(isCorrect) {
      this.isLoading = true;
      try {
        const result = await this.client.confirmGuess(isCorrect);
        if (result.found) {
          this.gameState = 'won';
        } else {
          this.currentQuestion = result.content;
          this.questionNumber = result.questionNumber;
          this.isGuessing = false;
        }
      } catch (err) {
        this.error = err.message;
      } finally {
        this.isLoading = false;
      }
    }
  }
};


// Export pour utilisation en module
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { AkinatorClient };
}
