"""OpenAI-compatible proxy routes (/v1/*)."""

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.deps import get_optimize_service
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import verify_jwt_or_api_key
from app.schemas import CompressionStrategy
from app.schemas.openai_proxy import (
    ChatCompletionRequest,
    ModelCard,
    ModelListResponse,
)
from app.services.optimize_service import OptimizeService
from app.services.proxy_service import ProxyService

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/v1", tags=["OpenAI Proxy"])


def _parse_strategy(value: str | None) -> CompressionStrategy:
    if not value:
        return CompressionStrategy(settings.proxy_default_strategy)
    try:
        return CompressionStrategy(value.lower())
    except ValueError:
        return CompressionStrategy.BALANCED


def _header_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@router.get("/models", response_model=ModelListResponse)
async def list_models(
    _auth: dict = Depends(verify_jwt_or_api_key),
) -> ModelListResponse:
    models = [
        "gpt-4o",
        "gpt-4o-mini",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "gemini/gemini-1.5-pro",
        "deepseek/deepseek-chat",
        "ollama/llama3.2",
    ]
    return ModelListResponse(
        data=[ModelCard(id=m, owned_by="ai-token-suppressor") for m in models]
    )


@router.post("/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    _auth: dict = Depends(verify_jwt_or_api_key),
    service: OptimizeService = Depends(get_optimize_service),
    x_ats_strategy: str | None = Header(default=None, alias="X-ATS-Strategy"),
    x_ats_pipeline: str | None = Header(default=None, alias="X-ATS-Pipeline"),
    x_ats_use_memory: str | None = Header(default=None, alias="X-ATS-Use-Memory"),
    x_ats_use_ollama: str | None = Header(default=None, alias="X-ATS-Use-Ollama"),
    x_ats_skip_optimize: str | None = Header(default=None, alias="X-ATS-Skip-Optimize"),
):
    strategy = _parse_strategy(x_ats_strategy)
    pipeline = (x_ats_pipeline or settings.proxy_pipeline).lower()
    if pipeline not in ("compress", "optimize"):
        pipeline = "compress"

    use_memory = _header_bool(x_ats_use_memory, settings.proxy_use_memory)
    skip_optimize = _header_bool(x_ats_skip_optimize, settings.proxy_skip_optimize)

    use_ollama: bool | None
    if x_ats_use_ollama is None:
        use_ollama = settings.proxy_use_ollama
    else:
        use_ollama = _header_bool(x_ats_use_ollama, True)

    proxy = ProxyService(service)

    try:
        if request.stream:
            stream = proxy.chat_completion_stream(
                request,
                strategy=strategy,
                pipeline=pipeline,
                use_memory=use_memory,
                use_ollama=use_ollama,
                skip_optimize=skip_optimize,
            )
            return StreamingResponse(
                stream,
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-ATS-Strategy": strategy.value,
                    "X-ATS-Pipeline": pipeline,
                },
            )

        response, meta_headers = await proxy.chat_completion(
            request,
            strategy=strategy,
            pipeline=pipeline,
            use_memory=use_memory,
            use_ollama=use_ollama,
            skip_optimize=skip_optimize,
        )
        return JSONResponse(
            content=response.model_dump(),
            headers=meta_headers,
        )
    except RuntimeError as exc:
        logger.error("proxy_llm_failed", error=str(exc))
        raise HTTPException(
            status_code=502,
            detail={
                "error": {
                    "message": str(exc),
                    "type": "proxy_error",
                    "code": "llm_upstream_failed",
                }
            },
        ) from exc
    except Exception as exc:
        logger.exception("proxy_chat_failed", error=str(exc))
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "message": "Proxy processing failed",
                    "type": "internal_error",
                }
            },
        ) from exc
