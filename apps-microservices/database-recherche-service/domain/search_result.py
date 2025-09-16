from dataclasses import dataclass

@dataclass
class SearchResultEntity:
    """
    Entité du domaine représentant un résultat de recherche.
    Cette abstraction empêche la logique applicative de dépendre directement
    de la structure de réponse de Milvus.
    """
    id: str
    score: float
    metadata: dict
    source: str