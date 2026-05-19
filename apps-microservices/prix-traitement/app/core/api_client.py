"""
Client API pour les appels vers base.hellopro.fr
Providers LLM: GeminiProvider, ClaudeProvider, ChatGPTProvider
"""
import asyncio
import httpx
import logging
from typing import Dict,  List, Any, Optional

from google.protobuf.json_format import MessageToDict
from google import genai
from google.genai import types, errors

from google.genai.errors import APIError
import anthropic
from openai import AsyncOpenAI
from tenacity import (
    Retrying,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
)
from app.core.credentials import settings

logger = logging.getLogger(__name__)



def make_serializable(obj):
    """Parcourt récursivement l'objet pour convertir les bytes en hex string."""
    if isinstance(obj, bytes):
        return obj.hex()  # Convertit b'\xe6...' en string 'e6...'
    if isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [make_serializable(v) for v in obj]
    return obj


def is_retryable_error(exception):
    """
    Checks if the exception is a Google GenAI 503 or 429 error.
    """
    code = getattr(exception, "status_code", None)

    if code is None:
        code = getattr(exception, "code", None)

    return code in [503, 429]


class GeminiProvider:
    """Provider pour l'API Gemini avec retry automatique"""
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        model: str = "gemini-3.1-pro-preview",
        thinking_level: str = "low",
        max_retries: int = 10
    ):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model
        self.thinking_level = thinking_level
        self.max_retries = max_retries
        self.client = genai.Client(api_key=self.api_key)
    
    def _chat_sync(self, prompt: str) -> Dict[str, Any]:
        """
        Logique synchrone d'appel Gemini avec retry (Tenacity).
        Appelée via asyncio.to_thread pour ne pas bloquer l'event loop.
        """
        response = None

        try:
            retryer = Retrying(
                stop=stop_after_attempt(self.max_retries),
                wait=wait_exponential(multiplier=1, min=1, max=60),
                retry=retry_if_exception(is_retryable_error),
                reraise=True,
            )

            for attempt in retryer:
                with attempt:
                    if attempt.retry_state.attempt_number > 1:
                        logger.info(
                            f"Retry Gemini API... Tentative {attempt.retry_state.attempt_number}"
                        )

                    logger.info(
                        f"Gemini API tentative: {attempt.retry_state.attempt_number}"
                    )

                    # On n'envoie config que si le thinking_level demandé
                    # diffère du défaut du modèle :
                    # - gemini-3.1-flash-lite-preview : défaut = low
                    # - autres modèles 
                    needs_config = (
                        (self.model == "gemini-3.1-flash-lite-preview" and self.thinking_level != "low")
                        or (self.model != "gemini-3.1-flash-lite-preview")
                    )

                    generate_kwargs = {
                        "model": self.model,
                        "contents": prompt,
                    }
                    if needs_config:
                        generate_kwargs["config"] = types.GenerateContentConfig(
                            thinking_config=types.ThinkingConfig(
                                thinking_level=self.thinking_level,
                                include_thoughts=True,
                            )
                        )

                    response = self.client.models.generate_content(**generate_kwargs)

        except errors.ClientError as e:
            logger.error(
                f"Gemini ClientError: {e.message} (Code: {e.code}) type: {type(e)}"
            )
            return {
                "code": e.code,
                "error": e.message,
                "content": None,
                "response": {
                    "code": e.code,
                    "message": e.message,
                    "status": getattr(e, "status", "UNKNOWN"),
                }
            }

        except Exception as e:
            logger.error(f"Erreur inattendue dans Gemini: {e}")
            return {
                "code": 500,
                "error": str(e),
                "content": None,
                "response": {}
            }

        # Succès — format normalisé identique à Claude/ChatGPT
        usage_meta = response.usage_metadata
        input_tokens = usage_meta.prompt_token_count or 0
        output_tokens = (usage_meta.candidates_token_count or 0) + (usage_meta.thoughts_token_count or 0)

        api_response = {
            "id": None,
            "model": self.model,
            "finish_reason": response.candidates[0].finish_reason if response.candidates else None,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
        }

        return {"message": response.text, "api_response": api_response}

    async def chat(self, prompt: str) -> Dict[str, Any]:
        """
        Envoie un prompt à Gemini de manière asynchrone (ne bloque pas l'event loop).
        Délègue l'appel synchrone Gemini SDK à un thread séparé via asyncio.to_thread.
        """
        return await asyncio.to_thread(self._chat_sync, prompt)


