"""Health check endpoints."""

import asyncio
import time

from fastapi import APIRouter
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.redis_client import get_redis
from app.schemas import HealthResponse
from app.services.ollama_service import OllamaService

router = APIRouter(prefix="/health", tags=["Health"])

HEALTH_PROBE_TIMEOUT = 8.0


def _service_dict(health: HealthResponse) -> dict:
    return health.model_dump()


@router.get("/live")
async def health_live() -> dict:
    """Probe JSON para load balancers (nginx: /health/live). Não use na rota SPA /health."""
    return {"status": "ok", "service": "api"}


@router.get("")
async def health() -> dict:
    """Alias do liveness probe."""
    return {"status": "ok", "service": "api"}


@router.get("/detail", response_model=HealthResponse)
async def health_detail() -> HealthResponse:
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
    result = await ollama.health_check(timeout=5.0)
    latency = (time.perf_counter() - start) * 1000
    status = result.get("status", "unhealthy")
    return HealthResponse(
        status=status,
        service="ollama",
        latency_ms=round(latency, 2),
        details=result,
    )


async def _probe(name: str, coro) -> HealthResponse:
    try:
        return await asyncio.wait_for(coro, timeout=HEALTH_PROBE_TIMEOUT)
    except asyncio.TimeoutError:
        return HealthResponse(
            status="unhealthy",
            service=name,
            details={"error": f"timeout after {HEALTH_PROBE_TIMEOUT}s"},
        )
    except Exception as exc:
        return HealthResponse(
            status="unhealthy",
            service=name,
            details={"error": str(exc)},
        )


@router.get("/full", response_model=dict)
async def health_full() -> dict:
    redis_health, postgres_health, ollama_health = await asyncio.gather(
        _probe("redis", health_redis()),
        _probe("postgres", health_postgres()),
        _probe("ollama", health_ollama()),
    )

    core_ok = redis_health.status == "healthy" and postgres_health.status == "healthy"

    return {
        "status": "healthy" if core_ok else "degraded",
        "services": {
            "api": {"status": "healthy", "service": "api", "latency_ms": None},
            "redis": _service_dict(redis_health),
            "postgres": _service_dict(postgres_health),
            "ollama": _service_dict(ollama_health),
        },
    }
