"""Cost-aware optimization decisions."""

from dataclasses import dataclass

from app.services.token_service import TokenService


@dataclass
class CostDecision:
    should_compress: bool
    should_use_local: bool
    should_use_cache: bool
    should_use_rag: bool
    max_tokens_budget: int | None
    estimated_cost_usd: float
    reason: str


PROVIDER_TOKEN_LIMITS = {
    "anthropic": {"claude-3-5-sonnet": 200000, "claude-3-haiku": 200000, "claude-3-opus": 200000},
    "openai": {"gpt-4o": 128000, "gpt-4o-mini": 128000, "gpt-4": 128000},
    "gemini": {"gemini-1.5-pro": 1000000, "gemini-1.5-flash": 1000000},
    "deepseek": {"deepseek-chat": 64000, "deepseek-coder": 64000},
}


class CostOptimizerService:
    def __init__(self) -> None:
        self.token_service = TokenService()

    def decide(
        self,
        messages: list[dict],
        target_model: str = "claude-3-5-sonnet",
        provider: str = "anthropic",
        cost_budget_usd: float | None = None,
        complexity_score: float = 0.5,
    ) -> CostDecision:
        tokens = self.token_service.count_messages(messages)
        estimated_cost = self.token_service.estimate_cost(tokens, target_model)

        should_compress = tokens > 2000 or estimated_cost > 0.01
        should_use_local = complexity_score < 0.4 or tokens > 10000
        should_use_cache = tokens > 500
        should_use_rag = tokens > 5000 and complexity_score > 0.5

        max_budget = None
        if cost_budget_usd:
            cost_per_token = estimated_cost / max(tokens, 1)
            max_budget = int(cost_budget_usd / max(cost_per_token, 1e-8))

        reason_parts = []
        if should_compress:
            reason_parts.append(f"compress({tokens} tokens)")
        if should_use_local:
            reason_parts.append("local_model_eligible")
        if cost_budget_usd and estimated_cost > cost_budget_usd:
            reason_parts.append("over_budget")

        return CostDecision(
            should_compress=should_compress,
            should_use_local=should_use_local,
            should_use_cache=should_use_cache,
            should_use_rag=should_use_rag,
            max_tokens_budget=max_budget,
            estimated_cost_usd=round(estimated_cost, 6),
            reason="; ".join(reason_parts) or "no_optimization_needed",
        )

    def provider_token_limit(self, provider: str, model: str) -> int:
        limits = PROVIDER_TOKEN_LIMITS.get(provider, {})
        for key, limit in limits.items():
            if key in model.lower():
                return limit
        return 128000

    def estimate_savings_usd(
        self, tokens_before: int, tokens_after: int, model: str,
    ) -> float:
        cost_before = self.token_service.estimate_cost(tokens_before, model)
        cost_after = self.token_service.estimate_cost(tokens_after, model)
        return max(0, cost_before - cost_after)
