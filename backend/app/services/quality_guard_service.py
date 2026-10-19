"""Preservação de instruções críticas. Implementação em ats_core."""

from ats_core.quality_guard import (
    OUTPUT_CONTRACT_PATTERNS,
    SYSTEM_PROMPT_MIN_LENGTH,
    PreservedBlock,
    QualityGuardService,
    QualityReport,
)

__all__ = [
    "OUTPUT_CONTRACT_PATTERNS",
    "SYSTEM_PROMPT_MIN_LENGTH",
    "PreservedBlock",
    "QualityGuardService",
    "QualityReport",
]
