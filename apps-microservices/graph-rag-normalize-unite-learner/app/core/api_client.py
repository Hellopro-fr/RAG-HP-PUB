"""
Clients du learner : DeepSeek (LLM, retry 429/503) + HelloProAPIClient (BO v2).

Le BO v2 porte tout le CRUD (règle projet : logique en Python, CRUD en PHP) :
  - prompt/info/get             : charge le prompt learner (BDD action_prompt_chatgpt)
  - normalisation/apprentissage : dédup/journal (get + upsert claim atomique)
  - normalisation/referentiel/save : insertion des lignes apprises
  - llm_tracking                : coût/tokens
"""
import logging
from typing import Any, Dict, List, Optional

import httpx
from openai import OpenAI
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)


def is_retryable_error(exception) -> bool:
    """Retryable si 429 (rate limit) ou 503 (service unavailable)."""
    code = getattr(exception, "status_code", None) or getattr(exception, "code", None)
    return code in [503, 429]


class DeepSeek:
    """Provider DeepSeek avec retry automatique sur 429/503 (même pattern que prix-caracterisation)."""

    def __init__(self, temperature: float = 0.1, max_retries: int = 5, config: Optional[dict] = None):
        config = config or {}
        self.API_KEY = config.get("api_key", settings.DEEPSEEK_API_KEY)
        self.BASE_URL = "https://api.deepseek.com"
        self.MODEL = "deepseek-v4-pro"
        self.TEMPERATURE = temperature
        self.max_retries = max_retries
        self.client = OpenAI(api_key=self.API_KEY, base_url=self.BASE_URL)

    def chat(self, message: str) -> Dict[str, Any]:
        """Retourne {'content', 'response'} en succès, {'code','error',...} en échec."""
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
                    response = self.client.chat.completions.create(
                        model=self.MODEL,
                        messages=[
                            {"role": "system", "content": "Tu es un expert en métrologie et unités physiques."},
                            {"role": "user", "content": message},
                        ],
                        temperature=self.TEMPERATURE,
                        stream=False,
                    )
        except Exception as e:
            code = getattr(e, "status_code", None) or getattr(e, "code", None) or 500
            msg = getattr(e, "message", None) or str(e)
            logger.error(f"DeepSeek error: {msg} (Code: {code})")
            return {"code": code, "error": msg, "content": None, "response": None}

        return {"content": response.choices[0].message.content, "response": response}


class HelloProAPIClient:
    """Client BO v2 (httpx async, retry exponentiel sur 5xx/timeout).
    L'URL vient de `settings.BO_V2_URL` (jamais hardcodée) — DOIT être identique au service dynamique."""

    DEFAULT_TIMEOUT = 120
    MAX_RETRIES = 3

    def __init__(self, timeout: Optional[int] = None):
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=30.0, read=self.timeout, write=60.0, pool=30.0)
        )

    async def close(self):
        await self.client.aclose()

    async def post(self, etape: str, field: str, action: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        import asyncio

        headers = {"Authorization": f"Bearer {settings.HP_TOKEN}", "Content-Type": "application/json"}
        payload = {"etape": etape, "field": field, "action": action, "data": data}
        last_error = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = await self.client.post(settings.BO_V2_URL, json=payload, headers=headers)
                response.raise_for_status()
                json_response = response.json()
                if json_response.get("code") == 200:
                    return json_response.get("response")
                logger.error(f"Erreur API {etape}/{field}/{action}: code={json_response.get('code')}")
                return None
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                last_error = e
                status = getattr(getattr(e, "response", None), "status_code", None)
                if (isinstance(e, httpx.TimeoutException) or status in [502, 503, 504]) and attempt < self.MAX_RETRIES:
                    await asyncio.sleep(2 ** attempt)
                else:
                    return None
            except Exception as e:
                logger.error(f"Erreur inattendue {etape}/{field}/{action}: {e}")
                return None
        logger.error(f"Échec après {self.MAX_RETRIES} tentatives {etape}/{field}/{action}: {last_error}")
        return None

    # ----- Wrappers learner ------------------------------------------------ #
    async def get_prompt(self, id_prompt: str) -> Optional[Dict[str, Any]]:
        return await self.post("prompt", "info", "get", {"id_prompt": id_prompt})

    async def get_referentiel(self) -> Optional[Dict[str, Any]]:
        return await self.post("normalisation", "referentiel", "get", {})

    async def apprentissage_get(self, unite: str, label_context: str) -> Optional[Dict[str, Any]]:
        return await self.post(
            "normalisation", "apprentissage", "get",
            {"unite": unite, "label_context": label_context},
        )

    async def apprentissage_upsert(
        self,
        unite: str,
        label_context: str,
        statut: str,
        confiance: Optional[float] = None,
        payload_llm: Optional[dict] = None,
        raison_rejet: Optional[str] = None,
        nb_requeue: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        data: Dict[str, Any] = {"unite": unite, "label_context": label_context, "statut": statut}
        if confiance is not None:
            data["confiance"] = confiance
        if payload_llm is not None:
            data["payload_llm"] = payload_llm
        if raison_rejet is not None:
            data["raison_rejet"] = raison_rejet
        if nb_requeue is not None:
            data["nb_requeue"] = nb_requeue
        return await self.post("normalisation", "apprentissage", "upsert", data)

    async def referentiel_save_batch(self, tables: Dict[str, List[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
        """Save ATOMIQUE multi-tables (#4) : le BO insère toutes les tables dans UNE transaction
        (COMMIT/ROLLBACK). Un échec ⇒ rien écrit ⇒ retry propre, zéro ligne orpheline/dupliquée."""
        payload_tables = [{"table": t, "rows": rows} for t, rows in tables.items()]
        return await self.post("normalisation", "referentiel", "save", {"tables": payload_tables})

    async def log_llm_usage(
        self, type_ia: int, model: str, input_token: int, output_token: int,
        id_process: str, origine: str, etat: int = 1, retour_erreur: str = "", temperature: float = 0.1,
    ) -> Optional[Dict[str, Any]]:
        data = {
            "type_ia": type_ia, "model": model,
            "input_token": input_token, "output_token": output_token,
            "total_token": input_token + output_token,
            "id_process": str(id_process), "origine": origine,
            "etat": etat, "retour_erreur": retour_erreur, "temperature": temperature,
        }
        try:
            return await self.post(etape="llm_tracking", field="", action="insert", data=data)
        except Exception as e:
            logger.warning(f"Erreur log LLM usage: {e}")
            return None
