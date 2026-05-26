"""Token counting and estimation service."""

from functools import lru_cache

import tiktoken

from app.core.logging import get_logger

logger = get_logger(__name__)

MODEL_ENCODINGS: dict[str, str] = {
    "gpt-4": "cl100k_base",
    "gpt-4o": "o200k_base",
    "gpt-3.5-turbo": "cl100k_base",
    "claude-3-5-sonnet": "cl100k_base",
    "claude-3-opus": "cl100k_base",
    "claude-3-haiku": "cl100k_base",
    "gemini-pro": "cl100k_base",
    "default": "cl100k_base",
}


@lru_cache(maxsize=8)
def _get_encoding(name: str) -> tiktoken.Encoding:
    return tiktoken.get_encoding(name)


class TokenService:
    def __init__(self, model: str = "default") -> None:
        self.model = model
        encoding_name = MODEL_ENCODINGS.get(model, MODEL_ENCODINGS["default"])
        self.encoding = _get_encoding(encoding_name)

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return len(self.encoding.encode(text))

    def count_messages(self, messages: list[dict]) -> int:
        total = 0
        for msg in messages:
            total += 4  # message overhead
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.count_tokens(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        total += self.count_tokens(part["text"])
            if msg.get("name"):
                total += self.count_tokens(msg["name"])
        total += 2  # reply priming
        return total

    def estimate_savings(
        self, tokens_before: int, tokens_after: int
    ) -> dict[str, float | int]:
        saved = max(0, tokens_before - tokens_after)
        ratio = tokens_after / tokens_before if tokens_before > 0 else 1.0
        percent = (saved / tokens_before * 100) if tokens_before > 0 else 0.0
        return {
            "tokens_before": tokens_before,
            "tokens_after": tokens_after,
            "tokens_saved": saved,
            "compression_ratio": round(ratio, 4),
            "savings_percent": round(percent, 2),
        }

    def estimate_cost(
        self,
        tokens: int,
        model: str,
        is_output: bool = False,
    ) -> float:
        from app.core.config import get_settings

        settings = get_settings()
        cost_map = {
            "claude": (settings.cost_claude_input, settings.cost_claude_output),
            "gpt": (settings.cost_openai_input, settings.cost_openai_output),
            "gemini": (settings.cost_gemini_input, settings.cost_gemini_output),
        }
        for key, (input_cost, output_cost) in cost_map.items():
            if key in model.lower():
                rate = output_cost if is_output else input_cost
                return (tokens / 1_000_000) * rate
        return (tokens / 1_000_000) * settings.cost_openai_input
