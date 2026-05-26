"""Optimization and compression endpoints."""

from fastapi import APIRouter, Depends

from app.api.deps import get_optimize_service
from app.core.security import verify_jwt_or_api_key
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    CompressRequest,
    CompressResponse,
    OptimizeRequest,
    OptimizeResponse,
)
from app.services.analytics_service import AnalyticsService
from app.services.optimize_service import OptimizeService

router = APIRouter(tags=["Optimization"])


@router.post("/optimize", response_model=OptimizeResponse)
async def optimize_prompt(
    request: OptimizeRequest,
    _auth: dict = Depends(verify_jwt_or_api_key),
    service: OptimizeService = Depends(get_optimize_service),
) -> OptimizeResponse:
    result = await service.optimize(
        messages=request.messages,
        strategy=request.strategy,
        target_model=request.target_model,
        use_memory=request.use_memory,
        use_rag=request.use_rag,
        rag_collection=request.rag_collection,
        session_id=request.session_id,
        user_id=request.user_id,
        max_tokens=request.max_tokens,
    )
    return OptimizeResponse(**result)


@router.post("/compress", response_model=CompressResponse)
async def compress_prompt(
    request: CompressRequest,
    _auth: dict = Depends(verify_jwt_or_api_key),
    service: OptimizeService = Depends(get_optimize_service),
) -> CompressResponse:
    result = await service.compress_only(
        messages=request.messages,
        strategy=request.strategy,
        max_tokens=request.max_tokens,
        preserve_system=request.preserve_system,
    )
    return CompressResponse(**result)


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_prompt(
    request: AnalyzeRequest,
    _auth: dict = Depends(verify_jwt_or_api_key),
    service: OptimizeService = Depends(get_optimize_service),
) -> AnalyzeResponse:
    analytics = AnalyticsService(service.db)
    msg_dicts = [m.model_dump() for m in request.messages]
    result = await analytics.analyze_content(msg_dicts, request.target_model)
    return AnalyzeResponse(**result)
