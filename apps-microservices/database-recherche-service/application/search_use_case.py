from infrastructure.milvus_client import MilvusClient
from domain.search_result import SearchResultEntity
from typing import List, Optional


class SearchUseCase:
    def __init__(self, db_client: MilvusClient):
        self.db_client = db_client

    # MODIFIÉ: La signature de la méthode est mise à jour
    def execute_search(
        self,
        collection_name: str,
        vector: List[float],
        top_k: int,
        filter_expression: Optional[str] = None,
        output_fields: Optional[List[str]] = None,
        context_mode: Optional[str] = None,
    ) -> List[SearchResultEntity]:

        # Préparation des kwargs pour le client Milvus
        search_kwargs = {}
        if filter_expression:
            search_kwargs["expr"] = filter_expression
        if output_fields:
            search_kwargs["output_fields"] = output_fields
        search_kwargs["context_mode"] = context_mode

        return self.db_client.search(collection_name, vector, top_k, **search_kwargs)

    def get_collection_schema(self, collection_name: str) -> dict[str, str]:
        """
        Cas d'utilisation pour récupérer le schéma d'une collection.
        """
        return self.db_client.get_field_type_map(collection_name)

    def execute_classic_search(
        self,
        collection_name: str,
        filter_expression: str,
        top_k: int,
        output_fields: Optional[List[str]] = None,
    ) -> List[SearchResultEntity]:
        """
        Cas d'utilisation pour exécuter une recherche classique par filtre.
        """
        return self.db_client.classic_search(
            collection_name=collection_name,
            expr=filter_expression,
            limit=top_k,
            output_fields=output_fields,
        )

    def execute_hybrid_search(
        self,
        collection_name: str,
        dense_vector: List[float],
        query_text: str,
        top_k: int,
        dense_weight: float = 0.7,
        sparse_weight: float = 0.3,
        filter_expression: Optional[str] = None,
        output_fields: Optional[List[str]] = None,
        context_mode: Optional[str] = None,
    ) -> List[SearchResultEntity]:
        """
        Cas d'utilisation pour exécuter une recherche hybride (dense + full-text BM25).
        """
        search_kwargs = {}
        if filter_expression:
            search_kwargs["expr"] = filter_expression
        if output_fields:
            search_kwargs["output_fields"] = output_fields
        search_kwargs["context_mode"] = context_mode

        return self.db_client.hybrid_search(
            collection_name=collection_name,
            dense_vector=dense_vector,
            query_text=query_text,
            top_k=top_k,
            dense_weight=dense_weight,
            sparse_weight=sparse_weight,
            **search_kwargs
        )
