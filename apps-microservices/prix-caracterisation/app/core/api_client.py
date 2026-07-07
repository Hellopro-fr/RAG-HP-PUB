"""
Client API pour les appels vers api.hellopro.fr (BO v2) + provider LLM DeepSeek avec retry.
"""
import httpx
import logging
from typing import Dict, Any, Optional

from openai import OpenAI, AsyncOpenAI
from tenacity import (
    Retrying,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
)
from app.core.credentials import settings

logger = logging.getLogger(__name__)


def is_retryable_error(exception):
    """Retryable si 429 (rate limit) ou 503 (service unavailable)."""
    code = getattr(exception, "status_code", None)
    if code is None:
        code = getattr(exception, "code", None)
    return code in [503, 429]


class DeepSeek:
    """Provider pour l'API DeepSeek avec retry automatique sur 429/503."""

    def __init__(self, temperature: float = 0.1, max_retries: int = 5, config: Optional[dict] = None):
        config = config or {}
        self.API_KEY = config.get("api_key", settings.DEEPSEEK_API_KEY)
        self.BASE_URL = "https://api.deepseek.com"
        self.MODEL = "deepseek-v4-pro"
        self.TEMPERATURE = temperature
        self.max_retries = max_retries
        self.client = OpenAI(api_key=self.API_KEY, base_url=self.BASE_URL)
        self.async_client = AsyncOpenAI(api_key=self.API_KEY, base_url=self.BASE_URL)

    def chat(self, message: str, stream: bool = False) -> Dict[str, Any]:
        """
        Envoie un prompt à DeepSeek avec retry automatique.

        Returns:
            {'content', 'response'} en cas de succès,
            {'code', 'error', 'content': None, 'response': {...}} en cas d'échec.
        """
        if stream:
            return self.client.chat.completions.create(
                model=self.MODEL,
                messages=[
                    {"role": "system", "content": "Tu es un assistant intelligent et serviable."},
                    {"role": "user", "content": message},
                ],
                temperature=self.TEMPERATURE,
                stream=True,
            )

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
                        logger.info(f"Retry DeepSeek API... Tentative {attempt.retry_state.attempt_number}")
                    logger.info(f"DeepSeek API tentative: {attempt.retry_state.attempt_number}")
                    response = self.client.chat.completions.create(
                        model=self.MODEL,
                        messages=[
                            {"role": "system", "content": "Tu es un assistant intelligent et serviable."},
                            {"role": "user", "content": message},
                        ],
                        temperature=self.TEMPERATURE,
                        stream=False,
                    )
        except Exception as e:
            code = getattr(e, "status_code", None) or getattr(e, "code", None) or 500
            msg = getattr(e, "message", None) or str(e)
            logger.error(f"DeepSeek error: {msg} (Code: {code}) type: {type(e)}")
            return {
                "code": code,
                "error": msg,
                "content": None,
                "response": {"code": code, "message": str(msg), "status": getattr(e, "status", "UNKNOWN")},
            }

        return {"content": response.choices[0].message.content, "response": response}

    def set_temperature(self, temperature: float):
        self.TEMPERATURE = float(temperature)


class HelloProAPIClient:
    """Client pour les appels API vers base.hellopro.fr (BO v2).

    Timeout étendu (5 min par défaut) et retry automatique pour les requêtes longues.
    """

    BASE_URL = "https://api.hellopro.fr/v2/index.php"
    DEFAULT_TIMEOUT = 300  # 5 minutes
    MAX_RETRIES = 3

    def __init__(self, timeout: Optional[int] = None):
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        timeout_config = httpx.Timeout(
            connect=30.0,
            read=self.timeout,
            write=60.0,
            pool=30.0,
        )
        self.client = httpx.AsyncClient(timeout=timeout_config)

    async def close(self):
        await self.client.aclose()

    async def post(self, etape: str, field: str, action: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """POST généralisé avec retry (exponential backoff sur 5xx/timeout)."""
        headers = {
            "Authorization": f"Bearer {settings.HP_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {"etape": etape, "field": field, "action": action, "data": data}

        last_error = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                logger.info(f"API call: {etape}/{field}/{action} (tentative {attempt}/{self.MAX_RETRIES})")
                response = await self.client.post(self.BASE_URL, json=payload, headers=headers)
                response.raise_for_status()
                json_response = response.json()
                http_code = json_response.get("code")
                if http_code == 200:
                    return json_response.get("response")
                logger.error(f"Erreur API sur {etape}/{field}/{action}: code={http_code}")
                return None
            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(f"Timeout sur {etape}/{field}/{action} (tentative {attempt}): {e}")
                if attempt < self.MAX_RETRIES:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
            except httpx.HTTPStatusError as e:
                last_error = e
                logger.error(f"Erreur HTTP {e.response.status_code} sur {etape}/{field}/{action}")
                if e.response.status_code in [502, 503, 504] and attempt < self.MAX_RETRIES:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
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
        temperature: float = 0.1,
    ) -> Optional[Dict[str, Any]]:
        """Enregistre l'utilisation LLM (coûts + tokens) dans historique_exec_chatgpt."""
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
            "temperature": temperature,
        }
        try:
            return await self.post(etape="llm_tracking", field="", action="insert", data=data)
        except Exception as e:
            logger.warning(f"Erreur lors du log LLM usage: {e}")
            return None
