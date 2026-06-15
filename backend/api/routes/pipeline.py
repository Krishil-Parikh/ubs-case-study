from fastapi import APIRouter, HTTPException
from backend.models.schemas import PipelineRequest, PipelineResponse
from backend.core.pipeline import pipeline

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/query", response_model=PipelineResponse)
async def query(request: PipelineRequest) -> PipelineResponse:
    try:
        return await pipeline.run(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
