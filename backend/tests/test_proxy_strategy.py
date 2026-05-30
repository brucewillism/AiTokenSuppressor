"""Tests for memory-efficient proxy strategy selection."""

from app.schemas import CompressionStrategy, Message, MessageRole
from app.services.proxy_strategy_service import (
    auto_proxy_strategy,
    map_strategy_without_ollama,
    resolve_proxy_compression,
)


def _user(content: str) -> Message:
    return Message(role=MessageRole.USER, content=content)


def test_map_ultra_to_balanced_without_ollama():
    assert map_strategy_without_ollama(CompressionStrategy.ULTRA) == CompressionStrategy.BALANCED


def test_small_prompt_stays_fast():
    strategy, ops = auto_proxy_strategy([_user("oi")])
    assert strategy == CompressionStrategy.FAST
    assert not ops


def test_large_prompt_uses_balanced():
    big = "Explain this architecture in detail. " * 200
    strategy, ops = auto_proxy_strategy([_user(big)])
    assert strategy == CompressionStrategy.BALANCED
    assert any("balanced" in o for o in ops)


def test_code_prompt_uses_code_focused():
    code = "```python\n" + "def foo():\n    return 1\n" * 80 + "```"
    strategy, ops = auto_proxy_strategy([_user(code)])
    assert strategy == CompressionStrategy.CODE_FOCUSED
    assert ops


def test_resolve_proxy_downgrades_ultra_env_without_ollama():
    big = "context " * 500
    strategy, ops = resolve_proxy_compression(
        [_user(big)],
        CompressionStrategy.ULTRA,
        strategy_explicit=False,
        use_ollama=False,
    )
    assert strategy in (CompressionStrategy.BALANCED, CompressionStrategy.CODE_FOCUSED)
    assert any("no_ollama" in o or "auto_strategy" in o for o in ops)
