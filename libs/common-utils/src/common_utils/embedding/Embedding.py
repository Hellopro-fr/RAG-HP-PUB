import os
import time
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from logging.handlers import TimedRotatingFileHandler

# from sentence_transformers import SentenceTransformer
# from langchain_text_splitters import RecursiveCharacterTextSplitter

# from transformers import AutoTokenizer # pour encoder du modèle d'embedding

import re
from common_utils.grpc_clients import embedding_client

# --- CONFIGURATION ---


os.makedirs(f'/logs', exist_ok=True)

file_handler = TimedRotatingFileHandler(
    filename="/logs/embeddings.log",
    when='midnight',  # Rotate at midnight
    interval=1,       # Rotate every day
    backupCount=30,   # Keep 30 days of logs
    encoding='utf-8'
)

# Handler pour les logs de temps
time_handler = TimedRotatingFileHandler(
    filename="/logs/temps_embedding.log",
    when='midnight',
    interval=1,
    backupCount=30,
    encoding='utf-8'
)

console_handler = logging.StreamHandler()

log_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(log_format)
time_handler.setFormatter(log_format)
console_handler.setFormatter(log_format)


logger = logging.getLogger("embedding")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)
logger.propagate = False

time_logger = logging.getLogger("embedding_time")
time_logger.setLevel(logging.INFO)
time_logger.addHandler(time_handler)
time_logger.addHandler(console_handler)
time_logger.propagate = False

@dataclass
class Config:
    BATCH_SIZE: int = 64 # Réduit pour les schémas plus complexes si la mémoire est un problème
    DEFAULT_CHUNK_STRATEGY: Dict[str, int] = field(default_factory=lambda: {"chunk_size": 500, "chunk_overlap": 100})
    CHUNK_STRATEGIES: Dict[str, Dict[str, int]] = field(default_factory=lambda: {
        "fiche_produit": {"chunk_size": 500, "chunk_overlap": 100},  # ~350 tokens, 115 overlap
        "home": {"chunk_size": 500, "chunk_overlap": 100},
        "listing_produit": {"chunk_size": 500, "chunk_overlap": 100},
        "fiche_realisation": {"chunk_size": 500, "chunk_overlap": 100},
        "Presentation-societe": {"chunk_size": 500, "chunk_overlap": 100},
        "contact": {"chunk_size": 500, "chunk_overlap": 100},
        "cgv_mentions_legales_cgu": {"chunk_size": 500, "chunk_overlap": 100},
        "article": {"chunk_size": 500, "chunk_overlap": 100},
        "Savoir_faire": {"chunk_size": 500, "chunk_overlap": 100},
        "Page_local": {"chunk_size": 500, "chunk_overlap": 100},
        "demande_devis": {"chunk_size": 500, "chunk_overlap": 100},
        "compte_client": {"chunk_size": 500, "chunk_overlap": 100},
        "recrutement": {"chunk_size": 500, "chunk_overlap": 100},
        "references_clients": {"chunk_size": 500, "chunk_overlap": 100},
        "faq": {"chunk_size": 500, "chunk_overlap": 100},
        "plan_du_site": {"chunk_size": 500, "chunk_overlap": 100},
        "politique_confidentialite": {"chunk_size": 500, "chunk_overlap": 100},
        "autre": {"chunk_size": 500, "chunk_overlap": 100}
    })

