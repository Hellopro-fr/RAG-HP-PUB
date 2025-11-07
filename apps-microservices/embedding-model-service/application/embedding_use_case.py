import logging
import numpy as np
import os
from typing import List
import asyncio
from sentence_transformers import SentenceTransformer
from tritonclient.grpc.aio import InferenceServerClient, InferInput, InferRequestedOutput
import torch
from langchain_text_splitters import RecursiveCharacterTextSplitter
from transformers import AutoTokenizer

TRITON_URL = os.getenv("TRITON_URL", "localhost:8001")
MODEL_NAME = "camembert-embedding"
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "64"))
TOTAL_MAX_CONCURRENT_REQUESTS = int(os.getenv("MAX_CONCURRENT_REQUESTS", "10"))
HIGH_PRIORITY_RATIO = float(os.getenv("HIGH_PRIORITY_RATIO", "0.8"))

# Services considérés comme basse priorité
LOW_PRIORITY_SERVICES = {"embedding-service"}


class EmbeddingUseCase:
    def __init__(self):
        tokenizer_name = "dangvantuan/sentence-camembert-large"
        logging.info(f"Chargement du tokenizer: {tokenizer_name}")
        self.tokenizer = SentenceTransformer(tokenizer_name).tokenizer
        self.tokenizer_pre = AutoTokenizer.from_pretrained(tokenizer_name)
        self.triton_client = InferenceServerClient(url=TRITON_URL)
        self.batch_size = EMBEDDING_BATCH_SIZE
        
        # --- MODIFIÉ: Logique de sémaphore par priorité ---
        high_prio_slots = int(TOTAL_MAX_CONCURRENT_REQUESTS * HIGH_PRIORITY_RATIO)
        low_prio_slots = TOTAL_MAX_CONCURRENT_REQUESTS - high_prio_slots
        # On garantit au moins un slot pour la basse priorité si le total le permet
        if high_prio_slots >= TOTAL_MAX_CONCURRENT_REQUESTS and TOTAL_MAX_CONCURRENT_REQUESTS > 0:
            high_prio_slots = TOTAL_MAX_CONCURRENT_REQUESTS - 1
            low_prio_slots = 1
        if TOTAL_MAX_CONCURRENT_REQUESTS == 0:
            low_prio_slots = 0

        self.high_prio_semaphore = asyncio.Semaphore(high_prio_slots)
        self.low_prio_semaphore = asyncio.Semaphore(low_prio_slots)

        logging.info(f"Taille de batch pour l'embedding configurée à: {self.batch_size}")
        logging.info(f"Total de requêtes concurrentes pour l'embedding: {TOTAL_MAX_CONCURRENT_REQUESTS}")
        logging.info(f"Slots haute priorité: {high_prio_slots} | Slots basse priorité: {low_prio_slots}")
        
    def tokenize_texts(self, texts: List[str]) -> List[List[int]]:
        """
        Tokenize une liste de textes en utilisant le tokenizer du service.
        """
        if not texts:
            return []
        try:
            # On ne veut que les IDs, sans tokens spéciaux pour le comptage de longueur.
            return self.tokenizer(texts, add_special_tokens=False).input_ids
        except Exception as e:
            logging.error(f"Erreur lors de la tokenization: {e}", exc_info=True)
            return [[] for _ in texts]
    
    def detokenize_texts(self, token_lists: List[List[int]]) -> List[str]:
        """
        Décode une liste de listes de tokens en chaînes de caractères.
        """
        if not token_lists:
            return []
        try:
            return self.tokenizer.batch_decode(token_lists, skip_special_tokens=True)
        except Exception as e:
            logging.error(f"Erreur lors de la détokenization: {e}", exc_info=True)
            return ["" for _ in token_lists]

    def mean_pooling(self, model_output, attention_mask):
        token_embeddings = torch.from_numpy(model_output)
        attention_mask = torch.from_numpy(attention_mask)
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1)
        sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
        return (sum_embeddings / sum_mask).numpy()

    async def generate_embeddings(self, texts: List[str], source_service: str | None = None) -> List[List[float]]:
        if not texts:
            return []
        
        # --- Sélection du sémaphore basé sur la source ---
        is_low_priority = source_service in LOW_PRIORITY_SERVICES
        semaphore = self.low_prio_semaphore if is_low_priority else self.high_prio_semaphore
        priority_label = "BASSE" if is_low_priority else "HAUTE"
        
        logging.info(f"Requête d'embedding reçue de '{source_service or 'inconnu'}'. Priorité: {priority_label}.")
        
        async with semaphore:
            all_embeddings = []
            
            try:
                # On itère sur la liste de textes par lots (batches)
                for i in range(0, len(texts), self.batch_size):
                    batch_texts = texts[i:i + self.batch_size]
                    logging.info(f"Traitement du batch d'embedding {i // self.batch_size + 1}/{(len(texts) + self.batch_size - 1) // self.batch_size} avec {len(batch_texts)} textes.")

                    encoded_input = self.tokenizer(
                        batch_texts, padding=True, truncation=True, return_tensors="np", max_length=512
                    )
                    input_ids = encoded_input["input_ids"].astype(np.int64)
                    attention_mask = encoded_input["attention_mask"].astype(np.int64)

                    inputs = [
                        InferInput("input_ids", input_ids.shape, "INT64"),
                        InferInput("attention_mask", attention_mask.shape, "INT64"),
                    ]
                    inputs[0].set_data_from_numpy(input_ids)
                    inputs[1].set_data_from_numpy(attention_mask)

                    # On demande la sortie brute du Transformer
                    outputs = [InferRequestedOutput("last_hidden_state")]

                    response = await self.triton_client.infer(
                        model_name=MODEL_NAME, inputs=inputs, outputs=outputs
                    )

                    last_hidden_state = response.as_numpy("last_hidden_state")
                    
                    # On effectue le pooling manuellement dans le client
                    sentence_embeddings = self.mean_pooling(last_hidden_state, attention_mask)
                    
                    all_embeddings.extend(sentence_embeddings.tolist())
                
                return all_embeddings
                
            except Exception as e:
                logging.error(f"Erreur lors de l'appel à Triton pour l'embedding: {e}", exc_info=True)
                # On propage l'exception pour que le serveur gRPC puisse renvoyer une erreur appropriée.
                raise e
        
    def chunk_text(self, text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
        """
        Découpe un texte en chunks en utilisant le tokenizer du modèle.
        C'est la logique de chunking centralisée.
        """
        if not text:
            return []

        # La fonction de longueur utilise le tokenizer interne au service.
        def hf_length_function(text_to_count: str) -> int:
            return len(self.tokenizer_pre.encode(text_to_count, add_special_tokens=False))

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=hf_length_function
        )
        return text_splitter.split_text(text)