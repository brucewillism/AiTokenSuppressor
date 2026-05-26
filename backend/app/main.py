"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.routes import api_router
from app.core.config import get_settings
from app.core.database import init_db
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.core.metrics import APP_INFO
from app.core.redis_client import close_redis
from app.middleware.rate_limit import PayloadLimitMiddleware, RateLimitMiddleware

settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    from app.core.init_db import setup_pgvector

    try:
        await setup_pgvector()
        await init_db()
    except Exception as exc:
        logger.exception("startup_initialization_failed", error=str(exc))
    APP_INFO.info({"version": "1.0.0", "env": settings.app_env})
    yield
    await close_redis()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description="Intelligent middleware layer for LLM token optimization",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(PayloadLimitMiddleware)
    app.add_middleware(RateLimitMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router)

    if settings.prometheus_enabled:
        Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    return app


app = create_app()
