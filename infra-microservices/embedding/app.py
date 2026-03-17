from fastapi import FastAPI, Body
from transformers import CamembertTokenizer
from sentence_transformers import SentenceTransformer
import uvicorn

# Initialisation modèles
tokenizer = CamembertTokenizer.from_pretrained("camembert-base")
model = SentenceTransformer("dangvantuan/sentence-camembert-large")

app = FastAPI(title="CamemBERT Chunking API")

def chunk_text(text, max_tokens=500, overlap=50):
    tokens = tokenizer.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = start + max_tokens
        chunk_tokens = tokens[start:end]
        chunk_text_str = tokenizer.decode(chunk_tokens)
        chunks.append(chunk_text_str)
        start += max_tokens - overlap
    return chunks

@app.post("/process")
def process_text(payload: dict = Body(...)):
    text = payload.get("text", "")
    if not text.strip():
        return {"error": "Le texte est vide"}

    chunks = chunk_text(text)
    embeddings = model.encode(chunks)

    results = []
    for i, chunk in enumerate(chunks):
        results.append({
            "chunk_id": i,
            "text": chunk,
            "embedding": embeddings[i].tolist(),
            "metadata": {
                "token_start": i * 450,
                "token_end": i * 450 + len(tokenizer.encode(chunk)),
                "source": payload.get("source", "unknown")
            }
        })

    return {"chunks": results, "total_chunks": len(results)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
