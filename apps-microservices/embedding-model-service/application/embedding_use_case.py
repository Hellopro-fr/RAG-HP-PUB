import logging
import numpy as np
import os
from typing import List
from sentence_transformers import SentenceTransformer
from tritonclient.grpc.aio import InferenceServerClient, InferInput, InferRequestedOutput
import torch

TRITON_URL = os.getenv("TRITON_URL", "localhost:8001")
MODEL_NAME = "camembert-embedding"

class EmbeddingUseCase:
    def __init__(self):
        tokenizer_name = "dangvantuan/sentence-camembert-large"
        logging.info(f"Chargement du tokenizer: {tokenizer_name}")
        self.tokenizer = SentenceTransformer(tokenizer_name).tokenizer
        self.triton_client = InferenceServerClient(url=TRITON_URL)

    def mean_pooling(self, model_output, attention_mask):
        token_embeddings = torch.from_numpy(model_output)
        attention_mask = torch.from_numpy(attention_mask)
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1)
        sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
        return (sum_embeddings / sum_mask).numpy()

    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        try:
            encoded_input = self.tokenizer(
                texts, padding=True, truncation=True, return_tensors="np", max_length=512
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
            
            return sentence_embeddings.tolist()
            
        except Exception as e:
            logging.error(f"Erreur lors de l'appel à Triton pour l'embedding: {e}", exc_info=True)
            return [[] for _ in texts]