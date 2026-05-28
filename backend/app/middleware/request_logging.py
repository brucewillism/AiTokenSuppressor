"""Structured request/response logging for reverse-proxy troubleshooting."""

import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.logging import get_logger

logger = get_logger(__name__)

PUBLIC_PATHS = frozenset({"/health", "/metrics", "/docs", "/openapi.json", "/redoc"})


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.perf_counter()
        path = request.url.path
        has_auth = bool(
            request.headers.get("authorization") or request.headers.get("x-api-key")
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "request_failed",
                method=request.method,
                path=path,
                elapsed_ms=round(elapsed_ms, 2),
                has_auth=has_auth,
                error=str(exc),
            )
            raise

        elapsed_ms = (time.perf_counter() - start) * 1000
        log_fn = logger.info if response.status_code < 400 else logger.warning
        if path not in PUBLIC_PATHS or response.status_code >= 400:
            log_fn(
                "request_complete",
                method=request.method,
                path=path,
                status=response.status_code,
                elapsed_ms=round(elapsed_ms, 2),
                has_auth=has_auth,
                client=request.client.host if request.client else None,
            )
        return response
