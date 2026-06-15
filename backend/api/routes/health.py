from fastapi import APIRouter
from backend.services.qdrant_service import qdrant_service

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health():
    return {"status": "ok", "qdrant": qdrant_service.health()}
