"""Sumarização hierárquica do serviço. O algoritmo está em ats_core; a port é o Ollama local."""

from typing import Any

from ats_core.summary import HierarchicalSummary, HierarchicalSummaryService as _CoreSummary
from ats_core.summary import SummaryLevel

__all__ = ["HierarchicalSummary", "HierarchicalSummaryService", "SummaryLevel"]


class HierarchicalSummaryService(_CoreSummary):
    def __init__(self, model: Any | None = None) -> None:
        if model is None:
            from app.services.ollama_service import OllamaService

            model = OllamaService()
        super().__init__(model=model)
