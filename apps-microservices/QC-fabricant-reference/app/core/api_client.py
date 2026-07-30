"""
Clients externes du service : API HelloPro (REST) et LLM DeepSeek.

Version elaguee de QC-caracterisation : ni Gemini, ni gRPC, ni protobuf — ce service
n'appelle qu'un seul modele et une seule API.
"""
import asyncio
import logging
from typing import Any, Dict, Optional

import httpx
from openai import OpenAI
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_fixed

from app.core.credentials import settings

logger = logging.getLogger(__name__)


class EmptyResponseError(Exception):
    """Levee quand le LLM renvoie un contenu vide alors qu'un retour etait attendu."""
    pass


def is_retryable_error(exception: Exception) -> bool:
    """Retryable : 503 / 429 cote fournisseur, ou reponse vide."""
    if isinstance(exception, EmptyResponseError):
        return True

    code = getattr(exception, "status_code", None)
    if code is None:
        code = getattr(exception, "code", None)

    return code in [503, 429]


class DeepSeek:
    """Provider DeepSeek avec retry sur erreurs 503/429 et contenu vide.

    Le modele et l'URL viennent de la configuration : basculer flash -> pro est une
    variable d'environnement, pas un redeploiement de code.
    """

    DEFAULT_MAX_RETRIES = 5
    RETRY_WAIT_SECONDS = 2
    SYSTEM_PROMPT = "Tu es un assistant d'extraction de donnees. Tu reponds exclusivement en JSON valide."

    def __init__(self, temperature: float = 0, config: Optional[Dict] = None,
                 max_retries: Optional[int] = None):
        config = config or {}
        self.API_KEY = config.get("api_key", settings.DEEPSEEK_API_KEY)
        self.BASE_URL = config.get("base_url", settings.DEEPSEEK_API_URL)
        self.MODEL = config.get("model", settings.DEEPSEEK_MODEL_NAME)
        self.TEMPERATURE = temperature
        self.max_retries = max_retries if max_retries is not None else self.DEFAULT_MAX_RETRIES
        self.client = OpenAI(api_key=self.API_KEY, base_url=self.BASE_URL)

    def set_temperature(self, temperature):
        self.TEMPERATURE = float(temperature)

    def chat(self, message: str) -> Dict[str, Any]:
        """Appel synchrone (a envelopper dans asyncio.to_thread).

        Retourne {"content": ..., "response": ...} en cas de succes,
        {"code": ..., "error": ..., "content": None} en cas d'echec definitif.
        """
        response = None

        try:
            retryer = Retrying(
                stop=stop_after_attempt(self.max_retries),
                wait=wait_fixed(self.RETRY_WAIT_SECONDS),
                retry=retry_if_exception(is_retryable_error),
                reraise=True,
            )

            for attempt in retryer:
                with attempt:
                    if attempt.retry_state.attempt_number > 1:
                        logger.info(
                            f"Retry DeepSeek... tentative "
                            f"{attempt.retry_state.attempt_number}/{self.max_retries}"
                        )

                    response = self.client.chat.completions.create(
                        model=self.MODEL,
                        messages=[
                            {"role": "system", "content": self.SYSTEM_PROMPT},
                            {"role": "user", "content": message},
                        ],
                        temperature=self.TEMPERATURE,
                    )

                    content = (
                        response.choices[0].message.content
                        if response and response.choices
                        else None
                    )
                    if not content or not content.strip():
                        logger.warning(
                            f"DeepSeek a renvoye un contenu vide (tentative "
                            f"{attempt.retry_state.attempt_number}/{self.max_retries})"
                        )
                        raise EmptyResponseError("Reponse DeepSeek vide")

        except EmptyResponseError as e:
            logger.error(f"DeepSeek: contenu vide apres {self.max_retries} tentatives")
            return {"code": 502, "error": str(e), "content": None, "response": response}

        except Exception as e:
            code = getattr(e, "status_code", None) or getattr(e, "code", None) or 500
            logger.error(f"DeepSeek erreur: {e} (code {code})")
            return {"code": code, "error": str(e), "content": None, "response": response}

        return {"content": response.choices[0].message.content, "response": response}


class HelloProAPIClient:
    """Client de l'API HelloPro (etape / field / action) avec retry sur erreurs transitoires."""

    MAX_RETRIES = 3

    def __init__(self, timeout: Optional[int] = None):
        self.base_url = settings.HP_API_URL
        self.timeout = timeout or settings.HP_TIMEOUT_SECONDS
        timeout_config = httpx.Timeout(
            connect=30.0,
            read=self.timeout,
            write=60.0,
            pool=30.0,
        )
        self.client = httpx.AsyncClient(timeout=timeout_config)

    async def close(self):
        await self.client.aclose()

    async def post(self, etape: str, field: str, action: str,
                   data: Dict[str, Any]) -> Optional[Any]:
        """Appel POST generique. Retourne le contenu de `response`, ou None en cas d'erreur."""
        headers = {
            "Authorization": f"Bearer {settings.HP_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {"etape": etape, "field": field, "action": action, "data": data}

        last_error = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                logger.info(f"API call: {etape}/{field}/{action} (tentative {attempt}/{self.MAX_RETRIES})")

                response = await self.client.post(self.base_url, json=payload, headers=headers)
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
                    await asyncio.sleep(2 ** attempt)

            except httpx.HTTPStatusError as e:
                last_error = e
                logger.error(f"Erreur HTTP {e.response.status_code} sur {etape}/{field}/{action}")
                if e.response.status_code in [502, 503, 504] and attempt < self.MAX_RETRIES:
                    await asyncio.sleep(2 ** attempt)
                else:
                    return None

            except httpx.HTTPError as e:
                logger.error(f"Erreur HTTP sur {etape}/{field}/{action}: {e}")
                return None

            except Exception as e:
                logger.error(f"Erreur inattendue sur {etape}/{field}/{action}: {e}")
                return None

        logger.error(f"Echec apres {self.MAX_RETRIES} tentatives sur {etape}/{field}/{action}: {last_error}")
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
        temperature: float = 0,
    ) -> Optional[Any]:
        """Enregistre tokens et couts d'un appel LLM (table de suivi llm_tracking)."""
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
