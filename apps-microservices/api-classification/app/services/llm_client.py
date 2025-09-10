# app/services/llm_client.py
import openai
import logging
import time
from typing import List, Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..exceptions import LLMConnectionError, RateLimitError, TimeoutError
from ..handlers import ErrorHandler

logger = logging.getLogger(__name__)

class LLMClient:
    """Client unifié pour les services LLM (OpenAI et DeepSeek)"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.openai_client = None
        self.deepseek_client = None
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialise les clients OpenAI et DeepSeek avec gestion d'erreurs"""
        # Initialisation OpenAI
        if self.config.get('openai', {}).get('api_key'):
            try:
                self.openai_client = openai.OpenAI(
                    api_key=self.config['openai']['api_key'],
                    timeout=30.0,
                    max_retries=2
                )
                # Test de connexion rapide
                self._test_openai_connection()
                logger.info("Client OpenAI initialisé avec succès")
            except Exception as e:
                logger.error(f"Erreur lors de l'initialisation du client OpenAI: {e}")
                self.openai_client = None
        else:
            logger.info("Configuration OpenAI manquante - client non initialisé")
        
        # Initialisation DeepSeek
        if self.config.get('deepseek', {}).get('api_key'):
            try:
                self.deepseek_client = openai.OpenAI(
                    api_key=self.config['deepseek']['api_key'],
                    base_url=self.config['deepseek']['base_url'],
                    timeout=30.0,
                    max_retries=2
                )
                # Test de connexion rapide
                self._test_deepseek_connection()
                logger.info("Client DeepSeek initialisé avec succès")
            except Exception as e:
                logger.error(f"Erreur lors de l'initialisation du client DeepSeek: {e}")
                self.deepseek_client = None
        else:
            logger.info("Configuration DeepSeek manquante - client non initialisé")
    
    def _test_openai_connection(self):
        """Test rapide de la connexion OpenAI"""
        try:
            # Test simple avec liste des modèles (plus rapide qu'une completion)
            models = self.openai_client.models.list()
            logger.debug("Test de connexion OpenAI réussi")
        except Exception as e:
            raise LLMConnectionError("OpenAI", f"Test de connexion échoué: {str(e)}")
    
    def _test_deepseek_connection(self):
        """Test rapide de la connexion DeepSeek"""
        try:
            # Test simple avec liste des modèles
            models = self.deepseek_client.models.list()
            logger.debug("Test de connexion DeepSeek réussi")
        except Exception as e:
            raise LLMConnectionError("DeepSeek", f"Test de connexion échoué: {str(e)}")
    
    def get_available_llms(self) -> List[str]:
        """Retourne la liste des LLMs disponibles"""
        available = []
        if self.openai_client:
            available.append("OpenAI")
        if self.deepseek_client:
            available.append("DeepSeek")
        return available
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((openai.RateLimitError, openai.APITimeoutError))
    )
    def query_openai(self, messages: List[Dict[str, str]], use_response_format: bool = True, 
                     max_tokens: Optional[int] = None, temperature: float = 0.0) -> str:
        """Interroge OpenAI avec retry automatique"""
        if not self.openai_client:
            raise LLMConnectionError("OpenAI", "Client OpenAI non initialisé")
        
        start_time = time.time()
        
        try:
            # Validation des messages
            self._validate_messages(messages)
            
            # Préparation des paramètres
            kwargs = {
                "model": self.config['openai']['model'],
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens or 500,
                "timeout": 30
            }
            
            if use_response_format:
                kwargs["response_format"] = {"type": "json_object"}
            
            logger.debug(f"Appel OpenAI avec modèle: {kwargs['model']}")
            
            # Appel API
            completion = self.openai_client.chat.completions.create(**kwargs)
            
            # Vérifications de la réponse
            if not completion.choices:
                raise LLMConnectionError("OpenAI", "Aucune réponse reçue")
            
            response_content = completion.choices[0].message.content
            if not response_content:
                raise LLMConnectionError("OpenAI", "Réponse vide reçue")
            
            # Métriques
            processing_time = time.time() - start_time
            tokens_used = completion.usage.total_tokens if completion.usage else 0
            
            logger.info(f"OpenAI - Temps: {processing_time:.2f}s, Tokens: {tokens_used}")
            
            return response_content
            
        except openai.RateLimitError as e:
            logger.warning(f"Rate limit OpenAI atteint: {e}")
            retry_after = getattr(e, 'retry_after', None) or 60
            raise RateLimitError("OpenAI", retry_after)
            
        except openai.APITimeoutError as e:
            logger.error(f"Timeout OpenAI: {e}")
            raise TimeoutError("Requête OpenAI", 30)
            
        except openai.AuthenticationError as e:
            logger.error(f"Erreur d'authentification OpenAI: {e}")
            raise LLMConnectionError("OpenAI", "Clé API invalide ou expirée")
            
        except openai.BadRequestError as e:
            logger.error(f"Requête invalide OpenAI: {e}")
            raise LLMConnectionError("OpenAI", f"Requête invalide: {str(e)}")
            
        except openai.APIConnectionError as e:
            logger.error(f"Erreur de connexion OpenAI: {e}")
            raise LLMConnectionError("OpenAI", "Impossible de se connecter à l'API OpenAI")
            
        except Exception as e:
            logger.exception(f"Erreur inattendue OpenAI: {e}")
            raise ErrorHandler.handle_openai_error(e, "OpenAI")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((openai.RateLimitError, openai.APITimeoutError))
    )
    def query_deepseek(self, messages: List[Dict[str, str]], use_response_format: bool = True,
                       max_tokens: Optional[int] = None, temperature: float = 0.0) -> str:
        """Interroge DeepSeek avec retry automatique"""
        if not self.deepseek_client:
            raise LLMConnectionError("DeepSeek", "Client DeepSeek non initialisé")
        
        start_time = time.time()
        
        try:
            # Validation des messages
            self._validate_messages(messages)
            
            # Préparation des paramètres
            kwargs = {
                "model": self.config['deepseek']['model'],
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens or 500,
                "timeout": 30
            }
            
            if use_response_format:
                kwargs["response_format"] = {"type": "json_object"}
            
            logger.debug(f"Appel DeepSeek avec modèle: {kwargs['model']}")
            
            # Appel API
            completion = self.deepseek_client.chat.completions.create(**kwargs)
            
            # Vérifications de la réponse
            if not completion.choices:
                raise LLMConnectionError("DeepSeek", "Aucune réponse reçue")
            
            response_content = completion.choices[0].message.content
            if not response_content:
                raise LLMConnectionError("DeepSeek", "Réponse vide reçue")
            
            # Métriques
            processing_time = time.time() - start_time
            tokens_used = completion.usage.total_tokens if completion.usage else 0
            
            logger.info(f"DeepSeek - Temps: {processing_time:.2f}s, Tokens: {tokens_used}")
            
            return response_content
            
        except openai.RateLimitError as e:
            logger.warning(f"Rate limit DeepSeek atteint: {e}")
            retry_after = getattr(e, 'retry_after', None) or 60
            raise RateLimitError("DeepSeek", retry_after)
            
        except openai.APITimeoutError as e:
            logger.error(f"Timeout DeepSeek: {e}")
            raise TimeoutError("Requête DeepSeek", 30)
            
        except openai.AuthenticationError as e:
            logger.error(f"Erreur d'authentification DeepSeek: {e}")
            raise LLMConnectionError("DeepSeek", "Clé API invalide ou expirée")
            
        except openai.BadRequestError as e:
            logger.error(f"Requête invalide DeepSeek: {e}")
            raise LLMConnectionError("DeepSeek", f"Requête invalide: {str(e)}")
            
        except openai.APIConnectionError as e:
            logger.error(f"Erreur de connexion DeepSeek: {e}")
            raise LLMConnectionError("DeepSeek", "Impossible de se connecter à l'API DeepSeek")
            
        except Exception as e:
            logger.exception(f"Erreur inattendue DeepSeek: {e}")
            raise ErrorHandler.handle_openai_error(e, "DeepSeek")
    
    def _validate_messages(self, messages: List[Dict[str, str]]):
        """Valide le format des messages"""
        if not messages:
            raise ValueError("La liste des messages ne peut pas être vide")
        
        for i, message in enumerate(messages):
            if not isinstance(message, dict):
                raise ValueError(f"Message {i}: doit être un dictionnaire")
            
            if 'role' not in message:
                raise ValueError(f"Message {i}: clé 'role' manquante")
            
            if 'content' not in message:
                raise ValueError(f"Message {i}: clé 'content' manquante")
            
            if message['role'] not in ['system', 'user', 'assistant']:
                raise ValueError(f"Message {i}: rôle invalide '{message['role']}'")
            
            if not isinstance(message['content'], str) or not message['content'].strip():
                raise ValueError(f"Message {i}: contenu vide ou invalide")
            
            # Limite de longueur raisonnable
            if len(message['content']) > 50000:
                raise ValueError(f"Message {i}: contenu trop long (max 50000 caractères)")
    
    def get_client_info(self, provider: str) -> Dict[str, Any]:
        """Retourne des informations sur un client spécifique"""
        if provider.lower() == "openai" and self.openai_client:
            return {
                "provider": "OpenAI",
                "model": self.config.get('openai', {}).get('model', 'unknown'),
                "status": "connected",
                "base_url": "https://api.openai.com/v1"
            }
        elif provider.lower() == "deepseek" and self.deepseek_client:
            return {
                "provider": "DeepSeek", 
                "model": self.config.get('deepseek', {}).get('model', 'unknown'),
                "status": "connected",
                "base_url": self.config.get('deepseek', {}).get('base_url', 'unknown')
            }
        else:
            return {
                "provider": provider,
                "status": "not_connected",
                "error": "Client non initialisé ou configuration manquante"
            }
    
    def health_check(self) -> Dict[str, Any]:
        """Vérifie la santé de tous les clients LLM"""
        health = {
            "timestamp": time.time(),
            "overall_status": "healthy",
            "providers": {}
        }
        
        # Test OpenAI
        if self.openai_client:
            try:
                start_time = time.time()
                self._test_openai_connection()
                response_time = time.time() - start_time
                health["providers"]["OpenAI"] = {
                    "status": "healthy",
                    "response_time_ms": round(response_time * 1000, 2),
                    "model": self.config.get('openai', {}).get('model', 'unknown')
                }
            except Exception as e:
                health["providers"]["OpenAI"] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
                health["overall_status"] = "degraded"
        else:
            health["providers"]["OpenAI"] = {
                "status": "not_configured"
            }
        
        # Test DeepSeek
        if self.deepseek_client:
            try:
                start_time = time.time()
                self._test_deepseek_connection()
                response_time = time.time() - start_time
                health["providers"]["DeepSeek"] = {
                    "status": "healthy",
                    "response_time_ms": round(response_time * 1000, 2),
                    "model": self.config.get('deepseek', {}).get('model', 'unknown')
                }
            except Exception as e:
                health["providers"]["DeepSeek"] = {
                    "status": "unhealthy", 
                    "error": str(e)
                }
                health["overall_status"] = "degraded"
        else:
            health["providers"]["DeepSeek"] = {
                "status": "not_configured"
            }
        
        # Statut global
        unhealthy_count = sum(1 for p in health["providers"].values() if p["status"] == "unhealthy")
        if unhealthy_count == len(health["providers"]):
            health["overall_status"] = "unhealthy"
        elif unhealthy_count > 0:
            health["overall_status"] = "degraded"
        
        return health
    
    def estimate_tokens(self, text: str) -> int:
        """Estime le nombre de tokens dans un texte (approximation)"""
        # Approximation simple : ~4 caractères par token
        return len(text) // 4
    
    def estimate_cost(self, provider: str, input_tokens: int, output_tokens: int) -> float:
        """Estime le coût d'une requête (prix approximatifs en USD)"""
        # Prix approximatifs (à ajuster selon les tarifs actuels)
        pricing = {
            "OpenAI": {
                "input": 0.01 / 1000,   # $0.01 per 1K tokens
                "output": 0.03 / 1000   # $0.03 per 1K tokens
            },
            "DeepSeek": {
                "input": 0.0014 / 1000,  # $0.0014 per 1K tokens
                "output": 0.0028 / 1000  # $0.0028 per 1K tokens
            }
        }
        
        if provider not in pricing:
            return 0.0
        
        rates = pricing[provider]
        return (input_tokens * rates["input"]) + (output_tokens * rates["output"])


# Fonction utilitaire pour créer un client LLM
def create_llm_client(config: Dict[str, Any]) -> LLMClient:
    """Factory function pour créer un client LLM"""
    try:
        client = LLMClient(config)
        available_llms = client.get_available_llms()
        
        if not available_llms:
            logger.warning("Aucun LLM disponible après initialisation")
        else:
            logger.info(f"Client LLM créé avec succès. LLMs disponibles: {available_llms}")
        
        return client
    except Exception as e:
        logger.error(f"Erreur lors de la création du client LLM: {e}")
        raise


# Context manager pour gestion automatique des ressources
class LLMClientContext:
    """Context manager pour gérer automatiquement le cycle de vie du client LLM"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.client = None
    
    def __enter__(self) -> LLMClient:
        self.client = create_llm_client(self.config)
        return self.client
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            # Cleanup si nécessaire
            logger.debug("Fermeture du client LLM")