import pytest
from langchain_deepseek import ChatDeepSeek

from app.core.config import Settings
from app.core.modeles import ErreurConfiguration, construire_modele

SETTINGS = Settings(OPENAI_API_KEY="sk-test", ANTHROPIC_API_KEY="sk-test", GEMINI_API_KEY="g-test",
                    DEEPSEEK_API_KEY="sk-test", MCP_GATEWAY_URL="https://mcp.test")
TOUT = {"recherche_web": 1, "mcp": 1}
RECHERCHE_SEULE = {"recherche_web": 1, "mcp": 0}
AUCUN = {"recherche_web": 0, "mcp": 0}


def fiche(fournisseur, nom, outils=None):
    return {"modele": {"fournisseur": fournisseur, "nom": nom, "temperature": 0}, "outils": outils or {}}


def jeton():
    return "jwt-test"


def test_openai_recherche_et_mcp_natifs():
    outils = {"recherche_web": {"max": 5}, "mcp": {"outils_autorises": ["bdd_query_readonly"]}}
    modele = construire_modele(fiche("openai", "gpt-6-luna", outils), TOUT, SETTINGS, jeton)
    assert modele.bound.use_responses_api is True
    assert modele.kwargs["tools"] == [
        {"type": "web_search"},
        {"type": "mcp", "server_label": "hellopro", "server_url": "https://mcp.test/mcp",
         "require_approval": "never", "headers": {"Authorization": "Bearer jwt-test"},
         "allowed_tools": ["bdd_query_readonly"]},
    ]


def test_anthropic_recherche_et_mcp_natifs():
    outils = {"recherche_web": {"max": 3}, "mcp": {}}
    modele = construire_modele(fiche("anthropic", "claude-haiku-4-5", outils), TOUT, SETTINGS, jeton)
    assert modele.kwargs["tools"] == [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": 3},
        {"type": "mcp_toolset", "mcp_server_name": "hellopro"},
    ]
    assert modele.bound.mcp_servers == [
        {"type": "url", "url": "https://mcp.test/mcp", "name": "hellopro", "authorization_token": "jwt-test"}]


def test_gemini_recherche_google_native():
    modele = construire_modele(fiche("gemini", "gemini-3.5-flash-lite", {"recherche_web": {"max": 5}}),
                               RECHERCHE_SEULE, SETTINGS)
    assert modele.kwargs["tools"][0]["google_search"] is not None


def test_gemini_mcp_refuse_tant_que_non_confirme():
    with pytest.raises(ErreurConfiguration, match="MCP natif indisponible"):
        construire_modele(fiche("gemini", "gemini-3.5-flash-lite", {"mcp": {}}), RECHERCHE_SEULE, SETTINGS, jeton)


def test_deepseek_sans_outils():
    assert isinstance(construire_modele(fiche("deepseek", "deepseek-flash"), AUCUN, SETTINGS), ChatDeepSeek)


def test_deepseek_recherche_refusee():
    with pytest.raises(ErreurConfiguration, match="recherche web native indisponible"):
        construire_modele(fiche("deepseek", "deepseek-flash", {"recherche_web": {"max": 5}}), AUCUN, SETTINGS)


def test_mcp_sans_gateway_configuree_refuse():
    sans_gateway = Settings(OPENAI_API_KEY="sk-test", MCP_GATEWAY_URL="")
    with pytest.raises(ErreurConfiguration, match="gateway MCP"):
        construire_modele(fiche("openai", "gpt-6-luna", {"mcp": {}}), TOUT, sans_gateway, jeton)


def test_fournisseur_inconnu_refuse():
    with pytest.raises(ErreurConfiguration, match="fournisseur inconnu"):
        construire_modele(fiche("mistral", "mistral-large"), AUCUN, SETTINGS)


def test_aucune_relance_des_sdk_le_graphe_gere_les_relances():
    # Les relances internes des SDK (jusqu'à 6 chez Gemini) dépasseraient le budget de 300 s du curl PHP.
    recherche = {"recherche_web": {"max": 5}}
    modeles = [
        construire_modele(fiche("openai", "gpt-6-luna", recherche), TOUT, SETTINGS).bound,
        construire_modele(fiche("anthropic", "claude-haiku-4-5", recherche), TOUT, SETTINGS).bound,
        construire_modele(fiche("gemini", "gemini-3.5-flash-lite", recherche), RECHERCHE_SEULE, SETTINGS).bound,
        construire_modele(fiche("deepseek", "deepseek-flash"), AUCUN, SETTINGS),
    ]
    assert [m.max_retries for m in modeles] == [0, 0, 0, 0]
