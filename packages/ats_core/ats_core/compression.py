"""Motor de compressão. Não abre rede, banco, Redis, Ollama nem provedor."""

import copy
import logging
import re
from typing import Any

from ats_core.dedup import DeduplicationService
from ats_core.quality_guard import QualityGuardService, _last_user_index
from ats_core.relevance import RelevanceService
from ats_core.specialized import SpecializedCompressionService
from ats_core.summary import HierarchicalSummaryService
from ats_core.textutil import (
    compact_json,
    minify_whitespace,
    parse_json_safe,
    remove_duplicate_lines,
    remove_stack_trace_duplicates,
    truncate_smart,
)
from ats_core.token_service import TokenService
from ats_core.types import CompressionStrategy

logger = logging.getLogger("ats_core")

DEFAULT_LIGHTWEIGHT_TOKEN_THRESHOLD = 400


def _message_dict(message: Any) -> Any:
    """Aceita dict ou modelo com model_dump(), como o serviço fazia com Message."""
    if isinstance(message, dict):
        return message
    dump = getattr(message, "model_dump", None)
    if callable(dump):
        return dump()
    return message

HEAVY_STRATEGIES = frozenset({CompressionStrategy.ULTRA, CompressionStrategy.SEMANTIC})

STRATEGY_CONFIG: dict[str, dict[str, Any]] = {
    "fast": {"target_ratio": 0.9, "summarize_threshold": 100_000, "use_ollama": False},
    "aggressive": {"target_ratio": 0.3, "summarize_threshold": 500, "use_ollama": True},
    "balanced": {"target_ratio": 0.5, "summarize_threshold": 1000, "use_ollama": True},
    "ultra": {"target_ratio": 0.15, "summarize_threshold": 300, "use_ollama": True},
    "semantic": {"target_ratio": 0.4, "summarize_threshold": 800, "use_ollama": True},
    "code-focused": {"target_ratio": 0.6, "summarize_threshold": 2000, "use_ollama": False},
    "chat-focused": {"target_ratio": 0.45, "summarize_threshold": 600, "use_ollama": True},
}


def resolve_compression_strategy(
    strategy: CompressionStrategy,
    tokens_before: int,
    use_ollama: bool | None,
    *,
    threshold: int | None = None,
    lightweight_token_threshold: int = DEFAULT_LIGHTWEIGHT_TOKEN_THRESHOLD,
) -> tuple[CompressionStrategy, list[str]]:
    """Use `fast` automatically for small prompts unless Ollama or heavy strategy."""
    limit = threshold if threshold is not None else lightweight_token_threshold
    if use_ollama is True or strategy in HEAVY_STRATEGIES:
        return strategy, []
    if tokens_before >= limit:
        return strategy, []
    if strategy in (CompressionStrategy.FAST, CompressionStrategy.CODE_FOCUSED):
        return strategy, []
    return CompressionStrategy.FAST, [f"auto_strategy:fast(tokens<{limit})"]


