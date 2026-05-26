"""Custom exceptions and global error handlers."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class TokenSuppressorError(Exception):
    def __init__(self, message: str, code: str = "INTERNAL_ERROR", status_code: int = 500):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class CompressionError(TokenSuppressorError):
    def __init__(self, message: str):
        super().__init__(message, code="COMPRESSION_ERROR", status_code=422)


class OllamaError(TokenSuppressorError):
    def __init__(self, message: str):
        super().__init__(message, code="OLLAMA_ERROR", status_code=503)


class MemoryError(TokenSuppressorError):
    def __init__(self, message: str):
        super().__init__(message, code="MEMORY_ERROR", status_code=500)


class RateLimitExceeded(TokenSuppressorError):
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, code="RATE_LIMIT", status_code=429)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(TokenSuppressorError)
    async def token_suppressor_handler(
        _request: Request, exc: TokenSuppressorError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(Exception)
    async def generic_handler(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "INTERNAL_ERROR", "message": str(exc)},
        )