class Embedding:
    def __init__(self, model_name: str = "dangvantuan/sentence-camembert-large", config: Config = Config(),**kwargs):
        self.config = config
        self.model_name = model_name
        self.logger = kwargs.get("logger",logger)
        self.time_logger = kwargs.get("time_logger", time_logger)
        
        # self.tokenizer = kwargs.get("tokenizer") if kwargs.get("tokenizer") else None
        
        # try:
        #     self.logger.info(f"Chargement du tokenizer pour le chunking: {self.model_name}")
        #     # self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        #     self.logger.info("Tokenizer chargé avec succès.")
        # except Exception as e:
        #     self.logger.error(f"Failed to load model '{self.model_name}': {e}", exc_info=True)
        #     self.model = None # Ensure model is None if loading fails
            # You might want to raise the exception here to stop the service from starting
            # raise e
    

    def _append_time_log(self, elapsed: float):
        """Ajoute une ligne avec le temps d’exécution dans temps_embedding.log"""
        log_path = "/logs/temps_embedding.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"total_time: {elapsed:.4f}s\n")

    async def embed(self, sentences: list[str]) -> list[list[float]]:
        # if not self.model:
        #     self.logger.error("Modèle non chargé, impossible de vectoriser les données.")
        #     # Return an empty list of the correct shape or handle the error appropriately
        #     return [[] for _ in sentences]
        
        if not sentences:
            return []
        
        start_time = time.perf_counter()
        # The model is already loaded, just use it.
        # Note: We now process a list of sentences for better batching.
        try:
            vectors = await embedding_client.get_embeddings(sentences)
            
            if not vectors or len(vectors) != len(sentences):
                self.logger.error("Le service d'embedding a retourné un nombre incorrect de vecteurs.")
                # Retourner une structure de données cohérente en cas d'erreur
                return [[] for _ in sentences]
            # vector = self.model.encode(
            #     sentences,
            #     show_progress_bar=False,
            #     normalize_embeddings=True,
            #     batch_size=self.config.BATCH_SIZE
            # ).tolist()
        except Exception as e:
            self.logger.error(f"Erreur lors de l'encodage des phrases: {e}", exc_info=True)
            raise

        elapsed = time.perf_counter() - start_time

        # Sauvegarde des stats dans le fichier (en écrasant le contenu)
        self._append_time_log(elapsed)

        return vectors
    

    ### FONCTION MODIFIÉE AVEC CORRECTION D'ENCODAGE ###
    @staticmethod
    def _clean_text(text: Any) -> str:
        """
        Nettoie une chaîne de texte en normalisant les espaces et en corrigeant
        les problèmes d'encodage courants (mojibake).
        """
        if not isinstance(text, str):
            return ""

        cleaned_text = text
        # Étape 1 : Tenter de corriger les problèmes d'encodage (ex: UTF-8 lu comme Latin-1)
        try:
            # Cette astuce encode la chaîne mal interprétée en bytes en utilisant
            # l'encodage "source" erroné (latin-1), puis la décode correctement en UTF-8.
            # Si la chaîne était déjà correcte, cette opération peut lever une erreur.
            encoded_bytes = cleaned_text.encode('latin-1')
            decoded_text = encoded_bytes.decode('utf-8')
            
            # On applique la correction uniquement si elle ne produit pas de caractères de remplacement '�'
            # qui indiquent un échec de décodage.
            if '�' not in decoded_text:
                cleaned_text = decoded_text
                
        except (UnicodeEncodeError, UnicodeDecodeError):
            # Si une erreur se produit, cela signifie que la chaîne était probablement
            # déjà dans le bon format. On continue avec le texte original.
            pass

        # Étape 2 : Normaliser les espaces (comme avant)
        return re.sub(r'\s+', ' ', cleaned_text).strip()

    async def _create_chunks(self, text: str, template: str) -> List[str]:
        """
        Délègue le chunking au microservice d'embedding.
        """
        # await self._ensure_model_info()

        strategy = self.config.CHUNK_STRATEGIES.get(template, self.config.DEFAULT_CHUNK_STRATEGY)
        
        # On valide la taille du chunk par rapport au contexte du modèle
        chunk_size = strategy["chunk_size"]
        chunk_overlap = strategy["chunk_overlap"]

        # Un seul appel gRPC pour faire tout le travail de chunking.
        return await embedding_client.chunk_text(text, chunk_size, chunk_overlap)

    async def embed_data_clean(self, data_to_embed: Dict[str, Any]) -> List[Dict[str, Any]]:
        batch_to_insert = []
        
        if not data_to_embed.get("text",""):
            self.logger.warning(f"Le texte à vectoriser est vide")
            self.logger.warning(f"Data: {data_to_embed}")
            return []
        
        data_clean = self._clean_text(data_to_embed.get("text", ""))
        
        if not data_clean:
            self.logger.warning(f"Le texte à vectoriser est vide après nettoyage")
            self.logger.warning(f"Data: {data_clean}")
            return []

        # Vérifier si le type de page est renseigné
        chunks = await self._create_chunks(data_clean, data_to_embed.get("type_page", "autre"))
        
        if not chunks:
            self.logger.warning(f"Aucun chunk créé pour le texte donné.")
            # self.logger.warning(f"Data: {data_clean}")
            return []
        
        try:
            all_embeddings = await self.embed(chunks)
            
            total_chunks = len(chunks)
            
            for i, (chunk_text, chunk_embedding) in enumerate(zip(chunks, all_embeddings)):
                if not chunk_embedding:
                    self.logger.warning(f"Chunk {i+1}/{total_chunks} n'a pas pu être vectorisé. Il sera ignoré.")
                    continue
                
                data_tmp = data_to_embed.copy()
                data_tmp.pop("text", None)
                
                data_tmp["embedding"] = chunk_embedding
                data_tmp["text"] = chunk_text
                data_tmp["chunk_id"] = str(i + 1)
                data_tmp["chunk_number"] = i + 1
                data_tmp["total_chunks"] = total_chunks
                
                batch_to_insert.append(data_tmp)
        except Exception as e:
            self.logger.error(f"Erreur lors de la création des chunks: {e}", exc_info=True)
            raise

        return batch_to_insert