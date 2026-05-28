"""Rate limiting and request middleware."""

import time
from collections import defaultdict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import get_settings
from app.core.exceptions import RateLimitExceeded
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests: int | None = None, window: int | None = None):
        super().__init__(app)
        self.requests = requests or settings.rate_limit_requests
        self.window = window or settings.rate_limit_window
        self._store: dict[str, list[float]] = defaultdict(list)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path.startswith("/health") or request.url.path in (
            "/metrics",
            "/docs",
            "/openapi.json",
            "/redoc",
        ):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - self.window

        self._store[client_ip] = [
            t for t in self._store[client_ip] if t > window_start
        ]

        if len(self._store[client_ip]) >= self.requests:
            raise RateLimitExceeded(
                f"Rate limit exceeded: {self.requests} requests per {self.window}s"
            )

        self._store[client_ip].append(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.requests)
        response.headers["X-RateLimit-Remaining"] = str(
            self.requests - len(self._store[client_ip])
        )
        return response


class PayloadLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method in ("POST", "PUT", "PATCH"):
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > settings.max_payload_bytes:
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": "PAYLOAD_TOO_LARGE",
                        "message": f"Payload exceeds {settings.max_payload_size_mb}MB limit",
                    },
                )
        return await call_next(request)
