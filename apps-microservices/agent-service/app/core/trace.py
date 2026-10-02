"""Trace des outils natifs d'un appel : recherches, pages lues, appels MCP, sources citées, tokens des outils.

OpenAI et Anthropic : lue dans les blocs standard de LangChain (server_tool_call / server_tool_result / citation).
Gemini (API Interactions) : calculée par ChatGemini et rangée dans response_metadata["trace"].
"""
from langchain_core.messages import AIMessage

NOMS_RECHERCHE = {"web_search", "google_search"}
NOMS_LECTURE = {"web_fetch", "url_context"}
ACTIONS_LECTURE_OPENAI = {"open_page", "find_in_page"}  # actions de web_search_call qui ouvrent une page


def trace_vide() -> dict:
    return {"recherches": [], "pages_lues": [], "appels_mcp": [], "sources": [], "tokens_outils": 0,
            "variables": {}}


def extraire_trace(message: AIMessage) -> dict:
    calculee = (message.response_metadata or {}).get("trace")
    if isinstance(calculee, dict):
        return {**trace_vide(), **calculee}

    trace = trace_vide()
    blocs = message.content_blocks
    resultats = {b.get("tool_call_id"): b for b in blocs if b.get("type") == "server_tool_result"}

    for bloc in blocs:
        if bloc.get("type") == "text":
            for note in bloc.get("annotations") or []:
                source = {"url": note.get("url"), "titre": note.get("title")}
                if note.get("type") == "citation" and source["url"] and source not in trace["sources"]:
                    trace["sources"].append(source)
            continue
        if bloc.get("type") != "server_tool_call":
            continue

        nom = bloc.get("name")
        arguments = bloc.get("args") or {}
        extras = bloc.get("extras") or {}
        resultat = resultats.get(bloc.get("id")) or {}
        erreur = (resultat.get("extras") or {}).get("error")
        statut = "erreur" if resultat.get("status") == "error" or erreur else "ok"

        if nom in NOMS_RECHERCHE and arguments.get("type") in ACTIONS_LECTURE_OPENAI:
            trace["pages_lues"].append({"url": arguments.get("url"), "statut": statut})
        elif nom in NOMS_RECHERCHE:
            requetes = arguments.get("queries") or [arguments.get("query")]
            trace["recherches"].extend({"requete": r} for r in requetes if r)
        elif nom in NOMS_LECTURE:
            trace["pages_lues"].append({"url": arguments.get("url"), "statut": statut})
        elif nom == "remote_mcp":
            trace["appels_mcp"].append({
                "serveur": extras.get("server_label") or extras.get("server_name"),
                "outil": extras.get("tool_name"),
                "arguments": arguments,
                "statut": statut,
                "erreur": erreur,
            })
    return trace


def additionner_trace(a: dict, b: dict) -> dict:
    somme = {cle: list(a.get(cle) or []) + list(b.get(cle) or [])
             for cle in ("recherches", "pages_lues", "appels_mcp", "sources")}
    somme["tokens_outils"] = int(a.get("tokens_outils") or 0) + int(b.get("tokens_outils") or 0)
    somme["variables"] = {**(a.get("variables") or {}), **(b.get("variables") or {})}
    return somme
