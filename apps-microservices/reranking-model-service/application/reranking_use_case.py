import logging
import numpy as np
import os
from typing import List, Dict, Any
from sentence_transformers.cross_encoder import CrossEncoder
from tritonclient.grpc.aio import InferenceServerClient, InferInput, InferRequestedOutput

TRITON_URL = os.getenv("TRITON_URL", "localhost:8001")
MODEL_NAME = "bge-reranker"

class RerankingUseCase:
    def __init__(self):
        tokenizer_name = "BAAI/bge-reranker-v2-m3"
        logging.info(f"Chargement du tokenizer: {tokenizer_name}")
        self.tokenizer = CrossEncoder(tokenizer_name).tokenizer
        self.triton_client = InferenceServerClient(url=TRITON_URL)

    async def rerank_documents(self, query: str, documents: List[str]) -> List[str]:
        if not documents:
            return []
            
        try:
            # 1. Création des paires (query, document)
            model_input = [[query, doc] for doc in documents]
            
            # 2. Tokenization
            encoded_input = self.tokenizer(
                model_input, padding=True, truncation=True, return_tensors="np"
            )
            input_ids = encoded_input["input_ids"].astype(np.int64)
            attention_mask = encoded_input["attention_mask"].astype(np.int64)

            # 3. Préparation des entrées pour Triton
            inputs = [
                InferInput("input_ids", input_ids.shape, "INT64"),
                InferInput("attention_mask", attention_mask.shape, "INT64"),
            ]
            inputs[0].set_data_from_numpy(input_ids)
            inputs[1].set_data_from_numpy(attention_mask)
            outputs = [InferRequestedOutput("output")]

            # 4. Appel à Triton
            response = await self.triton_client.infer(
                model_name=MODEL_NAME, inputs=inputs, outputs=outputs
            )
            scores = response.as_numpy("output").flatten()

            # 5. Tri des documents originaux en fonction des scores
            doc_score_pairs = list(zip(documents, scores))
            doc_score_pairs.sort(key=lambda x: x[1], reverse=True)
            
            return [doc for doc, score in doc_score_pairs]

        except Exception as e:
            logging.error(f"Erreur lors de l'appel à Triton pour le reranking: {e}", exc_info=True)
            # En cas d'erreur, on retourne les documents non triés pour ne pas casser le flux
            return documents

    async def rerank_documents_with_scores(self, query: str, documents: List[str]) -> List[Dict[str, Any]]:
        if not documents:
            return []
            
        try:
            # 1. Création des paires (query, document)
            model_input = [[query, doc] for doc in documents]
            
            # 2. Tokenization
            encoded_input = self.tokenizer(
                model_input, padding=True, truncation=True, return_tensors="np"
            )
            input_ids = encoded_input["input_ids"].astype(np.int64)
            attention_mask = encoded_input["attention_mask"].astype(np.int64)

            # 3. Préparation des entrées pour Triton
            inputs = [
                InferInput("input_ids", input_ids.shape, "INT64"),
                InferInput("attention_mask", attention_mask.shape, "INT64"),
            ]
            inputs[0].set_data_from_numpy(input_ids)
            inputs[1].set_data_from_numpy(attention_mask)
            outputs = [InferRequestedOutput("output")]

            # 4. Appel à Triton
            response = await self.triton_client.infer(
                model_name=MODEL_NAME, inputs=inputs, outputs=outputs
            )
            scores = response.as_numpy("output").flatten()

            # 5. Tri des documents originaux en fonction des scores
            doc_score_pairs = list(zip(documents, scores))
            doc_score_pairs.sort(key=lambda x: x[1], reverse=True)
            
            return [{"document": doc, "score": float(score)} for doc, score in doc_score_pairs]

        except Exception as e:
            logging.error(f"Erreur lors de l'appel à Triton pour le reranking avec scores: {e}", exc_info=True)
            # En cas d'erreur, on retourne les documents non triés avec un score de 0 pour ne pas casser le flux
            return [{"document": doc, "score": 0.0} for doc in documents]