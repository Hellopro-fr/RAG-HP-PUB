from fastapi import FastAPI
from pydantic import BaseModel
from milvus_client import execute_query


description = """
API rest-milvus pour le projet RAG Hellopro 🚀
"""


app = FastAPI()

class QueryRequest(BaseModel):
    collection_name: str
    query: dict  # paramètre générique pour la requête

@app.post("/execute")
def execute(req: QueryRequest):
    result = execute_query(req.collection_name, req.query)
    return {"result": result}

