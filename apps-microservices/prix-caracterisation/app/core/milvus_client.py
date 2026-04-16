"""
Client Milvus direct (pymilvus) pour la collection `prix`.

Réplique le pattern de apps-microservices/api-rest-milvus/app/core/api_rest_milvus.py
et /app/router/read.py : connexion partagée au niveau module via `connections`,
collection chargée et cachée, query par expression + pagination.

Pas de HTTP — appel direct Milvus (plus rapide, moins de latence que rest_milvus-service).
"""
import logging
from functools import lru_cache
from typing import List, Dict, Any, Optional

from pymilvus import connections, utility, Collection, MilvusException

from common_utils.database.config.settings import Configuration

logger = logging.getLogger(__name__)


# Milvus contraint offset + limit ≤ 16384 par query window
MILVUS_MAX_WINDOW = 16384


# Mapping source string → champ identifiant métier Milvus (miroir ponctuel_flag_milvus.php)
SOURCE_TO_DISTINCT_FIELD = {
    "devis":   "source_chunk_id",
    "message": "id_lead",
    "produit": "id_produit",
    "siteweb": "source_chunk_id",
}


# Mapping source string → TINYINT pour table _cppi (schéma caracterisation_prix_produit_ia)
SOURCE_STRING_TO_TINYINT = {
    "devis":   1,
    "message": 2,
    "produit": 3,
    "siteweb": 4,
}


# Champs à récupérer depuis la collection `prix` (identifiants + contexte produit + toutes infos prix)
MILVUS_PRIX_FIELDS = [
    "id",
    # Identifiants source
    "id_produit",
    "id_lead",
    "source_chunk_id",
    "source",
    # Contexte produit
    "nom_produit",
    "description_produit",
    "caracteristique",
    "id_categorie",
    "nom_categorie",
    # Fournisseur
    "id_fournisseur",
    "fournisseur",
    "id_societe_ia",
    # Infos prix (injectées dans {DESCRIPTIF_CATEGORIE} au moment de l'appel LLM)
    "valeur_prix",
    "devise",
    "taxe",
    "unite",
    "prix_original",
    "structure_prix",
    "type_transaction",
    "perimetre",
    "valeur_reponse_q1",
    "date_prix",
    # Texte embed (fallback description)
    "text",
    # Chunk ordering (1..n quand un texte est découpé en plusieurs embeddings)
    "chunk_id",
]


# ======================================================================
# Connexion Milvus (partagée au niveau module — pattern api-rest-milvus)
# ======================================================================

def _ensure_milvus_connection(alias: str = "default") -> None:
    """Connecte à Milvus via les env ZILLIZ_* si la connexion n'existe pas déjà."""
    if connections.has_connection(alias):
        return
    config = Configuration()
    logger.info(f"Connexion Milvus (alias={alias})...")
    connections.connect(
        alias,
        host=config.ZILLIZ_URI,
        port=config.ZILLIZ_PORT,
        user=config.ZILLIZ_USER,
        password=config.ZILLIZ_PASSWORD,
    )
    logger.info("Connecté à Milvus.")


@lru_cache(maxsize=16)
def _get_cached_collection(collection_name: str) -> Collection:
    """Collection pymilvus cachée par nom (évite de recréer l'objet à chaque query)."""
    return Collection(collection_name)


def _get_loaded_collection(collection_name: str) -> Collection:
    """Retourne une collection chargée en mémoire Milvus (load si nécessaire)."""
    collection = _get_cached_collection(collection_name)
    load_state = utility.load_state(collection_name)
    if str(load_state) != "Loaded":
        logger.info(f"Collection '{collection_name}' not loaded (state={load_state}), loading...")
        collection.load()
    return collection


# ======================================================================
# Client prix
# ======================================================================

