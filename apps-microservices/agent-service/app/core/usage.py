"""Consommation d'un appel modèle : tokens et nombre de recherches web natives."""
from langchain_core.messages import AIMessage

NOMS_RECHERCHE = {"web_search", "google_search"}
CLES = ("tokens_entree", "tokens_sortie", "recherches")


def compter_recherches(message: AIMessage) -> int:
    """Recherches exécutées par le fournisseur pendant l'appel.

    OpenAI et Anthropic : blocs standard `server_tool_call` nommés web_search.
    Gemini (grounding) : requêtes distinctes de `web_search_queries`, lues dans les
    annotations des blocs texte et dans `response_metadata["grounding_metadata"]`.
    """
    blocs = message.content_blocks
    nb = sum(1 for b in blocs if b.get("type") == "server_tool_call" and b.get("name") in NOMS_RECHERCHE)
    if nb:
        return nb
    requetes = set()
    for bloc in blocs:
        for annotation in bloc.get("annotations") or []:
            meta = (annotation.get("extras") or {}).get("google_ai_metadata") or {}
            requetes.update(meta.get("web_search_queries") or [])
    grounding = (message.response_metadata or {}).get("grounding_metadata") or {}
    requetes.update(grounding.get("web_search_queries") or [])
    return len(requetes)


def extraire_usage(message: AIMessage) -> dict:
    usage = message.usage_metadata or {}
    return {
        "tokens_entree": int(usage.get("input_tokens") or 0),
        "tokens_sortie": int(usage.get("output_tokens") or 0),
        "recherches": compter_recherches(message),
    }


def additionner_usage(a: dict, b: dict) -> dict:
    return {cle: a.get(cle, 0) + b.get(cle, 0) for cle in CLES}
