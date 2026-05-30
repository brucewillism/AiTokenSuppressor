"""Estratégia de compressão para proxy: qualidade alta sem Ollama na VPS."""

from app.core.config import get_settings
from app.schemas import CompressionStrategy, ContentType, Message
from app.services.compression_service import resolve_compression_strategy
from app.services.content_detection_service import ContentDetectionService
from app.services.token_service import TokenService

settings = get_settings()

# Estratégias que carregam Ollama (RAM no host) — substituídas quando use_ollama=False
OLLAMA_HEAVY_STRATEGIES = frozenset(
    {
        CompressionStrategy.ULTRA,
        CompressionStrategy.AGGRESSIVE,
        CompressionStrategy.SEMANTIC,
        CompressionStrategy.CHAT_FOCUSED,
    }
)


def _messages_as_dicts(messages: list[Message]) -> list[dict]:
    return [
        {
            "role": m.role.value if hasattr(m.role, "value") else str(m.role),
            "content": m.content,
        }
        for m in messages
    ]


def count_message_tokens(messages: list[Message]) -> int:
    return TokenService().count_messages(_messages_as_dicts(messages))


def _has_code_content(messages: list[Message]) -> bool:
    detector = ContentDetectionService()
    for msg in messages:
        result = detector.detect(str(msg.content or ""))
        if result.content_type == ContentType.CODE:
            return True
    return False


def map_strategy_without_ollama(strategy: CompressionStrategy) -> CompressionStrategy:
    """Substitui ultra/semantic por balanced — mesma pipeline rule-based, zero RAM de modelo local."""
    if strategy == CompressionStrategy.CHAT_FOCUSED:
        return CompressionStrategy.BALANCED
    if strategy in OLLAMA_HEAVY_STRATEGIES:
        return CompressionStrategy.BALANCED
    return strategy


def auto_proxy_strategy(messages: list[Message]) -> tuple[CompressionStrategy, list[str]]:
    """
    Escolhe estratégia pelo tamanho do prompt (sem Ollama):
    - pequeno → fast (rápido)
    - médio/grande com código → code-focused
    - médio/grande geral → balanced (boa economia, quality guard ativo)
    """
    ops: list[str] = []
    tokens = count_message_tokens(messages)
    small = settings.compress_lightweight_token_threshold
    large = settings.compress_auto_balanced_tokens

    if tokens < small:
        return CompressionStrategy.FAST, ops

    if _has_code_content(messages):
        ops.append(f"auto_strategy:code-focused(tokens={tokens})")
        return CompressionStrategy.CODE_FOCUSED, ops

    if tokens >= large:
        ops.append(f"auto_strategy:balanced(tokens={tokens})")
        return CompressionStrategy.BALANCED, ops

    if tokens >= small:
        ops.append(f"auto_strategy:balanced(tokens={tokens})")
        return CompressionStrategy.BALANCED, ops

    return CompressionStrategy.FAST, ops


def resolve_proxy_compression(
    messages: list[Message],
    requested: CompressionStrategy,
    *,
    strategy_explicit: bool,
    use_ollama: bool | None,
) -> tuple[CompressionStrategy, list[str]]:
    """
    Pipeline final do proxy: auto-tier por tokens + downgrade sem Ollama + regras existentes.
    """
    ops: list[str] = []
    strategy = requested

    if not strategy_explicit:
        strategy, auto_ops = auto_proxy_strategy(messages)
        ops.extend(auto_ops)

    if use_ollama is not True:
        mapped = map_strategy_without_ollama(strategy)
        if mapped != strategy:
            ops.append(f"no_ollama:{strategy.value}->{mapped.value}")
            strategy = mapped

    tokens = count_message_tokens(messages)
    strategy, size_ops = resolve_compression_strategy(
        strategy, tokens, use_ollama=False if use_ollama is not True else use_ollama
    )
    ops.extend(size_ops)
    return strategy, ops
