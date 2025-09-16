from app.utils.router.tags import RouterTags as Tags

from app.router.rest-milvus.rest-milvus import router as rest-milvusRouter

params = [
    [
        rest-milvusRouter,
        f"/rest-milvus",
        Tags.rest-milvus,
        True
    ]
]
