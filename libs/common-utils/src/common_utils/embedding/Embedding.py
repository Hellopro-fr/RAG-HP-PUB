import os
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from logging.handlers import TimedRotatingFileHandler
import torch

from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter

import re

# --- CONFIGURATION ---


os.makedirs(f'/logs', exist_ok=True)

file_handler = TimedRotatingFileHandler(
    filename="/logs/embeddings.log",
    when='midnight',  # Rotate at midnight
    interval=1,       # Rotate every day
    backupCount=30,   # Keep 30 days of logs
    encoding='utf-8'
)

console_handler = logging.StreamHandler()

log_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(log_format)
console_handler.setFormatter(log_format)


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)
logger.propagate = False

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
        self.model: Optional[SentenceTransformer] = None
        self.model_name = model_name
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.logger = kwargs.get("logger",logger)

    
    def embed(self, sentences: str) -> list[list[float]]:
        self.logger.info(f"Utilisation du modèle d'embedding : {self.model_name}")
        self.logger.info(f"Device utilisé pour l'embedding : {self.device}")

        self.model = SentenceTransformer(self.model_name, device=self.device)

        return self.model.encode(
            [sentences], 
            show_progress_bar=False, 
            normalize_embeddings=True, 
            batch_size=self.config.BATCH_SIZE
        ).tolist()

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

    def _create_chunks(self, text: str, template: str) -> List[str]:
        strategy = self.config.CHUNK_STRATEGIES.get(template, self.config.DEFAULT_CHUNK_STRATEGY)
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=strategy["chunk_size"], chunk_overlap=strategy["chunk_overlap"],
            length_function=len, separators=["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""]
        )
        return text_splitter.split_text(text)

    ### MODIFIED ###
    def embed_data_clean(self, data_to_embed: Dict[str, Any]) -> List[Dict[str, Any]]:
        batch_to_insert = []

        data_clean = self._clean_text(data_to_embed.get("text", ""))

        self.logger.info(f"Le texte à vectoriser : {data_clean}")


        if not data_to_embed.get("text",""):
            self.logger.warning(f"Le texte à vectoriser est vide")
            self.logger.warning(f"Data: {data_to_embed}")
            return []

        # Todo: Vérifier si le type de page est renseigné
        chunks = self._create_chunks(data_clean, data_to_embed.get("type_page", "autre"))
        if not chunks:
            chunks = [data_clean] # Assurer qu'il y a au moins un chunk

        for i, data in enumerate(chunks):
        
            chunk_id = str(i + 1)

            try:
                embeddings = self.embed(data)
                
                data_tmp = data_to_embed.copy()

                data_tmp.pop("text",None)

                data_tmp["embedding"] = embeddings[0]
                data_tmp["text"] = data  
                data_tmp["chunk_id"] = chunk_id  
                data_tmp["chunk_number"] = i + 1 
                data_tmp["total_chunks"] = len(chunks)
                data_tmp["metadata"]["chunk_id"] = chunk_id  # Ajout du texte original du chunk 
                data_tmp["metadata"]["chunk_number"] = i + 1 
                data_tmp["metadata"]["total_chunks"] = len(chunks)
                data_tmp["metadata"]["text"] = data
                
                batch_to_insert.append(data_tmp)

                del data_tmp

            except Exception as e:
                self.logger.error(f"Echec d'embedding pour le chunk {chunk_id}: {e}", exc_info=True)
                self.logger.error(f"Data : {data}") 
                return []
            finally:
                self.logger.info(f"Cleaning up resources...")
                del self.model
                self.model = None
                if self.device == 'cuda': torch.cuda.empty_cache()

        return batch_to_insert