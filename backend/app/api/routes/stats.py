"""Statistics and analytics endpoints."""

from fastapi import APIRouter, Depends

from app.api.deps import get_analytics_service
from app.core.security import verify_jwt_or_api_key
from app.schemas import StatsResponse
from app.services.analytics_service import AnalyticsService

router = APIRouter(tags=["Analytics"])


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    days: int = 7,
    _auth: dict = Depends(verify_jwt_or_api_key),
    service: AnalyticsService = Depends(get_analytics_service),
) -> StatsResponse:
    stats = await service.get_stats(days=days)
    return StatsResponse(**stats)
