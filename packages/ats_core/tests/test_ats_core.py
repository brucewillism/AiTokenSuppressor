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
    DeduplicationService,
    QualityGuardService,
    TokenSuppressor,
    __version__,
)
from tests.synthetic_fixtures import (
    DUPLICATE_LINE,
    FINAL_QUESTION,
    LONG_FINAL_USER,
    NEAR_NEWER_QUESTION,
    NEAR_OLDER_QUESTION,
    PYTHON_SNIPPET,
    REPEATED_LINE,
    SENTINEL,
    SHORT_USER,
    SYSTEM,
    VERBOSE_USER,
    conversation,
    long_final_budget_messages,
    near_duplicate_final_question,
    repeated_final_question,
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
    assert __version__ == "0.1.1"
    assert ats_core.__version__ == "0.1.1"
    assert pyproject["project"]["version"] == "0.1.1"


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
    assert users[0]["content"] == DUPLICATE_LINE
    assert result.messages[-1]["role"] == "user"
    assert result.messages[-1]["content"] == DUPLICATE_LINE
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


def test_dedup_keeps_newest_message_and_drops_the_older_copy():
    text = "Qual é o total sintético do widget azul?"
    older = {"role": "user", "content": text, "name": "older"}
    newer = {"role": "user", "content": text.upper(), "name": "newer"}
    deduped, operations = DeduplicationService().deduplicate_messages(
        [older, {"role": "assistant", "content": "O total sintético é 4."}, newer]
    )
    assert [item.get("name") for item in deduped if item.get("role") == "user"] == ["newer"]
    assert deduped[-1] is newer
    assert deduped[-1]["content"] == text.upper()
    assert any(op == "removed_duplicate_message:user" for op in operations)
    assert all(item.get("name") != "older" for item in deduped)


def test_repeated_final_question_stays_last_and_verbatim():
    result = _run(
        TokenSuppressor().compress(
            repeated_final_question(),
            strategy="balanced",
            use_ollama=False,
        )
    )
    assert result.messages[-1]["role"] == "user"
    assert result.messages[-1]["content"] == FINAL_QUESTION
    assert sum(item.get("content") == FINAL_QUESTION for item in result.messages) == 1
    assert result.messages[-1]["content"].count(REPEATED_LINE) == 2
    assert any(item.get("role") == "assistant" for item in result.messages)
    assert any(op.startswith("removed_duplicate_message:user") for op in result.operations)

    near = _run(
        TokenSuppressor().compress(
            near_duplicate_final_question(),
            strategy="fast",
            use_ollama=False,
        )
    )
    assert near.messages[-1] == {"role": "user", "content": NEAR_NEWER_QUESTION}
    assert all(item.get("content") != NEAR_OLDER_QUESTION for item in near.messages)


def test_budget_trimming_keeps_long_final_user_message():
    assert len(LONG_FINAL_USER) > 500
    result = _run(
        TokenSuppressor().compress(
            long_final_budget_messages(),
            strategy="fast",
            use_ollama=False,
            max_tokens=16,
        )
    )
    assert result.messages[-1]["role"] == "user"
    assert result.messages[-1]["content"] == LONG_FINAL_USER
    assert sum(item.get("content") == LONG_FINAL_USER for item in result.messages) == 1
    assert not result.messages[-1]["content"].startswith("...")
    assert any(item.get("role") == "system" and item.get("content") == SYSTEM for item in result.messages)
    assert any(op.startswith("trimmed_message:user") for op in result.operations)
    assert any(op.startswith("trimmed_message:assistant") for op in result.operations)
    assert all("contexto antigo do widget" not in str(item.get("content", "")) for item in result.messages)
    assert all("resposta antiga do widget" not in str(item.get("content", "")) for item in result.messages)


def test_all_strategies_preserve_final_user_without_ollama():
    model = _FakeModel()
    for strategy in CompressionStrategy:
        result = _run(
            TokenSuppressor(model=model).compress(
                copy.deepcopy(repeated_final_question()),
                strategy=strategy,
                use_ollama=False,
            )
        )
        assert result.messages[-1]["role"] == "user", strategy.value
        assert result.messages[-1]["content"] == FINAL_QUESTION, strategy.value
        assert result.messages[-1]["content"].count(REPEATED_LINE) == 2, strategy.value
        assert any(item.get("role") == "assistant" for item in result.messages), strategy.value
    assert model.calls == []


def test_earlier_user_text_still_shrinks_when_final_turn_is_pinned():
    final = "Qual é o total sintético do widget azul?"
    result = _run(
        TokenSuppressor().compress(
            [
                {"role": "user", "content": VERBOSE_USER},
                {"role": "assistant", "content": "ok"},
                {"role": "user", "content": final},
            ],
            strategy="fast",
            use_ollama=False,
        )
    )
    assert result.messages[-1]["content"] == final
    earlier = [
        item["content"]
        for item in result.messages
        if item.get("role") == "user" and item.get("content") != final
    ]
    assert earlier
    assert "Please note that" not in earlier[0]
    assert len(earlier[0]) < len(VERBOSE_USER)


def test_last_user_stays_verbatim_before_a_trailing_assistant():
    final_user = "Qual é o total sintético do widget azul? " + ("detalhe " * 30)
    trailing = "Resposta sintética que precisa permanecer depois do usuário."
    messages = [{"role": "system", "content": SYSTEM}]
    for index in range(8):
        messages.append(
            {
                "role": "user" if index % 2 == 0 else "assistant",
                "content": f"turno {index} {VERBOSE_USER}",
            }
        )
    messages[-2]["content"] = final_user
    messages[-1]["content"] = trailing
    model = _FakeModel()
    result = _run(
        TokenSuppressor(model=model).compress(
            messages,
            strategy="balanced",
            use_ollama=True,
        )
    )
    assert "summarize" in model.calls
    user_at = next(index for index, item in enumerate(result.messages) if item.get("content") == final_user)
    assistant_at = next(
        index for index, item in enumerate(result.messages) if item.get("content") == trailing
    )
    assert user_at < assistant_at
    assert result.messages[-1]["content"] == trailing


def test_quality_guard_moves_reordered_final_user_back_to_the_end():
    final = {"role": "user", "content": FINAL_QUESTION}
    original = [
        {"role": "system", "content": SYSTEM},
        {"role": "assistant", "content": "O total sintético é 4."},
        final,
    ]
    compressed = [final, {"role": "assistant", "content": "O total sintético é 4."}]
    merged, _report = QualityGuardService().merge_with_compressed(original, compressed)
    assert merged[-1] is final
    assert merged[-1]["content"] == FINAL_QUESTION


def test_small_prompt_resolves_to_fast_without_settings():
    from ats_core import CompressionStrategy, resolve_compression_strategy

    strategy, ops = resolve_compression_strategy(
        CompressionStrategy.BALANCED,
        tokens_before=50,
        use_ollama=False,
    )
    assert strategy == CompressionStrategy.FAST
    assert ops
