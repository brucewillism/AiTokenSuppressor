"""Prometheus metrics definitions."""

from prometheus_client import Counter, Gauge, Histogram, Info

APP_INFO = Info("ats_app", "AI Token Suppressor application info")

REQUESTS_TOTAL = Counter(
    "ats_requests_total",
    "Total API requests",
    ["endpoint", "method", "status"],
)

COMPRESSION_RATIO = Histogram(
    "ats_compression_ratio",
    "Compression ratio achieved",
    ["strategy"],
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

TOKENS_SAVED = Counter(
    "ats_tokens_saved_total",
    "Total tokens saved",
    ["model", "strategy"],
)

REQUEST_LATENCY = Histogram(
    "ats_request_latency_seconds",
    "Request latency in seconds",
    ["endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

CACHE_HITS = Counter(
    "ats_cache_hits_total",
    "Cache hit count",
    ["cache_type"],
)

CACHE_MISSES = Counter(
    "ats_cache_misses_total",
    "Cache miss count",
    ["cache_type"],
)

ACTIVE_CONNECTIONS = Gauge(
    "ats_active_connections",
    "Active database connections",
)

OLLAMA_REQUESTS = Counter(
    "ats_ollama_requests_total",
    "Ollama API requests",
    ["operation", "status"],
)

MEMORY_RECALLS = Counter(
    "ats_memory_recalls_total",
    "Semantic memory recalls",
)
