import os
from typing import Dict, Any
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):    
    # Model Configuration
    embedding_model_name: str = "dangvantuan/sentence-camembert-large"
    llm_model_name      : str = "TheBloke/deepseek-llm-7b-chat-AWQ"
    
    # # Milvus/Zilliz Configuration
    # zilliz_category_uri: str = os.getenv("ZILLIZ_CATEGORY_URI", "")
    # zilliz_category_api_key: str = os.getenv("ZILLIZ_CATEGORY_API_KEY", "")
    # category_collection_name: str = os.getenv("CATEGORY_COLLECTION_NAME", "classification_produit")
    
    # OpenAI Configuration
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model  : str = "gpt-4o-2024-05-13"
    
    # DeepSeek Configuration
    deepseek_api_key  : str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_model    : str = "deepseek-chat"
    deepseek_base_url: str  = "https://api.deepseek.com"
    
    # Search API URLs
    search_api_url           : str = "http://api-recherche-service:8510"
    external_product_api_url : str = "https://www.hellopro.fr/partenaires_externes/info_produit/get_info_produit.php"
    external_category_api_url: str = "https://www.hellopro.fr/partenaires_externes/info_produit/get_info_categorie.php"
    
    # BGE Reranker
    bge_reranker_model: str = "BAAI/bge-reranker-v2-m3"
    
    # Default Parameters
    default_n_similar   : int = int("DEFAULT_N_SIMILAR", "50")
    default_m_categories: int = int("DEFAULT_M_CATEGORIES", "10")
    default_k_products  : int = int("DEFAULT_K_PRODUCTS", "5")
    
    # Search Parameters
    initial_search_k: int = 20
    final_top_k: int = 5

    def get_config_dict(self) -> Dict[str, Any]:
        """Retourne la configuration sous forme de dictionnaire pour la compatibilité"""
        return {
            'embedding_model': self.embedding_model_name,
            'llm_model'      : self.llm_model_name,
            'openai'         : {
                'api_key': self.openai_api_key,
                'model'  : self.openai_model
            },
            'deepseek': {
                'api_key' : self.deepseek_api_key,
                'model'   : self.deepseek_model,
                'base_url': self.deepseek_base_url
            },
            'chunk_strategies': {
                "fiche_produit": {"chunk_size": 500, "chunk_overlap": 100}
            },
            'search_api_url'           : self.search_api_url,
            'external_product_api_url' : self.external_product_api_url,
            'external_category_api_url': self.external_category_api_url, # NOUVEAU
            'bge_reranker_model'       : self.bge_reranker_model,
            'chunk_strategies'         : {
                "fiche_produit": {"chunk_size": 500, "chunk_overlap": 100}
            }
        }

settings = Settings()