"""API route aggregation."""

from fastapi import APIRouter

from app.api.routes import advanced, auth, health, memory, optimize, rag, stats

api_router = APIRouter()
api_router.include_router(optimize.router)
api_router.include_router(advanced.router)
api_router.include_router(memory.router)
api_router.include_router(rag.router)
api_router.include_router(stats.router)
api_router.include_router(health.router)
api_router.include_router(auth.router)
