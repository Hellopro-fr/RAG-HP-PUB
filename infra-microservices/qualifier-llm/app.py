from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from transformers import pipeline
import torch

app = FastAPI(title="Content Classifier API - Local HF")

# Chargement du modèle zero-shot classification (une fois au démarrage)
classifier = pipeline("zero-shot-classification", 
                      model="facebook/bart-large-mnli",
                      device=0 if torch.cuda.is_available() else -1)

class ClassifyRequest(BaseModel):
    content: str
    max_chunk_size: Optional[int] = 1000
    chunk_overlap: Optional[int] = 100

class ChunkResponse(BaseModel):
    chunk: str
    category: str
    metadata: dict

class ClassifyResponse(BaseModel):
    category: str
    chunks: List[ChunkResponse]

CANDIDATE_LABELS = ["Article", "Produit", "FAQ", "Forum", "Page contact"]

def chunk_text(text: str, max_size: int, overlap: int) -> List[str]:
    chunks = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + max_size, length)
        chunk = text[start:end]
        chunks.append(chunk)
        start += max_size - overlap
    return chunks

def classify_chunk(chunk: str) -> str:
    result = classifier(chunk, CANDIDATE_LABELS)
    # label avec la plus haute probabilité
    return result['labels'][0]

def classify_global_category(categories: List[str]) -> str:
    from collections import Counter
    count = Counter(categories)
    return count.most_common(1)[0][0]

@app.post("/classify", response_model=ClassifyResponse)
async def classify_content(request: ClassifyRequest):
    if not request.content or len(request.content.strip()) == 0:
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    chunks = chunk_text(request.content, request.max_chunk_size, request.chunk_overlap)
    results = []
    categories = []

    for i, chunk in enumerate(chunks):
        cat = classify_chunk(chunk)
        categories.append(cat)
        results.append(
            ChunkResponse(
                chunk=chunk,
                category=cat,
                metadata={"chunk_index": i, "length": len(chunk)},
            )
        )
    global_cat = classify_global_category(categories)
    return ClassifyResponse(category=global_cat, chunks=results)
