"""Fachada `TokenSuppressor.compress` do contrato v1.2 §11.2.

A biblioteca não abre banco, Redis, Ollama, LiteLLM nem provedor.
Sumarização, se houver, usa a port `model` injetada pelo hospedeiro.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ats_core.compression import (
    DEFAULT_LIGHTWEIGHT_TOKEN_THRESHOLD,
    CompressionService,
)
from ats_core.types import CompressionStrategy

ATS_MODE_ENABLED = "ENABLED"


@dataclass(frozen=True)
class CompressionResult:
    messages: list[dict[str, Any]]
    operations: list[str]
    tokens_in_original: int
    tokens_in_final: int
    compression_ratio: float
    t_ats_ms: float
    ats_mode: str


class TokenSuppressor:
    """Núcleo puro de compressão. A mesma entrada produz a mesma saída de mensagens."""

    def __init__(
        self,
        *,
        model: Any | None = None,
        lightweight_token_threshold: int = DEFAULT_LIGHTWEIGHT_TOKEN_THRESHOLD,
    ) -> None:
        self._engine = CompressionService(
            model=model,
            lightweight_token_threshold=lightweight_token_threshold,
        )

    async def compress(
        self,
        messages: list[Any],
        strategy: CompressionStrategy | str = CompressionStrategy.BALANCED,
        max_tokens: int | None = None,
        preserve_system: bool = True,
        use_ollama: bool | None = None,
        sensitivity: str | None = None,
    ) -> CompressionResult:
        """Comprime `messages` com a mesma pipeline de `CompressionService.compress_prompt`.

        `sensitivity` é a classe do §8. A compressão é local e não escolhe provedor.
        `model` só é chamado quando a estratégia pede sumarização (`use_ollama`).
        """
        del sensitivity
        chosen = _strategy(strategy)
        started = time.perf_counter()
        original = [_as_dict(item) for item in messages]
        tokens_in_original = self._engine.token_service.count_messages(original)
        compressed, operations = await self._engine.compress_prompt(
            messages,
            strategy=chosen,
            max_tokens=max_tokens,
            preserve_system=preserve_system,
            use_ollama=use_ollama,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        tokens_in_final = self._engine.token_service.count_messages(compressed)
        ratio = tokens_in_final / tokens_in_original if tokens_in_original else 1.0
        return CompressionResult(
            messages=compressed,
            operations=operations,
            tokens_in_original=tokens_in_original,
            tokens_in_final=tokens_in_final,
            compression_ratio=round(ratio, 4),
            t_ats_ms=elapsed_ms,
            ats_mode=ATS_MODE_ENABLED,
        )


def _strategy(strategy: CompressionStrategy | str) -> CompressionStrategy:
    if isinstance(strategy, CompressionStrategy):
        return strategy
    value = getattr(strategy, "value", strategy)
    return CompressionStrategy(str(value))


def _as_dict(message: Any) -> dict[str, Any]:
    if isinstance(message, dict):
        return message
    dump = getattr(message, "model_dump", None)
    if callable(dump):
        dumped = dump()
        if isinstance(dumped, dict):
            return dumped
    return {"role": "user", "content": str(message)}
