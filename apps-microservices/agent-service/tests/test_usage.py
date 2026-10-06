from langchain_core.messages import AIMessage

from app.core.usage import additionner_usage, compter_recherches, extraire_usage


def test_recherches_openai_anthropic_blocs_server_tool_call():
    message = AIMessage(content=[
        {"type": "server_tool_call", "name": "web_search", "id": "ws_1", "args": {"query": "a"}},
        {"type": "server_tool_result", "tool_call_id": "ws_1", "status": "success"},
        {"type": "server_tool_call", "name": "web_search", "id": "ws_2", "args": {"query": "b"}},
        {"type": "text", "text": "12345678900012"},
    ])
    assert compter_recherches(message) == 2


def test_openai_pages_ouvertes_non_comptees_comme_recherches():
    # OpenAI ne facture que l'action search (doc web search) ; open_page et find_in_page sont gratuites
    message = AIMessage(content=[
        {"type": "server_tool_call", "name": "web_search", "id": "ws_1", "args": {"type": "search", "query": "a"}},
        {"type": "server_tool_call", "name": "web_search", "id": "ws_2",
         "args": {"type": "open_page", "url": "https://www.sol-equestre.fr/mentions"}},
        {"type": "server_tool_call", "name": "web_search", "id": "ws_3",
         "args": {"type": "find_in_page", "url": "https://www.sol-equestre.fr/mentions", "pattern": "SIRET"}},
        {"type": "text", "text": "47893401100030"},
    ])
    assert compter_recherches(message) == 1


def test_appel_mcp_non_compte_comme_recherche():
    message = AIMessage(content=[
        {"type": "server_tool_call", "name": "bdd_query_readonly", "id": "mcp_1", "args": {}},
        {"type": "text", "text": "ok"},
    ])
    assert compter_recherches(message) == 0


def test_recherches_gemini_requetes_distinctes_des_annotations():
    message = AIMessage(content=[{"type": "text", "text": "12345678900012", "annotations": [
        {"type": "citation", "url": "u1", "extras": {"google_ai_metadata": {"web_search_queries": ["q1", "q2"]}}},
        {"type": "citation", "url": "u2", "extras": {"google_ai_metadata": {"web_search_queries": ["q1"]}}},
    ]}])
    assert compter_recherches(message) == 2


def test_recherches_gemini_grounding_metadata():
    message = AIMessage(content="Non trouvé",
                        response_metadata={"grounding_metadata": {"web_search_queries": ["a", "b", "c"]}})
    assert compter_recherches(message) == 3


def test_usage_sans_metadonnees_vaut_zero():
    assert extraire_usage(AIMessage(content="x")) == {"tokens_entree": 0, "tokens_sortie": 0, "recherches": 0}


def test_usage_tokens_et_addition():
    message = AIMessage(content="x", usage_metadata={"input_tokens": 800, "output_tokens": 12, "total_tokens": 812})
    usage = extraire_usage(message)
    assert usage == {"tokens_entree": 800, "tokens_sortie": 12, "recherches": 0}
    assert additionner_usage(usage, usage) == {"tokens_entree": 1600, "tokens_sortie": 24, "recherches": 0}
