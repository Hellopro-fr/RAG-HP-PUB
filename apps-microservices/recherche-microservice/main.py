import os
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pymilvus import MilvusClient
from sentence_transformers import SentenceTransformer
from rerankers import Reranker
import numpy as np

# --- Configuration ---
ZILLIZ_CLOUD_URI = os.environ.get("ZILLIZ_CLOUD_URI", "YOUR_ZILLIZ_CLOUD_URI")
ZILLIZ_CLOUD_TOKEN = os.environ.get("ZILLIZ_CLOUD_TOKEN", "YOUR_ZILLIZ_CLOUD_TOKEN")
COLLECTION_NAME = "classification_produit"  # Replace with your collection name

# --- Initialize Models ---
print("Loading models...")
embedding_model = SentenceTransformer('dangvantuan/sentence-camembert-large')
reranker = Reranker("BAAI/bge-reranker-base") # You can choose other rerankers
print("Models loaded.")

# --- Milvus Connection ---
print("Connecting to Milvus...")
try:
    milvus_client = MilvusClient(uri=ZILLIZ_CLOUD_URI, token=ZILLIZ_CLOUD_TOKEN)
    print("Successfully connected to Milvus.")
except Exception as e:
    print(f"Failed to connect to Milvus: {e}")
    milvus_client = None

app = FastAPI()

# --- HTML Frontend ---
html = """
<!DOCTYPE html>
<html>
    <head>
        <title>Recherche Produit en Temps Réel</title>
    </head>
    <body>
        <h1>Recherche de Produits</h1>
        <form action="" onsubmit="sendMessage(event)">
            <input type="text" id="messageText" autocomplete="off"/>
            <button>Rechercher</button>
        </form>
        <h2>Résultats:</h2>
        <ul id='messages'>
        </ul>
        <script>
            var ws = new WebSocket("ws://localhost:8000/ws");
            ws.onmessage = function(event) {
                var messages = document.getElementById('messages')
                var message = document.createElement('li')
                var content = document.createTextNode(event.data)
                message.appendChild(content)
                messages.appendChild(message)
            };
            function sendMessage(event) {
                var input = document.getElementById("messageText")
                var messages = document.getElementById('messages')
                messages.innerHTML = '' // Clear previous results
                ws.send(input.value)
                event.preventDefault()
            }
        </script>
    </body>
</html>
"""

@app.get("/")
async def get():
    return HTMLResponse(html)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            query_text = await websocket.receive_text()
            if not milvus_client:
                await websocket.send_text("Erreur: La connexion à Milvus n'est pas établie.")
                continue

            # 1. Embed the query
            query_embedding = embedding_model.encode(query_text)

            # 2. Search in Milvus
            search_params = {"metric_type": "L2", "params": {"nprobe": 10}}
            try:
                results = milvus_client.search(
                    collection_name=COLLECTION_NAME,
                    data=[query_embedding.tolist()],
                    limit=10,
                    search_params=search_params,
                    output_fields=["product_name", "description"]  # Adjust to your fields
                )

                # 3. Rerank the results
                documents = [hit['entity']['description'] for hit in results[0]]
                reranked_results = reranker.rank(query=query_text, docs=documents)

                # 4. Send results in real-time
                for result in reranked_results:
                    doc = documents[result.doc_id]
                    await websocket.send_text(f"Produit: {doc} (Score: {result.score:.4f})")
                    await asyncio.sleep(0.1) # Simulate real-time stream

            except Exception as e:
                await websocket.send_text(f"Une erreur est survenue: {e}")

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"An error occurred: {e}")
        await websocket.close(code=1011, reason=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
