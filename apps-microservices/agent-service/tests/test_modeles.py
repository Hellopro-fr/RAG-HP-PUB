import pytest
from langchain_deepseek import ChatDeepSeek

from app.core.config import Settings
from app.core.gemini import ChatGemini
from app.core.modeles import ErreurConfiguration, construire_modele

SETTINGS = Settings(OPENAI_API_KEY="sk-test", ANTHROPIC_API_KEY="sk-test", GEMINI_API_KEY="g-test",
                    DEEPSEEK_API_KEY="sk-test", MCP_GATEWAY_URL="https://mcp.test")
TOUT = {"recherche_web": 1, "mcp": 1, "lecture_pages": 1}
RECHERCHE_SEULE = {"recherche_web": 1, "mcp": 0, "lecture_pages": 0}
GEMINI = {"recherche_web": 1, "mcp": 0, "lecture_pages": 1}
AUCUN = {"recherche_web": 0, "mcp": 0, "lecture_pages": 0}


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


def test_gemini_recherche_et_lecture_de_pages_natives():
    outils = {"recherche_web": {"max": 5}, "lecture_pages": {}}
    modele = construire_modele(fiche("gemini", "gemini-3.1-flash-lite", outils), GEMINI, SETTINGS)
    assert isinstance(modele.bound, ChatGemini)
    assert [sorted(k for k, v in outil.items() if v is not None) for outil in modele.kwargs["tools"]] == [
        ["google_search"], ["url_context"]]


def test_gemini_sans_outil_modele_seul():
    assert type(construire_modele(fiche("gemini", "gemini-3.1-flash-lite"), GEMINI, SETTINGS)) is ChatGemini


def test_anthropic_lecture_de_pages_web_fetch():
    modele = construire_modele(fiche("anthropic", "claude-haiku-4-5", {"lecture_pages": {}}), TOUT, SETTINGS)
    assert modele.kwargs["tools"] == [{"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 5}]


def test_openai_lecture_de_pages_contexte_de_recherche_eleve():
    # Pas d'outil de lecture séparé chez OpenAI : web_search remonte plus de contenu des pages
    outils = {"recherche_web": {"max": 5}, "lecture_pages": {}}
    modele = construire_modele(fiche("openai", "gpt-6-luna", outils), TOUT, SETTINGS)
    assert modele.kwargs["tools"] == [{"type": "web_search", "search_context_size": "high"}]


def test_openai_lecture_de_pages_sans_recherche_refusee():
    with pytest.raises(ErreurConfiguration, match="recherche web"):
        construire_modele(fiche("openai", "gpt-6-luna", {"lecture_pages": {}}), TOUT, SETTINGS)


def test_lecture_de_pages_refusee_sans_la_capacite():
    # Capacité absente de la fiche (modèle sans recherche) ; DeepSeek : aucun outil
    for fournisseur, nom in (("openai", "gpt-6-luna"), ("deepseek", "deepseek-flash")):
        with pytest.raises(ErreurConfiguration, match="lecture de pages native indisponible"):
            construire_modele(fiche(fournisseur, nom, {"lecture_pages": {}}), RECHERCHE_SEULE, SETTINGS)


def test_gemini_mcp_refuse_tant_que_non_confirme():
    with pytest.raises(ErreurConfiguration, match="MCP natif indisponible"):
        construire_modele(fiche("gemini", "gemini-3.5-flash-lite", {"mcp": {}}), GEMINI, SETTINGS, jeton)


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


SANS_OUTIL = (("openai", "gpt-6-luna"), ("anthropic", "claude-haiku-4-5"),
              ("gemini", "gemini-2.5-flash"), ("deepseek", "deepseek-flash"))


def test_temperature_null_ou_absente_non_envoyee():
    # gemini-2.5 : ChatGoogleGenerativeAI mettrait 0.7 par défaut si la température n'était pas passée
    for fournisseur, nom in SANS_OUTIL:
        for modele in ({"fournisseur": fournisseur, "nom": nom, "temperature": None},
                       {"fournisseur": fournisseur, "nom": nom}):
            llm = construire_modele({"modele": modele, "outils": {}}, AUCUN, SETTINGS)
            assert llm.temperature is None, (fournisseur, modele)


def test_temperature_de_la_fiche_transmise():
    for fournisseur, nom in SANS_OUTIL:
        modele = {"fournisseur": fournisseur, "nom": nom, "temperature": 0.3}
        assert construire_modele({"modele": modele, "outils": {}}, AUCUN, SETTINGS).temperature == 0.3


AVEC_RAISONNEMENT = {"recherche_web": 1, "mcp": 0, "lecture_pages": 1, "raisonnement": 1}


def test_effort_de_raisonnement_transmis_aux_trois_fournisseurs():
    # reasoning_effort : reasoning.effort (OpenAI), output_config.effort (Anthropic), thinking_level (Gemini)
    for fournisseur, nom in (("openai", "gpt-6-luna"), ("anthropic", "claude-sonnet-5"), ("gemini", "gemini-3.1-flash-lite")):
        modele = {"fournisseur": fournisseur, "nom": nom, "raisonnement": "high"}
        llm = construire_modele({"modele": modele, "outils": {}}, AVEC_RAISONNEMENT, SETTINGS)
        assert llm.reasoning_effort == "high", fournisseur


def test_sans_effort_de_raisonnement_rien_n_est_impose():
    llm = construire_modele(fiche("openai", "gpt-6-luna"), AVEC_RAISONNEMENT, SETTINGS)
    assert llm.reasoning_effort is None


def test_effort_de_raisonnement_refuse_sans_la_capacite():
    modele = {"fournisseur": "deepseek", "nom": "deepseek-flash", "raisonnement": "high"}
    with pytest.raises(ErreurConfiguration, match="effort de raisonnement"):
        construire_modele({"modele": modele, "outils": {}}, AUCUN, SETTINGS)


def test_aucune_relance_des_sdk():
    # Les relances internes des SDK dépasseraient le budget de 300 s du curl PHP.
    # Gemini avec recherche (API Interactions) : un seul appel HTTP, vérifié dans test_gemini.py.
    recherche = {"recherche_web": {"max": 5}}
    modeles = [
        construire_modele(fiche("openai", "gpt-6-luna", recherche), TOUT, SETTINGS).bound,
        construire_modele(fiche("anthropic", "claude-haiku-4-5", recherche), TOUT, SETTINGS).bound,
        construire_modele(fiche("gemini", "gemini-3.1-flash-lite", recherche), GEMINI, SETTINGS).bound,
        construire_modele(fiche("deepseek", "deepseek-flash"), AUCUN, SETTINGS),
    ]
    assert [m.max_retries for m in modeles] == [0, 0, 0, 0]
