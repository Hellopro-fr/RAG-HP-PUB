from app.utils.router.tags import RouterTags as Tags

from app.router.optimize.optimize import router as OptimizingRouter

params = [
    [
        OptimizingRouter,
        f"/optimize-product",
        Tags.optimizing,
        True
    ]
]