"""Pydantic request/response schemas."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class CompressionStrategy(str, Enum):
    AGGRESSIVE = "aggressive"
    BALANCED = "balanced"
    ULTRA = "ultra"
    SEMANTIC = "semantic"
    CODE_FOCUSED = "code-focused"
    CHAT_FOCUSED = "chat-focused"


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ContentType(str, Enum):
    CODE = "code"
    LOGS = "logs"
    MARKDOWN = "markdown"
    JSON = "json"
    XML = "xml"
    YAML = "yaml"
    STACKTRACE = "stacktrace"
    CHAT = "chat"
    DOCUMENTATION = "documentation"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class Message(BaseModel):
    role: MessageRole
    content: str
    name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompressRequest(BaseModel):
    messages: list[Message] = Field(min_length=1)
    strategy: CompressionStrategy = CompressionStrategy.BALANCED
    max_tokens: int | None = Field(default=None, ge=100)
    preserve_system: bool = True
    session_id: str | None = None
    user_id: str = "default"
    target_model: str = "claude-3-5-sonnet"
    check_semantic_loss: bool = True
    use_ollama: bool | None = None

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, v: list[Message]) -> list[Message]:
        if len(v) > 500:
            raise ValueError("Maximum 500 messages allowed")
        return v


class CompressResponse(BaseModel):
    messages: list[Message]
    tokens_before: int
    tokens_after: int
    tokens_saved: int
    savings_percent: float
    compression_ratio: float
    strategy: CompressionStrategy
    operations_applied: list[str]
    latency_ms: float
    semantic_loss_score: float | None = None
    content_types: dict[str, str] = Field(default_factory=dict)
    token_heatmap: list[dict[str, Any]] = Field(default_factory=list)
    quality_preserved: bool = True


class OptimizeRequest(BaseModel):
    messages: list[Message] = Field(min_length=1)
    strategy: CompressionStrategy = CompressionStrategy.BALANCED
    target_model: str = "claude-3-5-sonnet"
    provider: str = "anthropic"
    use_memory: bool = True
    use_rag: bool = False
    use_hierarchical_memory: bool = True
    use_semantic_cache: bool = True
    rag_collection: str = "default"
    session_id: str | None = None
    user_id: str = "default"
    max_tokens: int | None = None
    check_semantic_loss: bool = True
    cost_budget_usd: float | None = None


class OptimizeResponse(BaseModel):
    messages: list[Message]
    tokens_before: int
    tokens_after: int
    tokens_saved: int
    savings_percent: float
    recommended_model: str
    model_reason: str
    memory_injected: list[str]
    rag_context: list[str]
    operations_applied: list[str]
    cache_hit: bool
    latency_ms: float
    cost_saved_usd: float
    semantic_loss_score: float | None = None
    content_types: dict[str, str] = Field(default_factory=dict)
    token_heatmap: list[dict[str, Any]] = Field(default_factory=list)
    routing_details: dict[str, Any] = Field(default_factory=dict)
    graph_context: list[str] = Field(default_factory=list)
    quality_preserved: bool = True


class MemorySaveRequest(BaseModel):
    content: str = Field(min_length=1)
    memory_type: str = "context"
    user_id: str = "default"
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    entities: list[str] = Field(default_factory=list)


class MemorySaveResponse(BaseModel):
    id: UUID
    content: str
    summary: str | None
    memory_type: str
    created_at: datetime
    graph_entities: list[str] = Field(default_factory=list)


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1)
    user_id: str = "default"
    session_id: str | None = None
    top_k: int = Field(default=5, ge=1, le=50)
    memory_types: list[str] | None = None
    min_score: float = Field(default=0.5, ge=0.0, le=1.0)
    use_graph: bool = True


class MemoryItem(BaseModel):
    id: UUID
    content: str
    summary: str | None
    memory_type: str
    relevance_score: float
    metadata: dict[str, Any]
    created_at: datetime
    decay_score: float | None = None


class MemorySearchResponse(BaseModel):
    memories: list[MemoryItem]
    query: str
    total_found: int
    graph_entities: list[str] = Field(default_factory=list)


class RAGQueryRequest(BaseModel):
    query: str = Field(min_length=1)
    collection_id: str = "default"
    top_k: int = Field(default=5, ge=1, le=20)
    rerank: bool = True
    adaptive: bool = True
    max_context_tokens: int | None = None


class RAGChunk(BaseModel):
    id: UUID
    content: str
    source: str | None
    score: float
    chunk_index: int
    chunk_type: str = "document"
    symbol_name: str | None = None


class RAGQueryResponse(BaseModel):
    chunks: list[RAGChunk]
    query: str
    context: str
    total_found: int
    adaptive_params: dict[str, Any] = Field(default_factory=dict)


class RAGIngestRequest(BaseModel):
    content: str = Field(min_length=1)
    collection_id: str = "default"
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    language: str | None = None
    chunk_by_ast: bool = True


class RAGIngestResponse(BaseModel):
    chunks_created: int
    collection_id: str
    chunk_types: dict[str, int] = Field(default_factory=dict)


class AnalyzeRequest(BaseModel):
    messages: list[Message] = Field(min_length=1)
    target_model: str = "claude-3-5-sonnet"
    provider: str = "anthropic"


class AnalyzeResponse(BaseModel):
    tokens_before: int
    estimated_tokens_after: dict[str, int]
    estimated_savings: dict[str, float]
    recommended_strategy: CompressionStrategy
    complexity_score: float
    content_analysis: dict[str, Any]
    token_heatmap: list[dict[str, Any]] = Field(default_factory=list)
    content_types: dict[str, str] = Field(default_factory=dict)


class BenchmarkRequest(BaseModel):
    messages: list[Message] = Field(min_length=1)
    strategies: list[CompressionStrategy] | None = None
    target_model: str = "claude-3-5-sonnet"


class BenchmarkResult(BaseModel):
    strategy: str
    tokens_before: int
    tokens_after: int
    compression_ratio: float
    savings_percent: float
    semantic_loss_score: float
    latency_ms: float
    quality_preserved: bool


class BenchmarkResponse(BaseModel):
    results: list[BenchmarkResult]
    best_strategy: str
    best_balance_score: float


class HeatmapRequest(BaseModel):
    messages: list[Message] = Field(min_length=1)
    target_model: str = "claude-3-5-sonnet"


class HeatmapSegment(BaseModel):
    index: int
    role: str
    content_type: str
    tokens: int
    percent: float
    label: str
    compressible: bool


class HeatmapResponse(BaseModel):
    total_tokens: int
    segments: list[HeatmapSegment]
    hotspots: list[str]


class GraphQueryRequest(BaseModel):
    query: str = Field(min_length=1)
    user_id: str = "default"
    max_depth: int = Field(default=2, ge=1, le=5)


class GraphNode(BaseModel):
    id: str
    label: str
    entity_type: str
    weight: float


class GraphEdge(BaseModel):
    source: str
    target: str
    relationship: str
    weight: float


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    context_summary: str


class CodebaseIndexRequest(BaseModel):
    files: dict[str, str] = Field(description="filepath -> content")
    project_id: str = "default"
    collection_id: str = "codebase"


class CodebaseIndexResponse(BaseModel):
    files_indexed: int
    symbols_found: int
    chunks_created: int
    dependencies: dict[str, list[str]]


class StreamCompressRequest(BaseModel):
    messages: list[Message] = Field(min_length=1)
    strategy: CompressionStrategy = CompressionStrategy.BALANCED
    chunk_size: int = Field(default=5, ge=1, le=50)


class StatsResponse(BaseModel):
    total_requests: int
    total_tokens_saved: int
    total_cost_saved_usd: float
    average_compression_ratio: float
    average_latency_ms: float
    cache_hit_rate: float
    semantic_cache_hit_rate: float = 0.0
    average_semantic_loss: float = 0.0
    requests_by_strategy: dict[str, int]
    requests_by_model: dict[str, int]
    recent_requests: list[dict[str, Any]]


class HealthResponse(BaseModel):
    status: str
    service: str
    latency_ms: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
