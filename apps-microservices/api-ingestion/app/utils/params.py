from app.utils.router.tags import RouterTags as Tags

from app.router.ingestion.ingestion import router as IngestionRouter
from app.router.ingestion.ingestion_graph import router as IngestionRouterGraph
from app.router.ingestion.ingestion_QC import router as IngestionRouterQC

params = [
    [IngestionRouter, f"/ingestion", Tags.ingestion, True],
    [IngestionRouterGraph, f"/ingestion-graph", Tags.ingestion_graph, True],
    [IngestionRouterQC, f"/ingestion-qc", Tags.ingestion_qc, True],
]
