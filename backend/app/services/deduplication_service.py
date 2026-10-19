"""Deduplicação do serviço. O algoritmo está em ats_core; a port de modelo é o Ollama local."""

from typing import Any

from ats_core.dedup import DeduplicationService as _CoreDeduplicationService


class DeduplicationService(_CoreDeduplicationService):
    def __init__(self, model: Any | None = None) -> None:
        if model is None:
            from app.services.ollama_service import OllamaService

            model = OllamaService()
        super().__init__(model=model)