class ClaudeProvider:
    """Provider pour l'API Claude (Anthropic) avec retry automatique.

    Utilise AsyncAnthropic pour éviter l'overhead de asyncio.to_thread.
    Le client async est partagé (singleton) pour réutiliser le pool de connexions HTTP.
    """

    # Mapping effort → budget_tokens pour Haiku (extended thinking)
    EFFORT_TO_BUDGET = {
        "high": 10000,
        "medium": 4096,
        "low": 1024,
    }

    # Client async partagé (singleton) pour réutiliser le pool de connexions
    _async_client: Optional[anthropic.AsyncAnthropic] = None

    @classmethod
    def _get_client(cls, api_key: str) -> anthropic.AsyncAnthropic:
        if cls._async_client is None:
            cls._async_client = anthropic.AsyncAnthropic(api_key=api_key)
        return cls._async_client

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-haiku-4-5",
        max_tokens: int = 16000,
        effort: Optional[str] = None,
        budget_tokens: Optional[int] = None,
        max_retries: int = 5,
    ):
        self.api_key = api_key or settings.ANTHROPIC_API_KEY
        self.model = model
        self.max_tokens = max_tokens
        self.effort = effort
        self.budget_tokens = budget_tokens
        self.max_retries = max_retries
        self.client = self._get_client(self.api_key)

    async def chat(self, prompt: str) -> Dict[str, Any]:
        """
        Envoie un prompt à Claude de manière asynchrone via AsyncAnthropic.
        """
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                if attempt > 1:
                    logger.info(f"Retry Claude API... Tentative {attempt}")

                logger.info(f"Claude API tentative: {attempt}")

                create_kwargs = {
                    "model": self.model,
                    "max_tokens": self.max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                }

                supports_effort = any(k in self.model.lower() for k in ("opus", "sonnet"))

                if supports_effort and self.effort and not self.budget_tokens:
                    create_kwargs["output_config"] = {"effort": self.effort}
                elif self.budget_tokens:
                    create_kwargs["thinking"] = {
                        "type": "enabled",
                        "budget_tokens": self.budget_tokens,
                        "display": "omitted",
                    }
                elif self.effort and not supports_effort:
                    create_kwargs["thinking"] = {
                        "type": "enabled",
                        "budget_tokens": self.EFFORT_TO_BUDGET.get(self.effort, 5000),
                        "display": "omitted",
                    }

                response = await self.client.messages.create(**create_kwargs)

                # Extraire le texte de la réponse
                message_text = ""
                for block in response.content:
                    if block.type == "text":
                        message_text += block.text

                # Extraire uniquement les champs utiles (évite model_dump() lourd)
                api_response = {
                    "id": response.id,
                    "model": response.model,
                    "finish_reason": response.stop_reason,
                    "usage": {
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                    },
                }

                return {"message": message_text, "api_response": api_response}

            except anthropic.RateLimitError as e:
                last_error = e
                logger.warning(f"Claude RateLimitError (tentative {attempt}): {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(min(2 ** attempt, 60))
                    continue

            except anthropic.APIStatusError as e:
                last_error = e
                if e.status_code in (503, 529) and attempt < self.max_retries:
                    logger.warning(f"Claude APIStatusError {e.status_code} (tentative {attempt}): {e}")
                    await asyncio.sleep(min(2 ** attempt, 60))
                    continue
                logger.error(f"Claude APIStatusError: {e.status_code} - {e.message}")
                return {
                    "error": e.message,
                    "code": e.status_code,
                    "content": None,
                    "api_response": {},
                }

            except Exception as e:
                logger.error(f"Erreur inattendue dans Claude: {e}")
                return {
                    "error": str(e),
                    "code": 500,
                    "content": None,
                    "api_response": {},
                }

        logger.error(f"Échec Claude après {self.max_retries} tentatives: {last_error}")
        return {
            "error": str(last_error),
            "code": 503,
            "content": None,
            "api_response": {},
        }


class ChatGPTProvider:
    """Provider pour l'API ChatGPT (OpenAI) async."""

    _async_client: Optional[AsyncOpenAI] = None

    @classmethod
    def _get_client(cls, api_key: str) -> AsyncOpenAI:
        if cls._async_client is None:
            cls._async_client = AsyncOpenAI(api_key=api_key)
        return cls._async_client

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4.1-mini",
        reasoning_effort: str = None,
    ):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.client = self._get_client(self.api_key)

    async def chat(self, prompt: str) -> Dict[str, Any]:
        """Envoie un prompt à ChatGPT de manière asynchrone."""
        try:
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
            }
            
            if self.reasoning_effort:
                kwargs["reasoning_effort"] = self.reasoning_effort

            response = await self.client.chat.completions.create(**kwargs)

            message_text = response.choices[0].message.content or ""

            api_response = {
                "id": response.id,
                "model": response.model,
                "usage": {
                    "input_tokens": response.usage.prompt_tokens,
                    "output_tokens": response.usage.completion_tokens,
                },
                "finish_reason": response.choices[0].finish_reason,
            }

            return {"message": message_text, "api_response": api_response}

        except Exception as e:
            logger.error(f"Erreur ChatGPT: {e}")
            return {
                "error": str(e),
                "code": getattr(e, "status_code", 500),
                "content": None,
                "api_response": {},
            }


