"""LiteLLM universal gateway integration."""

from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

try:
    import litellm
    litellm.set_verbose = settings.app_debug
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False


PROVIDER_MAP = {
    "anthropic": "claude-3-5-sonnet",
    "openai": "gpt-4o",
    "gemini": "gemini/gemini-1.5-pro",
    "deepseek": "deepseek/deepseek-chat",
    "ollama": "ollama/llama3.2",
}


class LiteLLMService:
    def __init__(self) -> None:
        self.available = LITELLM_AVAILABLE
        if self.available:
            if settings.anthropic_api_key:
                litellm.api_key = settings.anthropic_api_key
            litellm.drop_params = True

    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        provider: str = "anthropic",
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        if not self.available:
            return {"error": "litellm_not_installed", "content": ""}

        resolved_model = model or PROVIDER_MAP.get(provider, "gpt-4o-mini")
        try:
            response = await litellm.acompletion(
                model=resolved_model,
                messages=[{"role": m["role"], "content": m["content"]} for m in messages],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            content = response.choices[0].message.content
            usage = response.usage
            return {
                "content": content,
                "model": resolved_model,
                "tokens_input": usage.prompt_tokens if usage else 0,
                "tokens_output": usage.completion_tokens if usage else 0,
                "cost_usd": litellm.completion_cost(completion_response=response) if usage else 0,
            }
        except Exception as exc:
            logger.error("litellm_completion_failed", error=str(exc))
            return {"error": str(exc), "content": ""}

    def estimate_cost(self, tokens: int, model: str) -> float:
        if not self.available:
            return 0.0
        try:
            return litellm.completion_cost(model=model, prompt="", completion=" " * tokens)
        except Exception:
            return 0.0

    def get_provider_model(self, provider: str, task_type: str = "general") -> str:
        task_models = {
            "coding": {"anthropic": "claude-3-5-sonnet", "openai": "gpt-4o", "deepseek": "deepseek/deepseek-coder"},
            "summarization": {"ollama": "ollama/mistral", "openai": "gpt-4o-mini"},
            "reasoning": {"anthropic": "claude-3-opus", "openai": "gpt-4o"},
            "embedding": {"ollama": "ollama/nomic-embed-text"},
        }
        if task_type in task_models and provider in task_models[task_type]:
            return task_models[task_type][provider]
        return PROVIDER_MAP.get(provider, "gpt-4o-mini")

    async def health_check(self) -> dict[str, Any]:
        return {
            "status": "healthy" if self.available else "unavailable",
            "litellm_installed": self.available,
        }