class CompressionService:
    def __init__(
        self,
        model: Any | None = None,
        lightweight_token_threshold: int = DEFAULT_LIGHTWEIGHT_TOKEN_THRESHOLD,
    ) -> None:
        self.lightweight_token_threshold = lightweight_token_threshold
        self.token_service = TokenService()
        self.dedup_service = DeduplicationService(model=model)
        self.ollama = model
        self.specialized = SpecializedCompressionService()
        self.quality_guard = QualityGuardService()
        self.relevance = RelevanceService()
        self.hierarchical_summary = HierarchicalSummaryService(model=model)

    def _get_config(self, strategy: CompressionStrategy) -> dict[str, Any]:
        return STRATEGY_CONFIG.get(strategy.value, STRATEGY_CONFIG["balanced"])

    def minify_prompt(self, text: str) -> tuple[str, list[str]]:
        operations: list[str] = []
        result = text

        result = minify_whitespace(result)
        operations.append("minify_whitespace")

        result = remove_duplicate_lines(result)
        operations.append("remove_duplicate_lines")

        result = remove_stack_trace_duplicates(result)
        operations.append("remove_stack_traces")

        result = re.sub(r"\n{3,}", "\n\n", result)
        operations.append("collapse_blank_lines")

        verbose_patterns = [
            (r"Please note that\s+", ""),
            (r"It is important to (?:note|remember) that\s+", ""),
            (r"As mentioned (?:above|earlier|before),?\s*", ""),
            (r"In order to\s+", "To "),
            (r"Due to the fact that\s+", "Because "),
            (r"At this point in time\s+", "Now "),
        ]
        for pattern, replacement in verbose_patterns:
            new_result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
            if new_result != result:
                operations.append("reduce_verbosity")
                result = new_result

        return result, operations

    def compact_json_in_text(self, text: str) -> tuple[str, list[str]]:
        operations: list[str] = []
        json_pattern = r"(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}|\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\])"

        def replace_json(match: re.Match[str]) -> str:
            parsed = parse_json_safe(match.group(0))
            if parsed is not None:
                operations.append("compact_json")
                return compact_json(parsed, max_length=1500)
            return match.group(0)

        result = re.sub(json_pattern, replace_json, text, count=10)
        return result, operations

    async def summarize_history(
        self, messages: list[dict], keep_recent: int = 5
    ) -> tuple[list[dict], list[str]]:
        operations: list[str] = []
        if len(messages) <= keep_recent + 1:
            return messages, operations

        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]

        if len(other_msgs) <= keep_recent:
            return messages, operations

        old_msgs = other_msgs[:-keep_recent]
        recent_msgs = other_msgs[-keep_recent:]

        old_text = "\n".join(
            f"[{m.get('role')}]: {m.get('content', '')[:500]}" for m in old_msgs
        )

        try:
            summary_result = await self.hierarchical_summary.summarize_messages(old_msgs)
            summary = summary_result.final_summary
            summary_msg = {
                "role": "system",
                "content": f"[Conversation summary of {len(old_msgs)} earlier messages]: {summary}",
            }
            operations.append(f"hierarchical_summary_{len(old_msgs)}_messages")
            return system_msgs + [summary_msg] + recent_msgs, operations
        except Exception:
            logger.warning("summarize_history_failed")
            return messages, operations

    async def semantic_reduce(self, text: str, target_ratio: float = 0.5) -> tuple[str, list[str]]:
        operations: list[str] = []
        try:
            compressed = await self.ollama.compress(text, target_ratio=target_ratio)
            operations.append("semantic_reduce_ollama")
            return compressed, operations
        except Exception:
            logger.warning("semantic_reduce_failed")
            max_chars = int(len(text) * target_ratio)
            return truncate_smart(text, max_chars), ["semantic_reduce_truncation"]

    async def deduplicate_content(
        self,
        messages: list[dict],
        *,
        preserve: dict | None = None,
    ) -> tuple[list[dict], list[str]]:
        all_ops: list[str] = []

        deduped, msg_ops = self.dedup_service.deduplicate_messages(messages, preserve=preserve)
        all_ops.extend(msg_ops)

        result: list[dict] = []
        for msg in deduped:
            if msg is preserve:
                result.append(msg)
                continue
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > 100:
                deduped_content, content_ops = self.dedup_service.deduplicate_content(content)
                all_ops.extend(content_ops)
                result.append({**msg, "content": deduped_content})
            else:
                result.append(msg)

        return result, all_ops

    async def compress_prompt(
        self,
        messages: list[Any],
        strategy: CompressionStrategy = CompressionStrategy.BALANCED,
        max_tokens: int | None = None,
        preserve_system: bool = True,
        use_ollama: bool | None = None,
    ) -> tuple[list[dict], list[str]]:
        config = self._get_config(strategy)
        ollama_enabled = config["use_ollama"] if use_ollama is None else use_ollama
        operations: list[str] = []

        msg_dicts = [_message_dict(m) for m in messages]
        pin_index = _last_user_index(msg_dicts)
        pinned = msg_dicts[pin_index] if pin_index is not None else None
        snapshot = copy.deepcopy(pinned) if pinned is not None else None
        was_last = pin_index is not None and pin_index == len(msg_dicts) - 1

        msg_dicts, dedup_ops = await self.deduplicate_content(msg_dicts, preserve=pinned)
        operations.extend(dedup_ops)
        if pinned is not None and not any(message is pinned for message in msg_dicts):
            if was_last:
                msg_dicts.append(pinned)
            else:
                msg_dicts.insert(min(pin_index or 0, len(msg_dicts)), pinned)
        if pinned is not None and snapshot is not None:
            _restore_snapshot(pinned, snapshot)

        protected, compressible = self.quality_guard.protect_during_compression(msg_dicts)
        if protected:
            operations.append(f"protected_{len(protected)}_critical_messages")

        if ollama_enabled:
            keep_recent = 8 if strategy == CompressionStrategy.CHAT_FOCUSED else 5
            compressible = await self._summarize_keeping_final_user(
                compressible,
                pinned,
                keep_recent=keep_recent,
                operations=operations,
            )

        processed: list[dict] = list(protected)
        for msg in compressible:
            if msg is pinned:
                processed.append(msg)
                continue
            content = msg.get("content", "")
            if not isinstance(content, str):
                processed.append(msg)
                continue

            if msg.get("role") == "system" and preserve_system and len(content) < 2000:
                processed.append(msg)
                continue

            result_content = content
            msg_ops: list[str] = []

            if strategy == CompressionStrategy.FAST:
                result_content, min_ops = self.minify_prompt(content)
                msg_ops.extend(min_ops)
                result_content, json_ops = self.compact_json_in_text(result_content)
                msg_ops.extend(json_ops)
            elif strategy == CompressionStrategy.CODE_FOCUSED:
                result_content, code_ops = self.dedup_service.deduplicate_code_blocks(content)
                msg_ops.extend(code_ops)
                spec_content, spec_ops, _ct = self.specialized.compress_message(result_content)
                result_content = spec_content
                msg_ops.extend(spec_ops)
            else:
                spec_content, spec_ops, _ct = self.specialized.compress_message(content)
                result_content = spec_content
                msg_ops.extend(spec_ops)
                result_content, min_ops = self.minify_prompt(result_content)
                msg_ops.extend(min_ops)
                result_content, json_ops = self.compact_json_in_text(result_content)
                msg_ops.extend(json_ops)

            token_count = self.token_service.count_tokens(result_content)
            threshold = config["summarize_threshold"]

            if token_count > threshold and ollama_enabled:
                if strategy in (CompressionStrategy.SEMANTIC, CompressionStrategy.ULTRA):
                    result_content, sem_ops = await self.semantic_reduce(
                        result_content, config["target_ratio"]
                    )
                    msg_ops.extend(sem_ops)
                else:
                    try:
                        result_content = await self.ollama.summarize(
                            result_content, max_words=int(token_count * config["target_ratio"] * 0.75)
                        )
                        msg_ops.append("ollama_summarize")
                    except Exception:
                        max_chars = int(len(result_content) * config["target_ratio"])
                        result_content = truncate_smart(result_content, max_chars)
                        msg_ops.append("truncate_fallback")

            operations.extend(msg_ops)
            processed.append({**msg, "content": result_content})

        if max_tokens:
            processed = self._enforce_token_limit(
                processed, max_tokens, operations, preserve=pinned
            )

        if pinned is not None and snapshot is not None:
            _restore_snapshot(pinned, snapshot)

        processed, quality_report = self.quality_guard.merge_with_compressed(msg_dicts, processed)
        if quality_report.violations:
            operations.extend(quality_report.violations)

        return processed, operations

    async def _summarize_keeping_final_user(
        self,
        compressible: list[dict],
        pinned: dict | None,
        *,
        keep_recent: int,
        operations: list[str],
    ) -> list[dict]:
        """Sumariza o miolo antigo sem engolir o último turno do usuário."""
        if not _pinned_would_be_summarized(compressible, pinned, keep_recent):
            summarized, sum_ops = await self.summarize_history(
                compressible, keep_recent=keep_recent
            )
            operations.extend(sum_ops)
            return summarized

        pin_at = 0
        body: list[dict] = []
        for index, message in enumerate(compressible):
            if message is pinned:
                pin_at = index
                continue
            body.append(message)

        summarized, sum_ops = await self.summarize_history(body, keep_recent=keep_recent)
        operations.extend(sum_ops)
        if any(op.startswith("hierarchical_summary_") for op in sum_ops):
            insert_at = next(
                (index for index, message in enumerate(summarized) if message.get("role") != "system"),
                len(summarized),
            )
            return summarized[:insert_at] + [pinned] + summarized[insert_at:]
        pin_at = min(pin_at, len(summarized))
        return summarized[:pin_at] + [pinned] + summarized[pin_at:]

    def _enforce_token_limit(
        self,
        messages: list[dict],
        max_tokens: int,
        operations: list[str],
        preserve: dict | None = None,
    ) -> list[dict]:
        current = self.token_service.count_messages(messages)
        if current <= max_tokens:
            return messages

        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]

        while current > max_tokens and other_msgs:
            removable = _removable_index(other_msgs, preserve)
            if removable is None:
                break
            removed = other_msgs.pop(removable)
            current = self.token_service.count_messages(system_msgs + other_msgs)
            operations.append(f"trimmed_message:{removed.get('role')}")

        if current > max_tokens:
            for msg in reversed(other_msgs):
                if msg is preserve:
                    continue
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > 500:
                    msg["content"] = truncate_smart(content, 500, preserve_end=True)
                    operations.append("truncated_oversized_message")
                    current = self.token_service.count_messages(system_msgs + other_msgs)
                    if current <= max_tokens:
                        break

        return system_msgs + other_msgs


def _restore_snapshot(pinned: dict, snapshot: dict) -> None:
    pinned.clear()
    pinned.update(copy.deepcopy(snapshot))


def _pinned_would_be_summarized(
    messages: list[dict], pinned: dict | None, keep_recent: int
) -> bool:
    if pinned is None or not any(message is pinned for message in messages):
        return False
    others = [message for message in messages if message.get("role") != "system"]
    if len(messages) <= keep_recent + 1 or len(others) <= keep_recent:
        return False
    return all(message is not pinned for message in others[-keep_recent:])


def _removable_index(messages: list[dict], preserve: dict | None) -> int | None:
    if preserve is None:
        return 0 if messages else None
    for index, message in enumerate(messages):
        if message is not preserve:
            return index
    return None
