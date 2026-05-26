"""Application configuration via environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


CompressionStrategy = Literal[
    "aggressive", "balanced", "ultra", "semantic", "code-focused", "chat-focused"
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "AI Token Suppressor"
    app_env: str = "development"
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    secret_key: str = Field(
        default="change-me-to-a-secure-random-string-min-32-chars",
        min_length=32,
    )
    api_key: str = "ats-dev-api-key"

    database_url: str = "postgresql+asyncpg://ats:ats_secret@localhost:5432/ai_token_suppressor"
    database_pool_size: int = 20
    database_max_overflow: int = 10

    redis_url: str = "redis://localhost:6379/0"
    redis_cache_ttl: int = 3600

    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_timeout: int = 120

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    openrouter_api_key: str = ""

    jwt_secret_key: str = Field(
        default="change-me-jwt-secret-key-min-32-chars-long",
        min_length=32,
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    rate_limit_requests: int = 100
    rate_limit_window: int = 60

    max_payload_size_mb: int = 10
    max_messages: int = 500

    default_compression_strategy: CompressionStrategy = "balanced"
    target_compression_ratio: float = 0.4

    rag_chunk_size: int = 512
    rag_chunk_overlap: int = 64
    rag_top_k: int = 5

    max_context_tokens: int = 128000
    sliding_window_size: int = 50

    cost_claude_input: float = 3.0
    cost_claude_output: float = 15.0
    cost_openai_input: float = 2.5
    cost_openai_output: float = 10.0
    cost_gemini_input: float = 1.25
    cost_gemini_output: float = 5.0

    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    prometheus_enabled: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: str | list[str]) -> str:
        if isinstance(v, list):
            return ",".join(v)
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_payload_bytes(self) -> int:
        return self.max_payload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
