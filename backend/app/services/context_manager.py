"""Intelligent context window manager."""

from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.ollama_service import OllamaService
from app.services.relevance_service import RelevanceService
from app.services.token_service import TokenService
from app.utils.helpers import truncate_smart

logger = get_logger(__name__)
settings = get_settings()


class ContextManager:
    def __init__(self) -> None:
        self.token_service = TokenService()
        self.ollama = OllamaService()
        self.relevance = RelevanceService()
        self.max_tokens = settings.max_context_tokens
        self.window_size = settings.sliding_window_size

    def calculate_relevance_score(self, message: dict, recent_context: str) -> float:
        return self.relevance.score_message(message, recent_context).total

    async def classify_irrelevant(self, messages: list[dict]) -> list[int]:
        irrelevant: list[int] = []
        non_system_indices = [
            i for i, m in enumerate(messages) if m.get("role") != "system"
        ]
        last_user_idx = next(
            (i for i in range(len(messages) - 1, -1, -1) if messages[i].get("role") == "user"),
            None,
        )
        filler = frozenset({"ok", "thanks", "thank you", "got it", "sure", "yes", "no"})

        for i, msg in enumerate(messages):
            score = self.relevance.score_message(msg)
            content = str(msg.get("content", "")).strip()
            role = msg.get("role", "user")

            if score.is_critical:
                continue
            # Nunca esvaziar o thread: última mensagem do user ou única não-system
            if i == last_user_idx:
                continue
            if len(non_system_indices) <= 1 and i in non_system_indices:
                continue

            if len(content) < 10 and role != "user":
                irrelevant.append(i)
            elif content.lower() in filler and role != "user":
                irrelevant.append(i)
            elif score.total < 0.15 and role not in ("system", "user"):
                irrelevant.append(i)
        return irrelevant

    def sliding_window(self, messages: list[dict], window_size: int | None = None) -> list[dict]:
        size = window_size or self.window_size
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]

        if len(other_msgs) <= size:
            return messages

        return system_msgs + other_msgs[-size:]

    async def summarize_old_context(self, messages: list[dict]) -> tuple[list[dict], list[str]]:
        operations: list[str] = []
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]

        if len(other_msgs) <= 10:
            return messages, operations

        split_point = len(other_msgs) // 2
        old_msgs = other_msgs[:split_point]
        recent_msgs = other_msgs[split_point:]

        old_text = "\n".join(
            f"[{m.get('role')}]: {str(m.get('content', ''))[:300]}" for m in old_msgs
        )

        try:
            summary = await self.ollama.summarize(old_text, max_words=250)
            summary_msg = {
                "role": "system",
                "content": f"[Historical context summary]: {summary}",
            }
            operations.append("rolling_memory_summary")
            return system_msgs + [summary_msg] + recent_msgs, operations
        except Exception as exc:
            logger.warning("summarize_old_context_failed", error=str(exc))
            return messages, operations

    async def dynamic_trim(
        self,
        messages: list[dict],
        max_tokens: int | None = None,
    ) -> tuple[list[dict], list[str]]:
        limit = max_tokens or self.max_tokens
        operations: list[str] = []
        current_tokens = self.token_service.count_messages(messages)

        if current_tokens <= limit:
            return messages, operations

        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]

        recent_context = " ".join(
            str(m.get("content", ""))[:200] for m in other_msgs[-3:]
        )

        scored: list[tuple[float, int, dict]] = []
        for i, msg in enumerate(other_msgs):
            score = self.calculate_relevance_score(msg, recent_context)
            scored.append((score, i, msg))

        scored.sort(key=lambda x: x[0], reverse=True)

        kept: list[dict] = []
        token_budget = limit - self.token_service.count_messages(system_msgs)

        for score, _idx, msg in scored:
            msg_tokens = self.token_service.count_tokens(str(msg.get("content", ""))) + 4
            if token_budget - msg_tokens >= 0:
                kept.append(msg)
                token_budget -= msg_tokens
            else:
                operations.append(f"trimmed_low_relevance:{score:.2f}")

        kept.sort(key=lambda m: other_msgs.index(m) if m in other_msgs else 0)

        if token_budget < 0:
            messages, sum_ops = await self.summarize_old_context(system_msgs + kept)
            operations.extend(sum_ops)
            return messages, operations

        return system_msgs + kept, operations

    async def manage_context(
        self,
        messages: list[dict],
        max_tokens: int | None = None,
        use_sliding_window: bool = True,
    ) -> tuple[list[dict], list[str]]:
        operations: list[str] = []
        result = messages

        irrelevant = await self.classify_irrelevant(result)
        if irrelevant:
            result = [m for i, m in enumerate(result) if i not in irrelevant]
            operations.append(f"removed_{len(irrelevant)}_irrelevant_messages")

        if use_sliding_window:
            windowed = self.sliding_window(result)
            if len(windowed) < len(result):
                operations.append("sliding_window_applied")
            result = windowed

        result, trim_ops = await self.dynamic_trim(result, max_tokens)
        operations.extend(trim_ops)

        return result, operations

    def prioritize_recent(self, messages: list[dict], ratio: float = 0.7) -> list[dict]:
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]

        if not other_msgs:
            return messages

        recent_count = max(1, int(len(other_msgs) * ratio))
        recent = other_msgs[-recent_count:]
        older = other_msgs[:-recent_count]

        compressed_older: list[dict] = []
        for msg in older:
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > 200:
                compressed_older.append({
                    **msg,
                    "content": truncate_smart(content, 200),
                })
            else:
                compressed_older.append(msg)

        return system_msgs + compressed_older + recent
