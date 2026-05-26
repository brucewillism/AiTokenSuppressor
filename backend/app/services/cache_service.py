"""Redis semantic cache service."""

import hashlib
import json
from typing import Any

from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import CACHE_HITS, CACHE_MISSES
from app.core.redis_client import get_redis
from app.utils.helpers import cosine_similarity, fingerprint

logger = get_logger(__name__)
settings = get_settings()

CACHE_PREFIX = "ats:cache:"
EMBED_PREFIX = "ats:embed:"
COMPRESS_PREFIX = "ats:compress:"
RESPONSE_PREFIX = "ats:response:"


class CacheService:
    def __init__(self) -> None:
        self.ttl = settings.redis_cache_ttl

    async def _redis(self) -> Redis:
        return await get_redis()

    def _key(self, prefix: str, content: str) -> str:
        fp = fingerprint(content)
        return f"{prefix}{fp}"

    async def get(self, prefix: str, content: str) -> Any | None:
        redis = await self._redis()
        key = self._key(prefix, content)
        data = await redis.get(key)
        if data:
            CACHE_HITS.labels(cache_type=prefix).inc()
            return json.loads(data)
        CACHE_MISSES.labels(cache_type=prefix).inc()
        return None

    async def set(self, prefix: str, content: str, value: Any, ttl: int | None = None) -> None:
        redis = await self._redis()
        key = self._key(prefix, content)
        await redis.setex(key, ttl or self.ttl, json.dumps(value))

    async def get_compression(self, content: str) -> dict[str, Any] | None:
        return await self.get(COMPRESS_PREFIX, content)

    async def set_compression(self, content: str, result: dict[str, Any]) -> None:
        await self.set(COMPRESS_PREFIX, content, result, ttl=self.ttl * 2)

    async def get_embedding(self, text: str) -> list[float] | None:
        return await self.get(EMBED_PREFIX, text)

    async def set_embedding(self, text: str, embedding: list[float]) -> None:
        await self.set(EMBED_PREFIX, text, embedding, ttl=self.ttl * 24)

    async def get_response(self, prompt_hash: str) -> str | None:
        redis = await self._redis()
        data = await redis.get(f"{RESPONSE_PREFIX}{prompt_hash}")
        if data:
            CACHE_HITS.labels(cache_type="response").inc()
            return data
        CACHE_MISSES.labels(cache_type="response").inc()
        return None

    async def set_response(self, prompt_hash: str, response: str, ttl: int | None = None) -> None:
        redis = await self._redis()
        await redis.setex(f"{RESPONSE_PREFIX}{prompt_hash}", ttl or self.ttl, response)

    async def find_similar_cached(
        self,
        embedding: list[float],
        prefix: str = CACHE_PREFIX,
        threshold: float = 0.92,
    ) -> tuple[str, Any] | None:
        redis = await self._redis()
        pattern = f"{prefix}*"
        best_score = 0.0
        best_key: str | None = None
        best_value: Any = None

        async for key in redis.scan_iter(match=pattern, count=100):
            data = await redis.get(key)
            if not data:
                continue
            try:
                parsed = json.loads(data)
                cached_emb = parsed.get("embedding")
                if cached_emb and isinstance(cached_emb, list):
                    score = cosine_similarity(embedding, cached_emb)
                    if score > threshold and score > best_score:
                        best_score = score
                        best_key = key
                        best_value = parsed.get("value")
            except (json.JSONDecodeError, TypeError):
                continue

        if best_key and best_value is not None:
            CACHE_HITS.labels(cache_type="semantic").inc()
            return best_key, best_value

        CACHE_MISSES.labels(cache_type="semantic").inc()
        return None

    async def cache_with_embedding(
        self,
        content: str,
        value: Any,
        embedding: list[float],
        prefix: str = CACHE_PREFIX,
        ttl: int | None = None,
    ) -> None:
        redis = await self._redis()
        key = self._key(prefix, content)
        payload = {"value": value, "embedding": embedding}
        await redis.setex(key, ttl or self.ttl, json.dumps(payload))

    async def increment_stat(self, stat_name: str, amount: int = 1) -> None:
        redis = await self._redis()
        await redis.incrby(f"ats:stats:{stat_name}", amount)

    async def get_stat(self, stat_name: str) -> int:
        redis = await self._redis()
        val = await redis.get(f"ats:stats:{stat_name}")
        return int(val) if val else 0

    async def health_check(self) -> dict[str, Any]:
        try:
            redis = await self._redis()
            start = __import__("time").perf_counter()
            await redis.ping()
            latency = (__import__("time").perf_counter() - start) * 1000
            return {"status": "healthy", "latency_ms": round(latency, 2)}
        except Exception as exc:
            return {"status": "unhealthy", "error": str(exc)}

    @staticmethod
    def hash_prompt(messages: list[dict]) -> str:
        content = json.dumps(messages, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode()).hexdigest()
