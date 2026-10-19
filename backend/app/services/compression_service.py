"""Compressão do serviço HTTP. O algoritmo está em ats_core; a port de modelo é o Ollama local."""

from typing import Any

from app.core.config import get_settings
from ats_core.compression import (
    HEAVY_STRATEGIES,
    STRATEGY_CONFIG,
    CompressionService as _CoreCompressionService,
)
from ats_core.compression import resolve_compression_strategy as _resolve_compression_strategy

__all__ = [
    "HEAVY_STRATEGIES",
    "STRATEGY_CONFIG",
    "CompressionService",
    "resolve_compression_strategy",
]


class CompressionService(_CoreCompressionService):
    def __init__(self, model: Any | None = None) -> None:
        if model is None:
            from app.services.ollama_service import OllamaService

            model = OllamaService()
        super().__init__(
            model=model,
            lightweight_token_threshold=get_settings().compress_lightweight_token_threshold,
        )


def resolve_compression_strategy(
    strategy: Any,
    tokens_before: int,
    use_ollama: bool | None,
    *,
    threshold: int | None = None,
) -> tuple[Any, list[str]]:
    """Mesma função do núcleo, com o limiar vindo da configuração do serviço."""
    limit = threshold if threshold is not None else get_settings().compress_lightweight_token_threshold
    return _resolve_compression_strategy(
        strategy,
        tokens_before,
        use_ollama,
        threshold=limit,
    )
