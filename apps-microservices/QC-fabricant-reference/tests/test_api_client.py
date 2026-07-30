"""
Tests du client API / LLM sans I/O reelle.

Verifient :
- le modele DeepSeek et l'URL viennent de la configuration (aucun hardcode),
- la classification des erreurs retryables,
- la forme du payload envoye a l'API HelloPro.

Execution (depuis la racine du service) :
    PYTHONPATH=. pytest tests/test_api_client.py
"""
import os
import sys
import asyncio
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.api_client import (
    DeepSeek,
    EmptyResponseError,
    HelloProAPIClient,
    is_retryable_error,
)
from app.core.credentials import settings


class TestDeepSeekConfiguration:
    def test_modele_et_url_issus_de_la_config(self):
        """Le modele ne doit jamais etre hardcode : le run flash/pro se choisit par env."""
        deepseek = DeepSeek()
        assert deepseek.MODEL == settings.DEEPSEEK_MODEL_NAME
        assert deepseek.BASE_URL == settings.DEEPSEEK_API_URL

    def test_temperature_par_defaut_deterministe(self):
        assert DeepSeek().TEMPERATURE == 0

    def test_set_temperature(self):
        deepseek = DeepSeek()
        deepseek.set_temperature("0.3")
        assert deepseek.TEMPERATURE == 0.3


class TestIsRetryableError:
    def test_reponse_vide_est_retryable(self):
        assert is_retryable_error(EmptyResponseError("vide")) is True

    def test_503_et_429_retryables(self):
        for code in (503, 429):
            err = Exception("boom")
            err.status_code = code
            assert is_retryable_error(err) is True

    def test_400_non_retryable(self):
        err = Exception("bad request")
        err.status_code = 400
        assert is_retryable_error(err) is False

    def test_erreur_sans_code_non_retryable(self):
        assert is_retryable_error(ValueError("nope")) is False


class TestHelloProAPIClientPost:
    def _client_avec_reponse(self, json_payload):
        client = HelloProAPIClient()
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json = MagicMock(return_value=json_payload)
        client.client = MagicMock()
        client.client.post = AsyncMock(return_value=response)
        return client

    def test_payload_etape_field_action(self):
        client = self._client_avec_reponse({"code": 200, "response": [{"id_produit": "1"}]})

        resultat = asyncio.run(
            client.post("fabricant_reference", "produits", "get", {"id_categorie": "42"})
        )

        assert resultat == [{"id_produit": "1"}]
        _, kwargs = client.client.post.call_args
        assert kwargs["json"] == {
            "etape": "fabricant_reference",
            "field": "produits",
            "action": "get",
            "data": {"id_categorie": "42"},
        }
        assert kwargs["headers"]["Authorization"].startswith("Bearer ")

    def test_code_non_200_retourne_none(self):
        client = self._client_avec_reponse({"code": 500, "response": None})
        assert asyncio.run(client.post("fabricant_reference", "produits", "get", {})) is None
