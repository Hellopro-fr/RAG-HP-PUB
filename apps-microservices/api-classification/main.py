from fastapi import FastAPI
from app.router import classify as classify_router

app = FastAPI(
    title="API Classification",
    version="1.0.0",
    description="API de classification des produits."
)

app.include_router(classify_router.router)

@app.get("/", tags=["Monitoring"])
def read_root():
    return {"message": f"Bienvenue sur l'API Classification v1.0.0"}
