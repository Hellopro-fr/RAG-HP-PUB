from app.utils.router.tags import RouterTags as Tags

from app.router.ingestion.ingestion import router as IngestionRouter

params = [
    [
        IngestionRouter,
        f"/",
        Tags.search,
        True
    ]
]
