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
        output_fields: Optional[List[str]] = None
    ) -> List[SearchResultEntity]:
        
        # Préparation des kwargs pour le client Milvus
        search_kwargs = {}
        if filter_expression:
            search_kwargs['expr'] = filter_expression
        if output_fields:
            search_kwargs['fields'] = output_fields

        return self.db_client.search(collection_name, vector, top_k, **search_kwargs)
    
    def get_collection_schema(
        self, 
        collection_name: str
    ) -> dict[str, str]:
        """
        Cas d'utilisation pour récupérer le schéma d'une collection.
        """
        return self.db_client.get_field_type_map(collection_name)