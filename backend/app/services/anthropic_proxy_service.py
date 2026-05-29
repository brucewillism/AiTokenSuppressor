"""Anthropic /v1/messages proxy with ATS compression (Claude Code, VS Code)."""

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from app.core.logging import get_logger
from app.schemas import CompressionStrategy, Message, MessageRole
from app.schemas.anthropic_proxy import (
    AnthropicMessageResponse,
    AnthropicMessagesRequest,
    AnthropicTextBlock,
    AnthropicUsage,
)
from app.services.proxy_service import ProxyService, normalize_messages

logger = get_logger(__name__)


def extract_text_content(content: str | list[dict[str, Any]] | None) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type", "")
        if block_type == "text":
            parts.append(str(block.get("text", "")))
        elif block_type == "tool_result":
            parts.append(f"[tool_result]: {block.get('content', '')}")
        elif block_type == "tool_use":
            parts.append(
                f"[tool_use {block.get('name', 'tool')}]: "
                f"{json.dumps(block.get('input', {}), ensure_ascii=False)[:2000]}"
            )
        elif "text" in block:
            parts.append(str(block["text"]))
    return "\n".join(p for p in parts if p).strip()


def anthropic_request_to_messages(request: AnthropicMessagesRequest) -> list[Message]:
    internal: list[dict[str, Any]] = []
    system_parts: list[str] = []

    if request.system is not None:
        top = extract_text_content(request.system)
        if top:
            system_parts.append(top)

    for msg in request.messages:
        text = extract_text_content(msg.content)
        if msg.role == "system":
            if text:
                system_parts.append(text)
            continue
        role = msg.role
        if role == "assistant" and not text:
            text = "[assistant message]"
        internal.append({"role": role, "content": text})

    if system_parts:
        internal.insert(0, {"role": "system", "content": "\n\n".join(system_parts)})

    return normalize_messages(internal)


def _sse(event: str, data: dict[str, Any]) -> str:
    payload = {**data, "type": data.get("type", event)}
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _chunk_text(text: str, size: int = 24) -> list[str]:
    if not text:
        return [""]
    return [text[i : i + size] for i in range(0, len(text), size)]


class AnthropicProxyService:
    def __init__(self, proxy: ProxyService) -> None:
        self.proxy = proxy

    async def _optimize_messages(
        self,
        messages: list[Message],
        *,
        model: str,
        strategy: CompressionStrategy,
        pipeline: str,
        use_memory: bool,
        use_ollama: bool | None,
        skip_optimize: bool,
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        tokens_before = 0
        tokens_after = 0
        tokens_saved = 0
        optimize_ms = 0.0

        if skip_optimize:
            optimized = [
                {"role": m.role.value, "content": m.content} for m in messages
            ]
        else:
            opt_start = time.perf_counter()
            opt_result = await self.proxy.run_compression(
                messages,
                strategy=strategy,
                model=model,
                pipeline=pipeline,
                use_memory=use_memory,
                use_ollama=use_ollama,
            )
            optimize_ms = (time.perf_counter() - opt_start) * 1000
            tokens_before = int(opt_result.get("tokens_before", 0))
            tokens_after = int(opt_result.get("tokens_after", 0))
            tokens_saved = int(opt_result.get("tokens_saved", 0))
            optimized = [
                {
                    "role": (
                        m.role.value if hasattr(m.role, "value") else str(m.role)
                    ),
                    "content": m.content,
                }
                for m in opt_result["messages"]
            ]

        meta = {
            "X-ATS-Tokens-Before": str(tokens_before),
            "X-ATS-Tokens-After": str(tokens_after),
            "X-ATS-Tokens-Saved": str(tokens_saved),
            "X-ATS-Optimize-Ms": str(round(optimize_ms, 2)),
            "X-ATS-Strategy": strategy.value,
            "X-ATS-Pipeline": pipeline,
        }
        return optimized, meta

    async def create_message(
        self,
        request: AnthropicMessagesRequest,
        *,
        strategy: CompressionStrategy,
        pipeline: str,
        use_memory: bool,
        use_ollama: bool | None,
        skip_optimize: bool,
    ) -> tuple[AnthropicMessageResponse, dict[str, str]]:
        messages = anthropic_request_to_messages(request)
        optimized, meta = await self._optimize_messages(
            messages,
            model=request.model,
            strategy=strategy,
            pipeline=pipeline,
            use_memory=use_memory,
            use_ollama=use_ollama,
            skip_optimize=skip_optimize,
        )

        temp = request.temperature if request.temperature is not None else 0.3
        llm_result = await self.proxy.litellm.complete_with_fallback(
            messages=optimized,
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=temp,
        )
        if llm_result.get("error"):
            raise RuntimeError(llm_result["error"])

        provider_used = llm_result.get("provider_used", "unknown")
        meta["X-ATS-Provider-Used"] = provider_used
        meta["X-ATS-Fallback-Chain"] = ",".join(self.proxy.litellm.get_fallback_chain())

        input_tokens = llm_result.get("tokens_input", 0)
        output_tokens = llm_result.get("tokens_output", 0)
        msg_id = f"msg_{uuid.uuid4().hex[:24]}"

        response = AnthropicMessageResponse(
            id=msg_id,
            content=[AnthropicTextBlock(text=llm_result.get("content", "") or "")],
            model=llm_result.get("model", request.model),
            stop_reason="end_turn",
            usage=AnthropicUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            ),
        )
        return response, meta

    async def create_message_stream(
        self,
        request: AnthropicMessagesRequest,
        *,
        strategy: CompressionStrategy,
        pipeline: str,
        use_memory: bool,
        use_ollama: bool | None,
        skip_optimize: bool,
    ) -> AsyncIterator[str]:
        """SSE Anthropic. Usa resposta completa + pseudo-stream (Groq stream pode bloquear)."""
        yield _sse("ping", {"type": "ping"})

        response, meta = await self.create_message(
            request,
            strategy=strategy,
            pipeline=pipeline,
            use_memory=use_memory,
            use_ollama=use_ollama,
            skip_optimize=skip_optimize,
        )

        text = response.content[0].text if response.content else ""
        msg_id = response.id
        model = response.model
        output_tokens = response.usage.output_tokens

        yield _sse(
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": msg_id,
                    "type": "message",
                    "role": "assistant",
                    "content": [],
                    "model": model,
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": 1,
                    },
                },
            },
        )
        yield _sse(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        )

        for piece in _chunk_text(text):
            if piece:
                yield _sse(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": piece},
                    },
                )

        yield _sse(
            "content_block_stop",
            {"type": "content_block_stop", "index": 0},
        )
        yield _sse(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": output_tokens},
            },
        )
        yield _sse("message_stop", {"type": "message_stop"})

        logger.info(
            "anthropic_stream_complete",
            strategy=strategy.value,
            ats_tokens_saved=meta.get("X-ATS-Tokens-Saved"),
            mode="pseudo_stream",
        )
