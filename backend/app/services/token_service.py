"""Contagem de tokens do serviço. O núcleo está em ats_core; o custo lê a config local."""

from ats_core.token_service import TokenService as _CoreTokenService


class TokenService(_CoreTokenService):
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
