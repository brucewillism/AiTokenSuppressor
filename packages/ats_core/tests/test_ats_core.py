"""Testes do núcleo puro. Só fixtures sintéticas."""

from __future__ import annotations

import ast
import asyncio
import copy
import logging
import tomllib
from pathlib import Path

import ats_core
from ats_core import (
    CompressionService,
    CompressionStrategy,
    TokenSuppressor,
    __version__,
)
from tests.synthetic_fixtures import (
    DUPLICATE_LINE,
    PYTHON_SNIPPET,
    SENTINEL,
    SHORT_USER,
    SYSTEM,
    VERBOSE_USER,
    conversation,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "ats_core"
FORBIDDEN_MODULES = {
    "aiohttp",
    "anthropic",
    "asyncpg",
    "celery",
    "fastapi",
    "httpx",
    "litellm",
    "ollama",
    "openai",
    "pgvector",
    "psycopg",
    "redis",
    "requests",
    "socket",
    "sqlalchemy",
    "uvicorn",
}


def _run(coro):
    return asyncio.run(coro)


class _FakeModel:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def summarize(self, text: str, max_words: int = 150) -> str:
        self.calls.append("summarize")
        return f"resumo sintetico de {max_words} palavras"

    async def compress(self, text: str, target_ratio: float = 0.5) -> str:
        self.calls.append("compress")
        return "texto sintetico comprimido"

    async def detect_redundancy(self, messages: list[str]) -> list[int]:
        self.calls.append("redundancy")
        return []


def test_version_matches_pyproject():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert __version__ == "0.1.0"
    assert ats_core.__version__ == "0.1.0"
    assert pyproject["project"]["version"] == "0.1.0"


def test_public_api_is_explicit():
    assert ats_core.__all__ == [
        "__version__",
        "ASTAnalysis",
        "ASTService",
        "CodeSymbol",
        "CompressionResult",
        "CompressionService",
        "CompressionStrategy",
        "ContentAnalysis",
        "ContentDetectionService",
        "ContentType",
        "DeduplicationService",
        "HierarchicalSummary",
        "HierarchicalSummaryService",
        "PreservedBlock",
        "QualityGuardService",
        "QualityReport",
        "RelevanceScore",
        "RelevanceService",
        "SpecializedCompressionService",
        "SummaryLevel",
        "TokenService",
        "TokenSuppressor",
        "resolve_compression_strategy",
    ]
    for name in ats_core.__all__:
        assert hasattr(ats_core, name)


def test_package_does_not_import_network_or_storage():
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module.split(".")[0]]
            leaked = FORBIDDEN_MODULES.intersection(modules)
            assert not leaked, f"{path.name} importa {sorted(leaked)}"


def test_compress_shrinks_verbose_synthetic_text_and_keeps_system():
    result = _run(
        TokenSuppressor().compress(
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": VERBOSE_USER},
            ],
            strategy="balanced",
            use_ollama=False,
            sensitivity="PUBLIC",
        )
    )
    assert result.ats_mode == "ENABLED"
    assert result.tokens_in_original > 0
    assert result.tokens_in_final <= result.tokens_in_original
    assert result.compression_ratio == round(result.tokens_in_final / result.tokens_in_original, 4)
    assert result.t_ats_ms >= 0
    assert any(message["content"] == SYSTEM for message in result.messages)


def test_same_input_same_messages_and_operations():
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": VERBOSE_USER},
    ]
    first = _run(TokenSuppressor().compress(messages, strategy="code-focused", use_ollama=False))
    second = _run(TokenSuppressor().compress(messages, strategy="code-focused", use_ollama=False))
    assert first.messages == second.messages
    assert first.operations == second.operations
    assert first.tokens_in_original == second.tokens_in_original
    assert first.tokens_in_final == second.tokens_in_final


def test_duplicate_synthetic_messages_collapse():
    message = {"role": "user", "content": DUPLICATE_LINE}
    result = _run(
        TokenSuppressor().compress(
            [message, dict(message)],
            strategy="fast",
            use_ollama=False,
        )
    )
    users = [item for item in result.messages if item.get("role") == "user"]
    assert len(users) == 1
    assert any(op.startswith("removed_duplicate_message:") for op in result.operations)


def test_code_strategy_keeps_synthetic_function_name():
    result = _run(
        TokenSuppressor().compress(
            [{"role": "user", "content": PYTHON_SNIPPET}],
            strategy="code-focused",
            use_ollama=False,
        )
    )
    joined = "\n".join(str(item.get("content", "")) for item in result.messages)
    assert "synthetic_widget_total" in joined


def test_disabled_model_port_is_not_called():
    model = _FakeModel()
    result = _run(
        TokenSuppressor(model=model).compress(
            conversation(),
            strategy="ultra",
            use_ollama=False,
        )
    )
    assert model.calls == []
    assert result.messages
    assert any(item["content"] == SYSTEM for item in result.messages)


def test_model_port_is_used_only_when_requested_and_logs_omit_text(caplog):
    model = _FakeModel()
    with caplog.at_level(logging.DEBUG, logger="ats_core"):
        result = _run(
            TokenSuppressor(model=model).compress(
                conversation(),
                strategy="balanced",
                use_ollama=True,
            )
        )
    assert "summarize" in model.calls
    assert result.tokens_in_final > 0
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert SENTINEL not in logged
    assert VERBOSE_USER[:40] not in logged


def test_missing_model_port_falls_back_without_raising(caplog):
    with caplog.at_level(logging.WARNING, logger="ats_core"):
        result = _run(
            TokenSuppressor().compress(
                [{"role": "user", "content": VERBOSE_USER + SENTINEL}],
                strategy="ultra",
                use_ollama=True,
            )
        )
    assert result.messages
    assert SENTINEL not in " ".join(record.getMessage() for record in caplog.records)


def test_facade_matches_engine_messages():
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": SHORT_USER + " " + VERBOSE_USER},
    ]
    engine = CompressionService()
    compressed, operations = _run(
        engine.compress_prompt(
            copy.deepcopy(messages),
            strategy=CompressionStrategy.FAST,
            use_ollama=False,
        )
    )
    result = _run(
        TokenSuppressor().compress(copy.deepcopy(messages), strategy="fast", use_ollama=False)
    )
    assert result.messages == compressed
    assert result.operations == operations


def test_small_prompt_resolves_to_fast_without_settings():
    from ats_core import CompressionStrategy, resolve_compression_strategy

    strategy, ops = resolve_compression_strategy(
        CompressionStrategy.BALANCED,
        tokens_before=50,
        use_ollama=False,
    )
    assert strategy == CompressionStrategy.FAST
    assert ops
