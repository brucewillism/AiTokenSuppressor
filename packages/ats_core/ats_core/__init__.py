"""Núcleo puro de compressão de tokens do AI Token Suppressor."""

from ats_core.ast_service import ASTAnalysis, ASTService, CodeSymbol
from ats_core.compression import CompressionService, resolve_compression_strategy
from ats_core.content_detection import ContentAnalysis, ContentDetectionService
from ats_core.dedup import DeduplicationService
from ats_core.quality_guard import PreservedBlock, QualityGuardService, QualityReport
from ats_core.relevance import RelevanceScore, RelevanceService
from ats_core.specialized import SpecializedCompressionService
from ats_core.summary import HierarchicalSummary, HierarchicalSummaryService, SummaryLevel
from ats_core.suppressor import CompressionResult, TokenSuppressor
from ats_core.token_service import TokenService
from ats_core.types import CompressionStrategy, ContentType

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "ASTAnalysis",
    "ASTService",
    "CodeSymbol",
    "CompressionResult",
    "CompressionService",
    "CompressionStrategy",
    "ContentAnalysis",
    "ContentDetectionService",
    "ContentType",
    "DeduplicationService",
    "HierarchicalSummary",
    "HierarchicalSummaryService",
    "PreservedBlock",
    "QualityGuardService",
    "QualityReport",
    "RelevanceScore",
    "RelevanceService",
    "SpecializedCompressionService",
    "SummaryLevel",
    "TokenService",
    "TokenSuppressor",
    "resolve_compression_strategy",
]