class HelloProAPIClient:
    """Client pour les appels API vers base.hellopro.fr
    
    Avec timeout étendu (5 min par défaut) et retry automatique pour les requêtes longues.
    """
    
    BASE_URL = "https://api.hellopro.fr/v2/index.php"
    
    # Timeout par défaut de 5 minutes pour les requêtes longues (récupération catégorie)
    DEFAULT_TIMEOUT = 300  # 5 minutes
    MAX_RETRIES = 3
    
    def __init__(self, timeout: int = None):
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        # Configuration des timeouts: connect=30s, read/write=5min
        timeout_config = httpx.Timeout(
            connect=30.0,      # 30s pour établir la connexion
            read=self.timeout, # 5min pour lire la réponse
            write=60.0,        # 60s pour écrire la requête
            pool=30.0          # 30s pour attendre une connexion du pool
        )
        self.client = httpx.AsyncClient(timeout=timeout_config)
    
    async def close(self):
        """Ferme le client HTTP"""
        await self.client.aclose()
    
    async def post(self, etape: str, field: str, action: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Fonction généralisée pour tous les appels POST avec retry automatique
        
        Args:
            etape: L'étape à appeler (ex: "prix")
            field: Le champ à appeler (ex: "extraction_siteweb")
            action: L'action à appeler (ex: "get" , "save" , "reset" , "update")
            data: Les données à envoyer
            
        Returns:
            La réponse JSON ou None en cas d'erreur
        """
        headers = {
            "Authorization": f"Bearer {settings.HP_TOKEN}", 
            "Content-Type": "application/json"
        }
        payload = {"etape": etape, "field": field, "action": action, "data": data}
        
        last_error = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                logger.info(f"API call: {etape}/{field}/{action} (tentative {attempt}/{self.MAX_RETRIES})")
                
                response = await self.client.post(
                    self.BASE_URL, 
                    json=payload,
                    headers=headers 
                )
                response.raise_for_status()
                
                json_response = response.json()
                http_code = json_response.get("code")
                
                if http_code == 200:
                    return json_response.get("response")
                else:
                    logger.error(f"Erreur API sur {etape}/{field}/{action}: code={http_code}")
                    return None
                    
            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(f"Timeout sur {etape}/{field}/{action} (tentative {attempt}): {e}")
                if attempt < self.MAX_RETRIES:
                    import asyncio
                    wait_time = 2 ** attempt  # Exponential backoff: 2, 4, 8s
                    logger.info(f"Retry dans {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    
            except httpx.HTTPStatusError as e:
                last_error = e
                logger.error(f"Erreur HTTP {e.response.status_code} sur {etape}/{field}/{action}")
                # Retry sur 502, 503, 504 (erreurs serveur temporaires)
                if e.response.status_code in [502, 503, 504] and attempt < self.MAX_RETRIES:
                    import asyncio
                    wait_time = 2 ** attempt
                    logger.info(f"Retry dans {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    return None
                    
            except httpx.HTTPError as e:
                last_error = e
                logger.error(f"Erreur HTTP sur {etape}/{field}/{action}: {e}")
                return None
                
            except Exception as e:
                last_error = e
                logger.error(f"Erreur inattendue sur {etape}/{field}/{action}: {e}")
                return None
        
        # Toutes les tentatives échouées
        logger.error(f"Échec après {self.MAX_RETRIES} tentatives sur {etape}/{field}/{action}: {last_error}")
        return None
    
    async def log_llm_usage(
        self,
        type_ia: int,
        model: str,
        input_token: int,
        output_token: int,
        id_process: str,
        origine: str,
        etat: int = 1,
        retour_erreur: str = "",
        temperature: float = 0.9
    ) -> Optional[Dict[str, Any]]:
        """
        Enregistre l'utilisation LLM (coûts et tokens) dans la base de données
        
        Args:
            type_ia: 2 pour DeepSeek, 3 pour Gemini
            model: Nom du modèle (ex: gemini-2.0-flash, deepseek-v4-flash)
            input_token: Nombre de tokens d'entrée
            output_token: Nombre de tokens de sortie
            id_process: ID de la catégorie ou du processus
            origine: Nom du service (ex: prix-extraction-siteweb)
            etat: 1 pour succès, 2 pour erreur
            retour_erreur: Message d'erreur si etat=2
            temperature: Température utilisée
            
        Returns:
            La réponse de l'API ou None en cas d'erreur
        """
        data = {
            "type_ia": type_ia,
            "model": model,
            "input_token": input_token,
            "output_token": output_token,
            "total_token": input_token + output_token,
            "id_process": str(id_process),
            "origine": origine,
            "etat": etat,
            "retour_erreur": retour_erreur,
            "temperature": temperature
        }
        
        try:
            return await self.post(
                etape="llm_tracking",
                field="",
                action="insert",
                data=data
            )
        except Exception as e:
            logger.warning(f"Erreur lors du log LLM usage: {e}")
            return None
