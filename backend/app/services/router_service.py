"""Smart model router based on task complexity."""

import re
from typing import Any

from app.core.logging import get_logger
from app.services.ollama_service import OllamaService
from app.services.token_service import TokenService

logger = get_logger(__name__)

MODEL_TIERS = {
    "simple": {
        "models": ["gpt-4o-mini", "claude-3-haiku", "gemini-1.5-flash"],
        "default": "gpt-4o-mini",
    },
    "moderate": {
        "models": ["gpt-4o", "claude-3-5-sonnet", "gemini-1.5-pro"],
        "default": "claude-3-5-sonnet",
    },
    "complex": {
        "models": ["gpt-4o", "claude-3-opus", "claude-3-5-sonnet"],
        "default": "claude-3-5-sonnet",
    },
    "local": {
        "models": ["ollama/llama3.2", "ollama/mistral"],
        "default": "ollama/llama3.2",
    },
}

COMPLEXITY_INDICATORS = [
    r"\barchitect\b", r"\bdesign pattern\b", r"\brefactor\b",
    r"\bsecurity\b", r"\bperformance\b", r"\boptimiz",
    r"\bdebug\b", r"\bimplement\b", r"\bcomplex\b",
    r"\bmulti.?step\b", r"\banaly[sz]e\b",
]

SIMPLE_INDICATORS = [
    r"\bsummarize\b", r"\btranslate\b", r"\bformat\b",
    r"\bwhat is\b", r"\bdefine\b", r"\blist\b",
    r"\byes or no\b", r"\btrue or false\b",
]


class RouterService:
    def __init__(self) -> None:
        self.token_service = TokenService()
        self.ollama = OllamaService()

    def analyze_complexity(self, messages: list[dict]) -> float:
        full_text = " ".join(
            str(m.get("content", "")) for m in messages if isinstance(m.get("content"), str)
        )
        score = 0.5

        token_count = self.token_service.count_tokens(full_text)
        if token_count > 10000:
            score += 0.2
        elif token_count > 5000:
            score += 0.1
        elif token_count < 500:
            score -= 0.1

        for pattern in COMPLEXITY_INDICATORS:
            if re.search(pattern, full_text, re.IGNORECASE):
                score += 0.1

        for pattern in SIMPLE_INDICATORS:
            if re.search(pattern, full_text, re.IGNORECASE):
                score -= 0.15

        code_blocks = len(re.findall(r"```", full_text))
        if code_blocks > 4:
            score += 0.15

        if len(messages) > 20:
            score += 0.1

        return max(0.0, min(1.0, score))

    def detect_task_type(self, messages: list[dict]) -> str:
        full_text = " ".join(
            str(m.get("content", "")) for m in messages if isinstance(m.get("content"), str)
        ).lower()

        if any(kw in full_text for kw in ["summarize", "summary", "resumir", "resumo"]):
            return "summarization"
        if any(kw in full_text for kw in ["embed", "embedding", "vector", "similarity"]):
            return "embedding"
        if any(kw in full_text for kw in ["code", "function", "class", "implement", "bug", "fix"]):
            return "coding"
        if any(kw in full_text for kw in ["chat", "conversation", "talk"]):
            return "chat"
        return "general"

    def route(
        self,
        messages: list[dict],
        target_model: str | None = None,
        strategy: str = "balanced",
    ) -> dict[str, Any]:
        task_type = self.detect_task_type(messages)
        complexity = self.analyze_complexity(messages)

        if task_type == "summarization":
            return {
                "model": "ollama/llama3.2",
                "tier": "local",
                "reason": "Summarization task routed to local Ollama",
                "complexity_score": complexity,
                "task_type": task_type,
            }

        if task_type == "embedding":
            return {
                "model": "nomic-embed-text",
                "tier": "local",
                "reason": "Embedding task routed to local model",
                "complexity_score": complexity,
                "task_type": task_type,
            }

        if target_model:
            tier = self._model_to_tier(target_model)
            return {
                "model": target_model,
                "tier": tier,
                "reason": f"User-specified model: {target_model}",
                "complexity_score": complexity,
                "task_type": task_type,
            }

        if complexity < 0.35:
            tier = "simple"
        elif complexity < 0.65:
            tier = "moderate"
        else:
            tier = "complex"

        if strategy == "aggressive" and tier != "complex":
            tier = "simple"

        model = MODEL_TIERS[tier]["default"]
        return {
            "model": model,
            "tier": tier,
            "reason": f"Complexity score {complexity:.2f} → {tier} tier",
            "complexity_score": complexity,
            "task_type": task_type,
        }

    def _model_to_tier(self, model: str) -> str:
        model_lower = model.lower()
        for tier, config in MODEL_TIERS.items():
            if any(m.lower() in model_lower or model_lower in m.lower() for m in config["models"]):
                return tier
        return "moderate"

    def should_use_local(self, task_type: str, complexity: float) -> bool:
        if task_type in ("summarization", "embedding"):
            return True
        return complexity < 0.3
