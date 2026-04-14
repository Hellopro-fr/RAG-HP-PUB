import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.routers import query, recommendation, product, admin, fournisseur, nodes
from app.config import settings
from common_utils.metrics.prometheus import start_metrics_server_in_thread
from app.infrastructure.clients import clients

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    start_metrics_server_in_thread(port=settings.PROMETHEUS_PORT)
    logging.info(f"Graph RAG Search API starting on port {settings.API_PORT}")
    yield
    # Shutdown
    clients.close()
    logging.info("Graph RAG Search API shutdown")


app = FastAPI(title="Graph RAG Search API", version="1.0.0", lifespan=lifespan)

# Register Routers
app.include_router(query.router, prefix="/query", tags=["Intelligent Search"])
app.include_router(recommendation.router, prefix="/produits", tags=["Recommendation"])
app.include_router(product.router, prefix="/produits", tags=["Produits"])
app.include_router(fournisseur.router, prefix="/fournisseur", tags=["Fournisseur"])
app.include_router(nodes.router, prefix="/nodes", tags=["Admin"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])


@app.get("/health", tags=["Health"], include_in_schema=False)
def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.API_PORT)
