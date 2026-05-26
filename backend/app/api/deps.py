"""API dependencies."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.analytics_service import AnalyticsService
from app.services.memory_service import MemoryService
from app.services.optimize_service import OptimizeService
from app.services.rag_service import RAGService


async def get_optimize_service(
    db: AsyncSession = Depends(get_db),
) -> OptimizeService:
    return OptimizeService(db)


async def get_memory_service(
    db: AsyncSession = Depends(get_db),
) -> MemoryService:
    return MemoryService(db)


async def get_rag_service(
    db: AsyncSession = Depends(get_db),
) -> RAGService:
    return RAGService(db)


async def get_analytics_service(
    db: AsyncSession = Depends(get_db),
) -> AnalyticsService:
    return AnalyticsService(db)
