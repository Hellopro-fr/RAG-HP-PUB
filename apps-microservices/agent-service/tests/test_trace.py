from langchain_core.messages import AIMessage

from app.core.trace import additionner_trace, extraire_trace, trace_vide


def test_trace_openai_recherche_page_ouverte_mcp_et_sources():
    # Blocs standard de LangChain pour l'API Responses (web_search_call, mcp_call, url_citation)
    message = AIMessage(content=[
        {"type": "server_tool_call", "name": "web_search", "id": "ws_1",
         "args": {"type": "search", "query": "sol-equestre.fr siret"}},
        {"type": "server_tool_result", "tool_call_id": "ws_1", "status": "success"},
        {"type": "server_tool_call", "name": "web_search", "id": "ws_2",
         "args": {"type": "open_page", "url": "https://www.sol-equestre.fr/mentions"}},
        {"type": "server_tool_result", "tool_call_id": "ws_2", "status": "error"},
        {"type": "server_tool_call", "name": "remote_mcp", "id": "mcp_1", "args": {"siren": "478934011"},
         "extras": {"tool_name": "fiche_societe", "server_label": "hellopro"}},
        {"type": "server_tool_result", "tool_call_id": "mcp_1", "extras": {"error": "outil indisponible"}},
        {"type": "text", "text": "47893401100030", "annotations": [
            {"type": "citation", "url": "https://www.pappers.fr/x", "title": "Pappers"},
            {"type": "citation", "url": "https://www.pappers.fr/x", "title": "Pappers"}]},
    ])
    trace = extraire_trace(message)
    assert trace["recherches"] == [{"requete": "sol-equestre.fr siret"}]
    assert trace["pages_lues"] == [{"url": "https://www.sol-equestre.fr/mentions", "statut": "erreur"}]
    assert trace["appels_mcp"] == [{"serveur": "hellopro", "outil": "fiche_societe", "arguments": {"siren": "478934011"},
                                    "statut": "erreur", "erreur": "outil indisponible"}]
    assert trace["sources"] == [{"url": "https://www.pappers.fr/x", "titre": "Pappers"}]


def test_trace_anthropic_web_search_web_fetch_et_mcp():
    message = AIMessage(content=[
        {"type": "server_tool_call", "name": "web_search", "id": "s1", "args": {"query": "altec france siren"}},
        {"type": "server_tool_call", "name": "web_fetch", "id": "f1", "args": {"url": "https://www.dechargement.com/"}},
        {"type": "server_tool_result", "tool_call_id": "f1", "status": "success"},
        {"type": "server_tool_call", "name": "remote_mcp", "id": "m1", "args": {},
         "extras": {"tool_name": "bdd_query_readonly", "server_name": "hellopro"}},
        {"type": "server_tool_result", "tool_call_id": "m1", "status": "success"},
        {"type": "text", "text": "392807160"},
    ])
    trace = extraire_trace(message)
    assert trace["recherches"] == [{"requete": "altec france siren"}]
    assert trace["pages_lues"] == [{"url": "https://www.dechargement.com/", "statut": "ok"}]
    assert trace["appels_mcp"][0]["serveur"] == "hellopro" and trace["appels_mcp"][0]["statut"] == "ok"


def test_trace_gemini_deja_calculee_par_chat_gemini():
    calculee = {**trace_vide(), "recherches": [{"requete": "q"}], "tokens_outils": 1200}
    assert extraire_trace(AIMessage(content="x", response_metadata={"trace": calculee})) == calculee


def test_trace_vide_sans_outil_et_addition():
    assert extraire_trace(AIMessage(content="12345678900012")) == trace_vide()
    a = {**trace_vide(), "recherches": [{"requete": "a"}], "tokens_outils": 10, "variables": {"pays": "FR"}}
    b = {**trace_vide(), "recherches": [{"requete": "b"}], "tokens_outils": 5}
    somme = additionner_trace(a, b)
    assert somme["recherches"] == [{"requete": "a"}, {"requete": "b"}]
    assert somme["tokens_outils"] == 15 and somme["variables"] == {"pays": "FR"}
