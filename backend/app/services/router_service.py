"""Contextual model router with domain, language, cost and urgency awareness."""

import re
from typing import Any

from app.core.logging import get_logger
from app.services.content_detection_service import ContentDetectionService
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

TASK_MODEL_MAP = {
    "coding": {
        "default": "claude-3-5-sonnet",
        "python": "claude-3-5-sonnet",
        "javascript": "claude-3-5-sonnet",
        "typescript": "claude-3-5-sonnet",
        "local": "ollama/qwen2.5-coder:3b",
    },
    "summarization": {"default": "ollama/mistral", "local": "ollama/mistral"},
    "embedding": {"default": "nomic-embed-text", "local": "nomic-embed-text"},
    "reasoning": {"default": "claude-3-opus", "complex": "claude-3-opus"},
    "chat": {"default": "gpt-4o-mini", "local": "ollama/llama3.2"},
    "general": {"default": "claude-3-5-sonnet"},
}

PROVIDER_PREFERENCES = {
    "anthropic": "claude-3-5-sonnet",
    "openai": "gpt-4o",
    "gemini": "gemini-1.5-pro",
    "deepseek": "deepseek/deepseek-chat",
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
]

URGENCY_INDICATORS = [r"\burgent\b", r"\basap\b", r"\bcritical\b", r"\bproduction\b", r"\boutage\b"]


class RouterService:
    def __init__(self) -> None:
        self.token_service = TokenService()
        self.content_detector = ContentDetectionService()

    def analyze_complexity(self, messages: list[dict]) -> float:
        full_text = " ".join(str(m.get("content", "")) for m in messages)
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

        if len(re.findall(r"```", full_text)) > 4:
            score += 0.15
        if len(messages) > 20:
            score += 0.1

        return max(0.0, min(1.0, score))

    def detect_task_type(self, messages: list[dict]) -> str:
        full_text = " ".join(str(m.get("content", "")) for m in messages).lower()
        if any(kw in full_text for kw in ["summarize", "summary", "resumir", "resumo"]):
            return "summarization"
        if any(kw in full_text for kw in ["embed", "embedding", "vector"]):
            return "embedding"
        if any(kw in full_text for kw in ["code", "function", "class", "implement", "bug", "fix", "refactor"]):
            return "coding"
        if any(kw in full_text for kw in ["reason", "analyze", "think step", "prove"]):
            return "reasoning"
        if any(kw in full_text for kw in ["chat", "conversation"]):
            return "chat"
        return "general"

    def detect_language(self, messages: list[dict]) -> str | None:
        for msg in messages:
            analysis = self.content_detector.detect(str(msg.get("content", "")))
            if analysis.language:
                return analysis.language
        return None

    def detect_urgency(self, messages: list[dict]) -> float:
        full_text = " ".join(str(m.get("content", "")) for m in messages)
        hits = sum(1 for p in URGENCY_INDICATORS if re.search(p, full_text, re.IGNORECASE))
        return min(hits * 0.25, 1.0)

    def route(
        self,
        messages: list[dict],
        target_model: str | None = None,
        strategy: str = "balanced",
        provider: str = "anthropic",
        context_tokens: int | None = None,
    ) -> dict[str, Any]:
        task_type = self.detect_task_type(messages)
        complexity = self.analyze_complexity(messages)
        language = self.detect_language(messages)
        urgency = self.detect_urgency(messages)
        tokens = context_tokens or self.token_service.count_messages(messages)

        task_models = TASK_MODEL_MAP.get(task_type, TASK_MODEL_MAP["general"])

        if task_type == "summarization":
            model = task_models.get("local", "ollama/mistral")
            return self._build_result(model, "local", "Summarization → local Mistral", complexity, task_type, language, urgency, tokens, provider)

        if task_type == "embedding":
            return self._build_result("nomic-embed-text", "local", "Embeddings → local", complexity, task_type, language, urgency, tokens, provider)

        if task_type == "coding":
            model = task_models.get(language or "default", task_models["default"])
            if complexity < 0.4 and strategy == "aggressive":
                model = task_models.get("local", "ollama/qwen2.5-coder:3b")
            return self._build_result(model, "moderate" if complexity > 0.5 else "simple", f"Coding ({language or 'generic'})", complexity, task_type, language, urgency, tokens, provider)

        if task_type == "reasoning" and complexity > 0.7:
            model = task_models.get("complex", task_models["default"])
            return self._build_result(model, "complex", "Complex reasoning → Claude Opus", complexity, task_type, language, urgency, tokens, provider)

        if target_model:
            return self._build_result(target_model, self._model_to_tier(target_model), f"User-specified: {target_model}", complexity, task_type, language, urgency, tokens, provider)

        if urgency > 0.5:
            model = PROVIDER_PREFERENCES.get(provider, "claude-3-5-sonnet")
            return self._build_result(model, "moderate", "Urgent → fast capable model", complexity, task_type, language, urgency, tokens, provider)

        if complexity < 0.35:
            tier = "simple"
        elif complexity < 0.65:
            tier = "moderate"
        else:
            tier = "complex"

        if strategy == "aggressive" and tier != "complex":
            tier = "simple"
        if tokens > 50000 and task_type != "reasoning":
            tier = "simple"

        model = MODEL_TIERS[tier]["default"]
        if provider in PROVIDER_PREFERENCES and tier == "moderate":
            model = PROVIDER_PREFERENCES[provider]

        return self._build_result(
            model, tier, f"Complexity {complexity:.2f} → {tier}",
            complexity, task_type, language, urgency, tokens, provider,
        )

    def _build_result(
        self, model: str, tier: str, reason: str,
        complexity: float, task_type: str, language: str | None,
        urgency: float, tokens: int, provider: str,
    ) -> dict[str, Any]:
        return {
            "model": model,
            "tier": tier,
            "reason": reason,
            "complexity_score": complexity,
            "task_type": task_type,
            "language": language,
            "urgency_score": urgency,
            "context_tokens": tokens,
            "provider": provider,
            "use_local": tier == "local" or model.startswith("ollama/"),
        }

    def _model_to_tier(self, model: str) -> str:
        model_lower = model.lower()
        if model_lower.startswith("ollama/"):
            return "local"
        for tier, config in MODEL_TIERS.items():
            if any(m.lower() in model_lower for m in config["models"]):
                return tier
        return "moderate"
