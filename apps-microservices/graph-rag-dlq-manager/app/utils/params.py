from app.utils.router.tags import RouterTags as Tags

from app.router.dlq import router as DLQRouter

params = [
    [DLQRouter, f"/dlq", Tags.dlq, True],
]
