import asyncio
import json

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.gemini import ChatGemini, ErreurGeminiInteractions
from app.core.usage import extraire_usage
from app.graphe.agent_simple import _est_timeout

# Réponse réelle de l'API Interactions du 01/10/2026 (get-siren, sol-equestre.fr), signatures retirées
REPONSE_SOL_EQUESTRE = {
    "id": "v1_ChczWFMt", "status": "completed", "model": "gemini-3.1-flash-lite",
    "usage": {"total_tokens": 1035, "total_input_tokens": 1021, "total_output_tokens": 14,
              "total_thought_tokens": 0, "total_cached_tokens": 403,
              "grounding_tool_count": [{"type": "google_search", "count": 10, "search_query_count": 10}]},
    "steps": [
        {"type": "google_search_call", "id": "c1",
         "arguments": {"queries": ['"sol-equestre" SIRET OR SIREN', "site:sol-equestre.fr SIRET OR SIREN OR RCS"]}},
        {"type": "google_search_result", "call_id": "c1", "result": [{"search_suggestions": "<div>…</div>"}]},
        {"type": "url_context_call", "id": "c2", "arguments": {"urls": ["https://www.sol-equestre.fr/mentions"]}},
        {"type": "model_output", "content": [{"type": "text", "text": "47893401100030", "annotations": [
            {"type": "url_citation", "start_index": 0, "end_index": 14,
             "url": "https://www.sol-equestre.fr/mentions", "title": "sol-equestre.fr"}]}]},
    ],
}
REPONSE_GENERATE_CONTENT = {
    "candidates": [{"content": {"role": "model", "parts": [{"text": "sans recherche"}]}, "finishReason": "STOP"}],
    "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 2, "totalTokenCount": 7},
}
MESSAGES = [SystemMessage("Trouve le SIRET"), HumanMessage("sol-equestre.fr")]


@pytest.fixture
def api(monkeypatch):
    """Faux serveur Google : Interactions ou generateContent selon l'URL, requêtes gardées."""
    appels = []

    def repondre(requete, interaction):
        appels.append({"url": str(requete.url).split("?")[0], "corps": json.loads(requete.content),
                       "timeout": requete.extensions.get("timeout")})
        if "/interactions" in str(requete.url):
            return httpx.Response(api.statut_http, json=interaction, request=requete)
        return httpx.Response(200, json=REPONSE_GENERATE_CONTENT, request=requete)

    def envoyer(self, requete, *args, **kwargs):
        if api.erreur:
            raise api.erreur
        return repondre(requete, api.interaction)

    async def envoyer_async(self, requete, *args, **kwargs):
        return envoyer(self, requete)

    monkeypatch.setattr(httpx.Client, "send", envoyer)
    monkeypatch.setattr(httpx.AsyncClient, "send", envoyer_async)
    api.appels, api.interaction, api.statut_http, api.erreur = appels, REPONSE_SOL_EQUESTRE, 200, None
    return api


def gemini(*outils):
    llm = ChatGemini(model="gemini-3.1-flash-lite", google_api_key="g-test", timeout=300, max_retries=0,
                     temperature=0)
    return llm.bind_tools(list(outils)) if outils else llm


def test_recherche_google_passe_par_interactions(api):
    gemini({"google_search": {}}).invoke(MESSAGES)
    assert len(api.appels) == 1
    assert api.appels[0]["url"] == "https://generativelanguage.googleapis.com/v1beta/interactions"
    assert api.appels[0]["corps"] == {"model": "gemini-3.1-flash-lite", "input": "sol-equestre.fr",
                                      "system_instruction": "Trouve le SIRET", "store": False,
                                      "tools": [{"type": "google_search"}]}
    assert api.appels[0]["timeout"]["read"] == 300


def test_lecture_de_pages_seule_ou_avec_la_recherche(api):
    gemini({"google_search": {}}, {"url_context": {}}).invoke(MESSAGES)
    gemini({"url_context": {}}).invoke(MESSAGES)
    assert api.appels[0]["corps"]["tools"] == [{"type": "google_search"}, {"type": "url_context"}]
    assert api.appels[1]["corps"]["tools"] == [{"type": "url_context"}]


def test_reponse_convertie_au_format_langchain(api):
    reponse = gemini({"google_search": {}}).invoke(MESSAGES)
    assert isinstance(reponse, AIMessage) and reponse.text == "47893401100030"
    # Recherches = search_query_count, le chiffre facturé par Google
    assert extraire_usage(reponse) == {"tokens_entree": 1021, "tokens_sortie": 14, "recherches": 10}
    assert reponse.usage_metadata["input_token_details"] == {"cache_read": 403}
    meta = reponse.response_metadata
    assert meta["requetes_recherche"] == ['"sol-equestre" SIRET OR SIREN', "site:sol-equestre.fr SIRET OR SIREN OR RCS"]
    assert meta["urls_lues"] == ["https://www.sol-equestre.fr/mentions"]
    assert meta["sources"] == [{"url": "https://www.sol-equestre.fr/mentions", "title": "sol-equestre.fr"}]
    assert (meta["interaction_id"], meta["status"], meta["api"]) == ("v1_ChczWFMt", "completed", "interactions")


def test_sans_recherche_ni_lecture_reste_sur_generate_content(api):
    reponse = gemini().invoke(MESSAGES)
    assert reponse.text == "sans recherche"
    assert api.appels[0]["url"].endswith("/models/gemini-3.1-flash-lite:generateContent")


def test_ainvoke_et_stream_avec_recherche_passent_aussi_par_interactions(api):
    llm = gemini({"google_search": {}})
    assert asyncio.run(llm.ainvoke(MESSAGES)).text == "47893401100030"
    morceaux = list(llm.stream(MESSAGES))  # LangChain ajoute un morceau final vide
    assert "".join(m.text for m in morceaux) == "47893401100030"
    assert all(a["url"].endswith("/interactions") for a in api.appels) and len(api.appels) == 2


def test_interaction_non_terminee_refusee(api):
    # Régression signalée le 01/10/2026 : requires_action au lieu d'une recherche faite par Google
    api.interaction = {"id": "x", "status": "requires_action", "steps": []}
    with pytest.raises(ErreurGeminiInteractions, match="statut requires_action"):
        gemini({"google_search": {}}).invoke(MESSAGES)


def test_erreur_serveur_un_seul_appel_sans_relance_du_sdk(api):
    api.statut_http, api.interaction = 500, {"error": {"code": 500, "message": "boom"}}
    with pytest.raises(Exception, match="boom"):
        gemini({"google_search": {}}).invoke(MESSAGES)
    assert len(api.appels) == 1  # le SDK relance seul par défaut : budget de 300 s du curl PHP


def test_delai_depasse_classe_en_timeout_par_le_graphe(api):
    api.erreur = httpx.ReadTimeout("trop long")
    with pytest.raises(Exception) as exc:
        gemini({"google_search": {}}).invoke(MESSAGES)
    assert _est_timeout(exc.value)


def test_plusieurs_tours_ou_fonction_python_avec_la_recherche_refuses(api):
    def verifier_siren(siren: str) -> str:
        """Vérifie un SIREN."""
        return siren

    with pytest.raises(ErreurGeminiInteractions, match="plusieurs tours"):
        gemini({"google_search": {}}).invoke(MESSAGES + [AIMessage("1"), HumanMessage("Corrige")])
    with pytest.raises(ErreurGeminiInteractions, match="non gérés"):
        gemini({"google_search": {}}, verifier_siren).invoke(MESSAGES)
