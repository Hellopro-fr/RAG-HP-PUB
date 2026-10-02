"""Modèle LangChain d'une fiche, avec les outils natifs de son fournisseur.

Le service n'exécute aucun outil : il les déclare, le fournisseur les exécute pendant
l'appel. Syntaxe vérifiée dans la doc LangChain (doc de décision §6).
"""
from typing import Callable, Optional

from langchain_anthropic import ChatAnthropic
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI

from app.core.config import Settings
from app.core.gemini import ChatGemini

NOM_SERVEUR_MCP = "hellopro"
TYPE_RECHERCHE_ANTHROPIC = "web_search_20260209"
TYPE_LECTURE_ANTHROPIC = "web_fetch_20260209"
MAX_LECTURES_ANTHROPIC = 5  # plafond de pages lues par appel, comme la recherche par défaut


class ErreurConfiguration(Exception):
    """Fiche incompatible : outil non proposé par le modèle, fournisseur inconnu, gateway absente."""


def construire_modele(definition: dict, capacites: dict, settings: Settings,
                      obtenir_jeton_mcp: Optional[Callable[[], str]] = None):
    modele = definition.get("modele") or {}
    fournisseur, nom = modele.get("fournisseur", ""), modele.get("nom", "")
    outils = definition.get("outils") or {}
    recherche, mcp = outils.get("recherche_web"), outils.get("mcp")
    lecture = outils.get("lecture_pages")  # {} dans la fiche : tester `is not None`
    if not nom:
        raise ErreurConfiguration("modèle absent de la fiche")
    if recherche and not capacites.get("recherche_web"):
        raise ErreurConfiguration(f"recherche web native indisponible pour {fournisseur}/{nom}")
    if mcp is not None and not capacites.get("mcp"):
        raise ErreurConfiguration(f"MCP natif indisponible pour {fournisseur}/{nom}")
    if lecture is not None and not capacites.get("lecture_pages"):
        raise ErreurConfiguration(f"lecture de pages native indisponible pour {fournisseur}/{nom}")

    # max_retries=0 : les relances des SDK (6 chez Gemini) dépasseraient le budget de 300 s du curl PHP.
    params = {"timeout": settings.TIMEOUT_MODELE_S, "max_retries": 0}
    if "temperature" in modele:
        params["temperature"] = modele["temperature"]
    autorises = list((mcp or {}).get("outils_autorises") or [])

    if fournisseur == "openai":
        llm = ChatOpenAI(model=nom, api_key=settings.OPENAI_API_KEY, use_responses_api=True, **params)
        liste = [{"type": "web_search"}] if recherche else []
        if mcp is not None:
            outil = {"type": "mcp", "server_label": NOM_SERVEUR_MCP, "server_url": _url_mcp(settings),
                     "require_approval": "never",
                     "headers": {"Authorization": f"Bearer {_jeton(obtenir_jeton_mcp)}"}}
            if autorises:
                outil["allowed_tools"] = autorises
            liste.append(outil)
        return llm.bind_tools(liste) if liste else llm

    if fournisseur == "anthropic":
        options, liste = {}, []
        if recherche:
            liste.append({"type": TYPE_RECHERCHE_ANTHROPIC, "name": "web_search",
                          "max_uses": int(recherche.get("max", 5))})
        if lecture is not None:
            liste.append({"type": TYPE_LECTURE_ANTHROPIC, "name": "web_fetch", "max_uses": MAX_LECTURES_ANTHROPIC})
        if mcp is not None:
            serveur = {"type": "url", "url": _url_mcp(settings), "name": NOM_SERVEUR_MCP,
                       "authorization_token": _jeton(obtenir_jeton_mcp)}
            if autorises:
                serveur["tool_configuration"] = {"enabled": True, "allowed_tools": autorises}
            options["mcp_servers"] = [serveur]
            liste.append({"type": "mcp_toolset", "mcp_server_name": NOM_SERVEUR_MCP})
        llm = ChatAnthropic(model=nom, api_key=settings.ANTHROPIC_API_KEY,
                            max_tokens=int(modele.get("max_tokens", settings.MAX_TOKENS_DEFAUT)),
                            **options, **params)
        return llm.bind_tools(liste) if liste else llm

    if fournisseur == "gemini":
        # ChatGemini : recherche et lecture de pages via l'API Interactions, le reste via generateContent
        llm = ChatGemini(model=nom, google_api_key=settings.GEMINI_API_KEY, **params)
        liste = []
        if recherche:
            liste.append({"google_search": {}})
        if lecture is not None:
            liste.append({"url_context": {}})
        return llm.bind_tools(liste) if liste else llm

    if fournisseur == "deepseek":
        return ChatDeepSeek(model=nom, api_key=settings.DEEPSEEK_API_KEY, **params)

    raise ErreurConfiguration(f"fournisseur inconnu : {fournisseur}")


def _url_mcp(settings: Settings) -> str:
    if not settings.MCP_GATEWAY_URL:
        raise ErreurConfiguration("gateway MCP non configurée (MCP_GATEWAY_URL)")
    return settings.MCP_GATEWAY_URL.rstrip("/") + "/mcp"


def _jeton(obtenir_jeton_mcp: Optional[Callable[[], str]]) -> str:
    if obtenir_jeton_mcp is None:
        raise ErreurConfiguration("gateway MCP non configurée (jeton)")
    return obtenir_jeton_mcp()
