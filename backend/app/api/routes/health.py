"""Health check endpoints."""

import time

from fastapi import APIRouter
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.redis_client import get_redis
from app.schemas import HealthResponse
from app.services.ollama_service import OllamaService

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="healthy", service="api")


@router.get("/redis", response_model=HealthResponse)
async def health_redis() -> HealthResponse:
    start = time.perf_counter()
    try:
        redis = await get_redis()
        await redis.ping()
        latency = (time.perf_counter() - start) * 1000
        return HealthResponse(status="healthy", service="redis", latency_ms=round(latency, 2))
    except Exception as exc:
        return HealthResponse(
            status="unhealthy", service="redis", details={"error": str(exc)}
        )


@router.get("/postgres", response_model=HealthResponse)
async def health_postgres() -> HealthResponse:
    start = time.perf_counter()
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        latency = (time.perf_counter() - start) * 1000
        return HealthResponse(status="healthy", service="postgres", latency_ms=round(latency, 2))
    except Exception as exc:
        return HealthResponse(
            status="unhealthy", service="postgres", details={"error": str(exc)}
        )


@router.get("/ollama", response_model=HealthResponse)
async def health_ollama() -> HealthResponse:
    start = time.perf_counter()
    ollama = OllamaService()
    result = await ollama.health_check()
    latency = (time.perf_counter() - start) * 1000
    status = result.get("status", "unhealthy")
    return HealthResponse(
        status=status,
        service="ollama",
        latency_ms=round(latency, 2),
        details=result,
    )


@router.get("/full", response_model=dict)
async def health_full() -> dict:
    redis_health = await health_redis()
    postgres_health = await health_postgres()
    ollama_health = await health_ollama()

    all_healthy = all(
        h.status == "healthy"
        for h in (redis_health, postgres_health, ollama_health)
    )

    return {
        "status": "healthy" if all_healthy else "degraded",
        "services": {
            "api": "healthy",
            "redis": redis_health.model_dump(),
            "postgres": postgres_health.model_dump(),
            "ollama": ollama_health.model_dump(),
        },
    }