class MilvusPrixClient:
    """
    Client pymilvus direct pour la collection `prix`.

    Méthodes synchrones (pymilvus est sync) — à invoquer via `asyncio.to_thread`
    côté consommateur pour rester compatible avec l'event loop.
    """

    COLLECTION = "prix"
    DEFAULT_PAGE_SIZE = 1000

    def __init__(self, page_size: Optional[int] = None):
        self.page_size = page_size or self.DEFAULT_PAGE_SIZE

    # --------------------------------------------------------------
    # Construction expression de filtre (équivalent _build_metadata_expression)
    # --------------------------------------------------------------
    def _build_expr(self, id_categorie: str, source: Optional[str]) -> str:
        """
        Les champs `id_categorie` et `source` de la collection `prix` sont VARCHAR
        → valeur quotée obligatoire.
        """
        expr_parts = [f'id_categorie == "{id_categorie}"']
        if source:
            expr_parts.append(f'source == "{source}"')
        return " and ".join(expr_parts)

    def _query_page(
        self,
        collection: Collection,
        expr: str,
        fields: List[str],
        limit: int,
        offset: int,
    ) -> List[Dict[str, Any]]:
        try:
            return collection.query(
                expr=expr,
                output_fields=fields,
                limit=limit,
                offset=offset,
                consistency_level="Bounded",
            )
        except MilvusException as e:
            logger.error(
                f"Milvus query error (expr={expr}, offset={offset}, limit={limit}): {e}"
            )
            raise

    # --------------------------------------------------------------
    # API publique
    # --------------------------------------------------------------
    def search_prix(
        self,
        id_categorie: str,
        source: Optional[str] = None,
        fields: Optional[List[str]] = None,
        page_size: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Récupère tous les points de la collection `prix` pour (id_categorie, source?)
        via pagination offset/limit (Milvus impose offset+limit ≤ 16384).

        Args:
            id_categorie: ID catégorie (stocké en VARCHAR dans Milvus)
            source:       Filtre optionnel : devis | message | produit | siteweb
            fields:       Liste de champs à retourner (défaut = MILVUS_PRIX_FIELDS)
            page_size:    Taille de page Milvus (défaut 1000)

        Returns:
            Liste de dicts ; 1 élément = 1 point Milvus avec les champs demandés.

        Note:
            Méthode synchrone — enveloppée par asyncio.to_thread côté consommateur.
            Si plus de 16384 points pour (categorie, source), les suivants ne sont
            PAS récupérés (log WARNING). À ce jour les catégories ont ~360 prix en
            moyenne, on est très en-dessous du plafond.
        """
        _ensure_milvus_connection()
        fields = fields or MILVUS_PRIX_FIELDS
        page = page_size or self.page_size

        if not utility.has_collection(self.COLLECTION):
            logger.warning(f"Collection '{self.COLLECTION}' absente dans Milvus — retour vide")
            return []

        collection = _get_loaded_collection(self.COLLECTION)
        expr = self._build_expr(str(id_categorie), source)

        all_items: List[Dict[str, Any]] = []
        offset = 0

        while True:
            if offset >= MILVUS_MAX_WINDOW:
                logger.warning(
                    f"Milvus pagination cap atteint (offset={offset} ≥ {MILVUS_MAX_WINDOW}) — "
                    f"id_categorie={id_categorie} source={source or '*'}. "
                    f"Les résultats au-delà ne sont pas récupérés."
                )
                break

            # Borner limit pour respecter offset+limit ≤ 16384
            remaining_window = MILVUS_MAX_WINDOW - offset
            limit = min(page, remaining_window)

            items = self._query_page(collection, expr, fields, limit, offset)

            if not items:
                break

            all_items.extend(items)

            if len(items) < limit:
                break  # dernière page

            offset += limit

        logger.info(
            f"Milvus `prix` : {len(all_items)} point(s) récupérés "
            f"(id_categorie={id_categorie}, source={source or '*'})"
        )
        return all_items

    async def close(self):
        """Noop — la connexion Milvus est partagée au niveau module (pas de close par client)."""
        return
