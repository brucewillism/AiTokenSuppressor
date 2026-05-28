"""LiteLLM universal gateway with ordered provider fallback."""

from collections.abc import AsyncIterator
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


# Ordem padrão: Groq → OpenAI → Claude → Gemini → DeepSeek → Ollama
DEFAULT_FALLBACK_CHAIN: tuple[str, ...] = (
    "groq",
    "openai",
    "anthropic",
    "gemini",
    "deepseek",
    "ollama",
)

PROVIDER_DEFAULTS: dict[str, str] = {
    "groq": "groq/llama-3.3-70b-versatile",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-20241022",
    "gemini": "gemini/gemini-1.5-flash",
    "deepseek": "deepseek/deepseek-chat",
    "ollama": "ollama/llama3.2",
}


class LiteLLMService:
    def __init__(self) -> None:
        self.available = LITELLM_AVAILABLE
        if self.available:
            litellm.drop_params = True

    def get_fallback_chain(self) -> list[str]:
        raw = settings.proxy_provider_fallback.strip()
        if not raw:
            return list(DEFAULT_FALLBACK_CHAIN)
        chain = [p.strip().lower() for p in raw.split(",") if p.strip()]
        valid = [p for p in chain if p in PROVIDER_DEFAULTS]
        return valid or list(DEFAULT_FALLBACK_CHAIN)

    def _provider_available(self, provider: str) -> bool:
        if provider == "groq":
            return bool(settings.groq_api_key)
        if provider == "openai":
            return bool(settings.openai_api_key)
        if provider == "anthropic":
            return bool(settings.anthropic_api_key)
        if provider == "gemini":
            return bool(settings.gemini_api_key)
        if provider == "deepseek":
            return bool(settings.deepseek_api_key)
        if provider == "ollama":
            return bool(settings.ollama_base_url)
        return False

    def _resolve_api_key(self, provider: str) -> str | None:
        keys = {
            "groq": settings.groq_api_key,
            "openai": settings.openai_api_key,
            "anthropic": settings.anthropic_api_key,
            "gemini": settings.gemini_api_key,
            "deepseek": settings.deepseek_api_key,
        }
        key = keys.get(provider, "")
        return key or None

    def _model_belongs_to_provider(self, model: str, provider: str) -> bool:
        m = model.lower()
        if provider == "groq":
            return m.startswith("groq/") or "groq" in m
        if provider == "openai":
            return m.startswith("gpt") or m.startswith("openai/")
        if provider == "anthropic":
            return "claude" in m or m.startswith("anthropic/")
        if provider == "gemini":
            return "gemini" in m
        if provider == "deepseek":
            return "deepseek" in m
        if provider == "ollama":
            return m.startswith("ollama/") or "llama" in m
        return False

    def _resolve_model_for_provider(self, provider: str, requested_model: str | None) -> str:
        if requested_model and self._model_belongs_to_provider(requested_model, provider):
            if requested_model.startswith("groq/") or requested_model.startswith("ollama/"):
                return requested_model
            if provider == "gemini" and not requested_model.startswith("gemini/"):
                return f"gemini/{requested_model}"
            if provider == "deepseek" and not requested_model.startswith("deepseek/"):
                return f"deepseek/{requested_model}"
            return requested_model
        return PROVIDER_DEFAULTS[provider]

    def _format_messages(self, messages: list[dict]) -> list[dict[str, str]]:
        formatted: list[dict[str, str]] = []
        for m in messages:
            role = str(m.get("role", "user"))
            if role == "tool":
                role = "user"
            content = m.get("content", "")
            if not isinstance(content, str):
                content = str(content)
            formatted.append({"role": role, "content": content})
        return formatted

    def _build_kwargs(
        self,
        provider: str,
        model: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
        *,
        stream: bool = False,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": self._format_messages(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if stream:
            kwargs["stream"] = True
        api_key = self._resolve_api_key(provider)
        if api_key:
            kwargs["api_key"] = api_key
        if provider == "ollama":
            kwargs["api_base"] = settings.ollama_base_url.rstrip("/")
        return kwargs

    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        provider: str = "openai",
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        if not self.available:
            return {"error": "litellm_not_installed", "content": ""}

        resolved_model = self._resolve_model_for_provider(provider, model)
        try:
            kwargs = self._build_kwargs(
                provider, resolved_model, messages, max_tokens, temperature
            )
            response = await litellm.acompletion(**kwargs)
            content = response.choices[0].message.content or ""
            usage = response.usage
            return {
                "content": content,
                "model": resolved_model,
                "provider_used": provider,
                "tokens_input": usage.prompt_tokens if usage else 0,
                "tokens_output": usage.completion_tokens if usage else 0,
                "cost_usd": (
                    litellm.completion_cost(completion_response=response) if usage else 0
                ),
            }
        except Exception as exc:
            logger.error(
                "litellm_completion_failed",
                provider=provider,
                model=resolved_model,
                error=str(exc),
            )
            return {"error": str(exc), "content": "", "provider_used": provider}

    async def complete_with_fallback(
        self,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """Tenta provedores na ordem configurada até obter resposta."""
        if not self.available:
            return {"error": "litellm_not_installed", "content": ""}

        errors: list[str] = []
        chain = self.get_fallback_chain()

        for provider in chain:
            if not self._provider_available(provider):
                errors.append(f"{provider}: skipped (no credentials)")
                logger.info("provider_skipped", provider=provider, reason="no_credentials")
                continue

            resolved_model = self._resolve_model_for_provider(provider, model)
            result = await self.complete(
                messages=messages,
                model=resolved_model,
                provider=provider,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            if not result.get("error"):
                logger.info(
                    "provider_fallback_success",
                    provider=provider,
                    model=resolved_model,
                )
                result["fallback_chain"] = chain
                result["providers_tried"] = [
                    e.split(":")[0] for e in errors if ":" in e
                ] + [provider]
                return result

            err_msg = str(result["error"])
            errors.append(f"{provider}: {err_msg}")
            logger.warning(
                "provider_fallback_failed",
                provider=provider,
                model=resolved_model,
                error=err_msg,
            )

        return {
            "error": "All providers failed. " + " | ".join(errors),
            "content": "",
            "providers_tried": [e.split(":")[0] for e in errors if ":" in e],
            "fallback_chain": chain,
        }

    async def complete_stream(
        self,
        messages: list[dict],
        model: str | None = None,
        provider: str = "openai",
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> AsyncIterator[dict[str, Any]]:
        if not self.available:
            yield {"delta": {"content": ""}, "finish_reason": "stop"}
            return

        resolved_model = self._resolve_model_for_provider(provider, model)
        kwargs = self._build_kwargs(
            provider, resolved_model, messages, max_tokens, temperature, stream=True
        )
        response = await litellm.acompletion(**kwargs)
        sent_role = False
        async for chunk in response:
            choice = chunk.choices[0]
            delta: dict[str, str] = {}
            if choice.delta.role and not sent_role:
                delta["role"] = choice.delta.role
                sent_role = True
            if choice.delta.content:
                delta["content"] = choice.delta.content
            finish = choice.finish_reason
            if delta or finish:
                yield {"delta": delta, "finish_reason": finish}

    async def complete_stream_with_fallback(
        self,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> AsyncIterator[dict[str, Any]]:
        """Streaming com fallback: tenta cada provedor até iniciar stream."""
        if not self.available:
            yield {"delta": {"content": "LiteLLM not available"}, "finish_reason": "stop"}
            return

        errors: list[str] = []
        for provider in self.get_fallback_chain():
            if not self._provider_available(provider):
                errors.append(f"{provider}: skipped")
                continue
            resolved_model = self._resolve_model_for_provider(provider, model)
            try:
                async for chunk in self.complete_stream(
                    messages=messages,
                    model=resolved_model,
                    provider=provider,
                    max_tokens=max_tokens,
                    temperature=temperature,
                ):
                    yield chunk
                return
            except Exception as exc:
                errors.append(f"{provider}: {exc}")
                logger.warning("stream_fallback_failed", provider=provider, error=str(exc))

        yield {
            "delta": {
                "content": f"All providers failed: {' | '.join(errors)}",
            },
            "finish_reason": "stop",
        }

    def estimate_cost(self, tokens: int, model: str) -> float:
        if not self.available:
            return 0.0
        try:
            return litellm.completion_cost(model=model, prompt="", completion=" " * tokens)
        except Exception:
            return 0.0

    def get_provider_model(self, provider: str, task_type: str = "general") -> str:
        return PROVIDER_DEFAULTS.get(provider, "gpt-4o-mini")

    async def health_check(self) -> dict[str, Any]:
        chain = self.get_fallback_chain()
        available = [p for p in chain if self._provider_available(p)]
        return {
            "status": "healthy" if self.available and available else "degraded",
            "litellm_installed": self.available,
            "fallback_chain": chain,
            "providers_available": available,
        }
