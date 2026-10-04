"""Assemblage des dépendances réelles (remplacées dans les tests par dependency_overrides)."""
from functools import lru_cache

from app.core.api_v2 import ClientApiV2
from app.core.config import get_settings
from app.core.execution import Dependances
from app.core.jeton_mcp import JetonMcp
from app.core.modeles import construire_modele


@lru_cache()
def get_dependances() -> Dependances:
    s = get_settings()
    jeton = JetonMcp(s.MCP_GATEWAY_URL, s.MCP_CLIENT_ID, s.MCP_CLIENT_SECRET) if s.MCP_GATEWAY_URL else None
    obtenir = jeton.obtenir if jeton else None
    return Dependances(
        api_v2=ClientApiV2(s.HELLOPRO_API_URL, s.HP_TOKEN, s.TTL_CACHE_FICHE_S),
        fabrique_modele=lambda definition, capacites: construire_modele(definition, capacites, s, obtenir),
    )
