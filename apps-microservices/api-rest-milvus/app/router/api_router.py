from fastapi import APIRouter

from .create import router as create_router
from .read import router as read_router
from .update import router as update_router
from .delete import router as delete_router

api_router = APIRouter()

api_router.include_router(read_router, tags=["GET"])
api_router.include_router(create_router, tags=["POST"])
api_router.include_router(update_router, tags=["PUT"])
# api_router.include_router(delete_router, tags=["DELETE"])  # Désactivé pour sécurité