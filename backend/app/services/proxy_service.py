"""OpenAI-compatible proxy: optimize prompts then forward to LiteLLM."""

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas import CompressionStrategy, Message, MessageRole
from app.schemas.openai_proxy import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatCompletionMessage,
    UsageInfo,
)
from app.services.litellm_service import LiteLLMService
from app.services.optimize_service import OptimizeService

logger = get_logger(__name__)
settings = get_settings()


def infer_provider(model: str) -> str:
    m = model.lower()
    if m.startswith("gpt") or "openai" in m:
        return "openai"
    if "claude" in m or "anthropic" in m:
        return "anthropic"
    if "gemini" in m:
        return "gemini"
    if "deepseek" in m:
        return "deepseek"
    if "ollama" in m or m.startswith("llama"):
        return "ollama"
    return "openai"


def _messages_to_dicts(messages: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for m in messages:
        if isinstance(m, Message):
            dumped = m.model_dump()
            dumped["role"] = (
                m.role.value if hasattr(m.role, "value") else str(m.role)
            )
            result.append(dumped)
        else:
            result.append(m)
    return result


def normalize_messages(raw: list[dict[str, Any]]) -> list[Message]:
    normalized: list[Message] = []
    role_map = {
        "system": MessageRole.SYSTEM,
        "user": MessageRole.USER,
        "assistant": MessageRole.ASSISTANT,
        "tool": MessageRole.TOOL,
        "function": MessageRole.TOOL,
    }
    for item in raw:
        role_str = item.get("role", "user")
        role = role_map.get(role_str, MessageRole.USER)
        content = item.get("content", "")
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(str(part.get("text", "")))
            content = " ".join(parts).strip()
        if content is None:
            content = ""
        if role == MessageRole.TOOL and content:
            content = f"[tool result]: {content}"
        normalized.append(
            Message(role=role, content=str(content), name=item.get("name"))
        )
    return normalized


class ProxyService:
    def __init__(self, optimize_service: OptimizeService) -> None:
        self.optimize_service = optimize_service
        self.litellm = LiteLLMService()

    async def run_compression(
        self,
        messages: list[Message],
        *,
        strategy: CompressionStrategy,
        model: str,
        pipeline: str,
        use_memory: bool,
        use_ollama: bool | None,
    ) -> dict[str, Any]:
        if pipeline == "optimize":
            return await self.optimize_service.optimize(
                messages=messages,
                strategy=strategy,
                target_model=model,
                provider=infer_provider(model),
                use_memory=use_memory,
                use_rag=False,
                use_hierarchical_memory=use_memory,
                use_semantic_cache=True,
                check_semantic_loss=False,
            )
        return await self.optimize_service.compress_only(
            messages=messages,
            strategy=strategy,
            target_model=model,
            check_semantic_loss=False,
            use_ollama=use_ollama,
        )

    async def chat_completion(
        self,
        request: ChatCompletionRequest,
        *,
        strategy: CompressionStrategy,
        pipeline: str,
        use_memory: bool,
        use_ollama: bool | None,
        skip_optimize: bool,
    ) -> tuple[ChatCompletionResponse, dict[str, str]]:
        raw_messages = [m.model_dump() for m in request.messages]
        messages = normalize_messages(raw_messages)

        tokens_before = 0
        tokens_after = 0
        tokens_saved = 0
        optimize_ms = 0.0

        if skip_optimize:
            optimized_dicts = [m.model_dump() for m in messages]
        else:
            opt_start = time.perf_counter()
            opt_result = await self.run_compression(
                messages,
                strategy=strategy,
                model=request.model,
                pipeline=pipeline,
                use_memory=use_memory,
                use_ollama=use_ollama,
            )
            optimize_ms = (time.perf_counter() - opt_start) * 1000
            tokens_before = opt_result.get("tokens_before", 0)
            tokens_after = opt_result.get("tokens_after", 0)
            tokens_saved = opt_result.get("tokens_saved", 0)
            optimized_dicts = _messages_to_dicts(opt_result["messages"])

        llm_result = await self.litellm.complete(
            messages=optimized_dicts,
            model=request.model,
            provider=infer_provider(request.model),
            max_tokens=request.max_tokens or 4096,
            temperature=request.temperature if request.temperature is not None else 0.3,
        )

        if llm_result.get("error"):
            raise RuntimeError(llm_result["error"])

        completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        response = ChatCompletionResponse(
            id=completion_id,
            created=int(time.time()),
            model=llm_result.get("model", request.model),
            choices=[
                ChatCompletionChoice(
                    message=ChatCompletionMessage(
                        role="assistant",
                        content=llm_result.get("content", ""),
                    ),
                    finish_reason="stop",
                )
            ],
            usage=UsageInfo(
                prompt_tokens=llm_result.get("tokens_input", tokens_after or tokens_before),
                completion_tokens=llm_result.get("tokens_output", 0),
                total_tokens=(
                    llm_result.get("tokens_input", 0) + llm_result.get("tokens_output", 0)
                ),
            ),
        )

        meta_headers = {
            "X-ATS-Tokens-Before": str(tokens_before),
            "X-ATS-Tokens-After": str(tokens_after),
            "X-ATS-Tokens-Saved": str(tokens_saved),
            "X-ATS-Optimize-Ms": str(round(optimize_ms, 2)),
            "X-ATS-Strategy": strategy.value,
            "X-ATS-Pipeline": pipeline,
        }
        return response, meta_headers

    async def chat_completion_stream(
        self,
        request: ChatCompletionRequest,
        *,
        strategy: CompressionStrategy,
        pipeline: str,
        use_memory: bool,
        use_ollama: bool | None,
        skip_optimize: bool,
    ) -> AsyncIterator[str]:
        raw_messages = [m.model_dump() for m in request.messages]
        messages = normalize_messages(raw_messages)

        if skip_optimize:
            optimized_dicts = [m.model_dump() for m in messages]
        else:
            opt_result = await self.run_compression(
                messages,
                strategy=strategy,
                model=request.model,
                pipeline=pipeline,
                use_memory=use_memory,
                use_ollama=use_ollama,
            )
            optimized_dicts = _messages_to_dicts(opt_result["messages"])

        completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created = int(time.time())

        async for chunk in self.litellm.complete_stream(
            messages=optimized_dicts,
            model=request.model,
            provider=infer_provider(request.model),
            max_tokens=request.max_tokens or 4096,
            temperature=request.temperature if request.temperature is not None else 0.3,
        ):
            payload = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": request.model,
                "choices": [
                    {
                        "index": 0,
                        "delta": chunk.get("delta", {}),
                        "finish_reason": chunk.get("finish_reason"),
                    }
                ],
            }
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"
