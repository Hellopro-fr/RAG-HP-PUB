"""
Client API pour les appels vers base.hellopro.fr
"""
import httpx
import logging
from typing import Dict,  List, Any, Optional

from google.protobuf.json_format import MessageToDict
from google import genai
from google.genai import types, errors

from common_utils.grpc_clients.schemas.chat import ChatRequest
from openai import OpenAI, AsyncOpenAI

from common_utils.grpc_clients.schemas.chat import ChatBaseURL, ChatProvider
from google.genai.errors import APIError
from tenacity import (
    Retrying,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
)
from app.core.credentials import settings

logger = logging.getLogger(__name__)



class LLMProvider:
    def __init__(self, config=None):
        config = config or {}
        self.PROVIDER = config.get("provider", ChatProvider.DEEPSEEK)
        if self.PROVIDER == ChatProvider.DEEPSEEK:
            self.API_KEY = config.get("api_key", settings.DEEPSEEK_API_KEY)
            self.BASE_URL = ChatBaseURL.DEEPSEEK
        elif self.PROVIDER == ChatProvider.GPT:
            self.API_KEY = config.get("api_key", settings.OPENAI_API_KEY)
            self.BASE_URL = ChatBaseURL.OPENAI
        elif self.PROVIDER == ChatProvider.OPENROUTER:
            self.API_KEY = config.get("api_key", settings.OPENROUTER_API_KEY)
            self.BASE_URL = ChatBaseURL.OPENROUTER

        self.MODEL = config.get("model", "deepseek-chat")
        self.TEMPERATURE = config.get("temperature", 0.4)
        self.client = OpenAI(api_key=self.API_KEY, base_url=self.BASE_URL)
        self.async_client = AsyncOpenAI(api_key=self.API_KEY, base_url=self.BASE_URL)

    def chat(self, message, stream=False):
        response = self.client.chat.completions.create(
            model=self.MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Tu es un assistant intelligent et serviable.",
                },
                {"role": "user", "content": message},
            ],
            temperature=self.TEMPERATURE,
            stream=stream,
        )
        if stream:
            return response
        return {"content": response.choices[0].message.content, "response": response}

    def set_temperature(self, temperature):
        self.TEMPERATURE = float(temperature)

    async def stream(self, message):
        response_stream = await self.async_client.chat.completions.create(
            model=self.MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful and intelligent assistant.",
                },
                {"role": "user", "content": message},
            ],
            temperature=self.TEMPERATURE,
            stream=True,
        )
        async for chunk in response_stream:
            yield chunk

class DeepSeek:
    def __init__(self, temperature=0.1, config=None):
        config = config or {}
        self.API_KEY = config.get("api_key", settings.DEEPSEEK_API_KEY)
        self.BASE_URL = "https://api.deepseek.com"
        self.MODEL = "deepseek-chat"
        self.TEMPERATURE = temperature
        self.client = OpenAI(api_key=self.API_KEY, base_url=self.BASE_URL)
        self.async_client = AsyncOpenAI(api_key=self.API_KEY, base_url=self.BASE_URL)

    def chat(self, message, stream=False):
        response = self.client.chat.completions.create(
            model=self.MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Tu es un assistant intelligent et serviable.",
                },
                {"role": "user", "content": message},
            ],
            temperature=self.TEMPERATURE,
            stream=stream,
        )
        if stream:
            return response
        return {"content": response.choices[0].message.content, "response": response}

    def set_temperature(self, temperature):
        self.TEMPERATURE = float(temperature)

    async def stream(self, message):
        response_stream = await self.async_client.chat.completions.create(
            model=self.MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful and intelligent assistant.",
                },
                {"role": "user", "content": message},
            ],
            temperature=self.TEMPERATURE,
            stream=True,
        )
        async for chunk in response_stream:
            yield chunk

        
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
        model: str = "gemini-2.0-flash-thinking-exp-01-21",
        thinking_level: str = "high",
        max_retries: int = 10
    ):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model
        self.thinking_level = thinking_level
        self.max_retries = max_retries
        self.client = genai.Client(api_key=self.api_key)
    
    def chat(self, prompt: str) -> Dict[str, Any]:
        """
        Envoie un prompt à Gemini avec retry automatique
        
        Args:
            prompt: Le prompt à envoyer
            
        Returns:
            Dict avec 'code', 'content', 'response' et éventuellement 'error'
        """
        response = None
        
        try:
            # Configure Tenacity pour les retries
            retryer = Retrying(
                stop=stop_after_attempt(self.max_retries),
                wait=wait_exponential(multiplier=1, min=1, max=60),
                retry=retry_if_exception(is_retryable_error),
                reraise=True,
            )
            
            for attempt in retryer:
                with attempt:
                    # Log seulement sur les retries
                    if attempt.retry_state.attempt_number > 1:
                        logger.info(
                            f"Retry Gemini API... Tentative {attempt.retry_state.attempt_number}"
                        )
                    
                    logger.info(
                        f"Gemini API tentative: {attempt.retry_state.attempt_number}"
                    )
                    
                    response = self.client.models.generate_content(
                        model=self.model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            thinking_config=types.ThinkingConfig(
                                thinking_level=self.thinking_level,
                                include_thoughts=True,
                            )
                        ),
                    )
        
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
        
        # Succès
        api_response_dict = response.model_dump()
        safe_api_response = make_serializable(api_response_dict)
        
        return {"message": response.text, "api_response": safe_api_response}


class HelloProAPIClient:
    """Client pour les appels API vers base.hellopro.fr"""
    
    BASE_URL = "https://dev-api.hellopro.fr/v2/index.php"
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
    
    async def close(self):
        """Ferme le client HTTP"""
        await self.client.aclose()
    
    async def post(self, etape: str, field: str, action: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Fonction généralisée pour tous les appels POST
        
        Args:
            etape: L'étape à appeler (ex: "question")
            field: Le champ à appeler (ex: "question1" , "question2aN")
            action: L'action à appeler (ex: "get" , "save" , "reset" , "update")
            data: Les données à envoyer
            
        Returns:
            La réponse JSON ou None en cas d'erreur
        """
        try:
            headers = {
                "Authorization": f"Bearer {settings.HP_TOKEN}", 
                "Content-Type": "application/json"
            }

            url = self.BASE_URL
            response = await self.client.post(
                url, 
                json={"etape": etape, "field": field, "action": action, "data": data},
                headers=headers 
            )
            response.raise_for_status()
            
            response = response.json()
            http_code = response.get("code")
            if http_code == 200:
                return response.get("response")
            else:
                logger.error(f"Erreur HTTP sur {etape} {field} {action} : {http_code} {response}")
                return None
        except httpx.HTTPError as e:
            logger.error(f"Erreur HTTP sur {etape} {field} {action} : {e}")
            return None
        except Exception as e:
            logger.error(f"Erreur lors de l'appel API {etape} {field} {action} : {e}")
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
            return await self.post(etape="llm_tracking", field="", action="insert", data=data)
        except Exception as e:
            logger.warning(f"Erreur lors du log LLM usage: {e}")
            return None